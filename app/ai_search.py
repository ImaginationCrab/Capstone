import json
import anthropic
from .config import ANTHROPIC_API_KEY

_STOP_WORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "will",
    "not", "are", "was", "but", "all", "can", "its", "been", "into",
    "made", "used", "use", "also", "more", "such", "each", "than",
}


def get_candidates(description: str, conn) -> list[dict]:
    """Multi-strategy candidate search for AI ranking."""
    words = [
        w.strip(".,;:!?") for w in description.lower().split()
        if len(w.strip(".,;:!?")) > 3 and w.lower() not in _STOP_WORDS
    ][:6]

    if not words:
        words = description.split()[:4]

    # Strategy 1: FTS OR search across key terms
    fts_parts = []
    for w in words[:5]:
        fts_parts.append(f'"{w}"')
        fts_parts.append(f'"{w}"*')
    fts_query = " OR ".join(fts_parts)

    try:
        rows = conn.execute(
            """SELECT c.id, c.hts_code, c.description, c.unit, c.general, c.special, c.other, c.chapter, c.indent
               FROM hts_search s JOIN hts_codes c ON c.id = s.rowid
               WHERE hts_search MATCH ? ORDER BY rank LIMIT 50""",
            (fts_query,),
        ).fetchall()
        if rows:
            return [dict(r) for r in rows]
    except Exception:
        pass

    # Strategy 2: LIKE fallback on individual terms
    seen, results = set(), []
    for word in words[:4]:
        rows = conn.execute(
            "SELECT id, hts_code, description, unit, general, special, other, chapter, indent "
            "FROM hts_codes WHERE description LIKE ? LIMIT 25",
            (f"%{word}%",),
        ).fetchall()
        for row in rows:
            rd = dict(row)
            if rd["id"] not in seen:
                seen.add(rd["id"])
                results.append(rd)
    return results[:50]


def ai_classify_hts(product_description: str, candidates: list[dict]) -> list[dict]:
    """Use Claude to rank HTS code candidates by relevance and return confidence scores."""
    if not ANTHROPIC_API_KEY or not candidates:
        return [{**c, "confidence": None} for c in candidates[:10]]

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    candidates_text = "\n".join(
        f"{i + 1}. [{c['hts_code']}] {c['description']} | Rate: {c.get('general') or 'N/A'}"
        for i, c in enumerate(candidates[:40])
    )

    prompt = (
        f'You are a US Customs HTS tariff classification expert.\n\n'
        f'A user is importing: "{product_description}"\n\n'
        f"Candidate HTS codes from the tariff schedule:\n{candidates_text}\n\n"
        f"Select and rank the top 10 best matches. "
        f"Respond ONLY with a JSON array:\n"
        f'[{{"index": 3, "confidence": 92}}, {{"index": 7, "confidence": 78}}, ...]\n\n'
        f"Rules:\n"
        f"- index is 1-based position in the list above\n"
        f"- confidence 0-100: 80-100=near-certain, 60-79=likely, 40-59=possible, <40=unlikely\n"
        f"- Return up to 10 entries, no other text"
    )

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        rankings = json.loads(raw)

        results = []
        for item in rankings[:10]:
            idx = int(item.get("index", 0)) - 1
            if 0 <= idx < len(candidates):
                entry = candidates[idx].copy()
                entry["confidence"] = float(item.get("confidence", 0))
                results.append(entry)
        return results

    except Exception as e:
        print(f"[AI search] Claude error: {e}")
        return [{**c, "confidence": None} for c in candidates[:10]]
