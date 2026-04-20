import sqlite3
from fastapi import APIRouter, Query, HTTPException, Request
from ..database import get_db, rows_to_dicts
from ..auth import try_get_current_user, get_current_user
from ..config import ANTHROPIC_API_KEY
from ..ai_search import get_candidates, ai_classify_hts

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
async def keyword_search(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(50, ge=1, le=200),
):
    with get_db() as conn:
        terms = q.strip().split()
        fts_query = " ".join(terms[:-1] + [terms[-1] + "*"]) if terms else q
        try:
            results = conn.execute(
                """SELECT c.hts_code, c.description, c.unit, c.general, c.special, c.other, c.chapter, c.indent
                   FROM hts_search s JOIN hts_codes c ON c.id = s.rowid
                   WHERE hts_search MATCH ? ORDER BY rank LIMIT ?""",
                (fts_query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            results = conn.execute(
                "SELECT hts_code, description, unit, general, special, other, chapter, indent "
                "FROM hts_codes WHERE description LIKE ? ORDER BY hts_code LIMIT ?",
                (f"%{q}%", limit),
            ).fetchall()
    return {"query": q, "count": len(results), "results": rows_to_dicts(results)}


@router.get("/lookup/{hts_code}")
async def lookup(hts_code: str):
    with get_db() as conn:
        results = conn.execute(
            "SELECT * FROM hts_codes WHERE hts_code = ?", (hts_code,)
        ).fetchall()
        if not results:
            results = conn.execute(
                "SELECT * FROM hts_codes WHERE hts_code LIKE ? ORDER BY hts_code LIMIT 100",
                (f"{hts_code}%",),
            ).fetchall()
        if not results:
            raise HTTPException(404, f"No HTS code found for '{hts_code}'")
    return {"code": hts_code, "count": len(results), "results": rows_to_dicts(results)}


@router.get("/ai-search")
async def ai_search(
    q: str = Query(..., min_length=1, max_length=400),
    limit: int = Query(10, ge=1, le=50),
    request: Request = None,
):
    """AI-powered search using Claude to classify and rank HTS codes."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(503, "AI search not available — ANTHROPIC_API_KEY not configured")

    user = try_get_current_user(request) if request else None

    with get_db() as conn:
        candidates = get_candidates(q, conn)

        if not candidates:
            return {"query": q, "count": 0, "results": [], "mode": "ai"}

        ranked = ai_classify_hts(q, candidates)
        ranked = ranked[:limit]

        if user:
            conn.execute(
                "INSERT INTO search_history (user_id, query, mode, result_count) VALUES (?, ?, 'ai', ?)",
                (user["id"], q, len(ranked)),
            )
            conn.commit()

    return {"query": q, "count": len(ranked), "results": ranked, "mode": "ai"}


@router.get("/history")
async def get_search_history(request: Request):
    user = get_current_user(request)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, query, mode, result_count, created_at FROM search_history "
            "WHERE user_id = ? ORDER BY created_at DESC LIMIT 100",
            (user["id"],),
        ).fetchall()
    return {"history": rows_to_dicts(rows)}
