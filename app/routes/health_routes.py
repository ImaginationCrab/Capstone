from fastapi import APIRouter
from ..database import get_db
from ..config import OPENAI_API_KEY

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health():
    with get_db() as conn:
        meta = conn.execute("SELECT * FROM import_meta WHERE id = 1").fetchone()
        total = conn.execute("SELECT COUNT(*) as n FROM hts_codes").fetchone()
        users = conn.execute("SELECT COUNT(*) as n FROM users").fetchone()
    return {
        "status": "ok",
        "total_codes": total["n"] if total else 0,
        "total_users": users["n"] if users else 0,
        "imported_at": meta["imported_at"] if meta else None,
        "ai_search": bool(OPENAI_API_KEY),
    }
