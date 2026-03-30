"""
HTS Code Lookup API
====================
A single-file FastAPI app that serves HTS code search results.

Run with:
    uvicorn main:app --reload

Endpoints:
    GET /                   → serves the frontend
    GET /api/search?q=...   → full-text search on HTS descriptions
    GET /api/lookup/{code}  → exact HTS code lookup
    GET /api/health         → health check + import metadata
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "hts.db"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="HTS Code Lookup",
    version="0.1.0",
    description="Search the Harmonized Tariff Schedule of the United States",
)

# Serve static files (frontend)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Database helpers ─────────────────────────────────────────────────────

@contextmanager
def get_db():
    """Yield a read-only database connection."""
    if not DB_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail="Database not found. Run: python scripts/import_hts.py",
        )
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    try:
        yield conn
    finally:
        conn.close()


def rows_to_dicts(rows) -> list[dict]:
    """Convert sqlite3.Row objects to plain dicts."""
    return [dict(row) for row in rows]


# ── Routes ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the frontend."""
    html_path = STATIC_DIR / "index.html"
    return HTMLResponse(html_path.read_text())


@app.get("/api/search")
async def search(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
):
    """
    Full-text search across HTS descriptions.

    Uses SQLite FTS5 with Porter stemming, so queries like "frozen fish"
    will match "frozen fillets of fish" etc.
    """
    with get_db() as conn:
        # FTS5 query — add * for prefix matching on the last term
        # so "cotto" matches "cotton", "cottonseed", etc.
        terms = q.strip().split()
        fts_query = " ".join(terms[:-1] + [terms[-1] + "*"]) if terms else q

        try:
            results = conn.execute(
                """
                SELECT
                    c.hts_code,
                    c.description,
                    c.unit,
                    c.general,
                    c.special,
                    c.other,
                    c.chapter,
                    c.indent
                FROM hts_search s
                JOIN hts_codes c ON c.id = s.rowid
                WHERE hts_search MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            # If the FTS query syntax is invalid, fall back to LIKE
            results = conn.execute(
                """
                SELECT hts_code, description, unit, general, special, other, chapter, indent
                FROM hts_codes
                WHERE description LIKE ?
                ORDER BY hts_code
                LIMIT ?
                """,
                (f"%{q}%", limit),
            ).fetchall()

    return {
        "query": q,
        "count": len(results),
        "results": rows_to_dicts(results),
    }


@app.get("/api/lookup/{hts_code}")
async def lookup(hts_code: str):
    """
    Exact lookup by HTS code (or prefix).

    Examples:
        /api/lookup/0101.21.00    → exact match
        /api/lookup/0101          → all codes starting with 0101
    """
    with get_db() as conn:
        # Try exact match first
        results = conn.execute(
            "SELECT * FROM hts_codes WHERE hts_code = ?", (hts_code,)
        ).fetchall()

        # If no exact match, treat as prefix
        if not results:
            results = conn.execute(
                "SELECT * FROM hts_codes WHERE hts_code LIKE ? ORDER BY hts_code LIMIT 100",
                (f"{hts_code}%",),
            ).fetchall()

        if not results:
            raise HTTPException(status_code=404, detail=f"No HTS code found for '{hts_code}'")

    return {
        "code": hts_code,
        "count": len(results),
        "results": rows_to_dicts(results),
    }


@app.get("/api/health")
async def health():
    """Health check — also shows when data was last imported."""
    with get_db() as conn:
        meta = conn.execute("SELECT * FROM import_meta WHERE id = 1").fetchone()
        total = conn.execute("SELECT COUNT(*) as n FROM hts_codes").fetchone()

    return {
        "status": "ok",
        "total_codes": total["n"] if total else 0,
        "imported_at": meta["imported_at"] if meta else None,
        "chapters_imported": meta["chapters"] if meta else 0,
    }