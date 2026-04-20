from fastapi import APIRouter, Request
from ..models import SaveProductRequest
from ..database import get_db, rows_to_dicts
from ..auth import get_current_user

router = APIRouter(prefix="/api", tags=["products"])


@router.get("/products")
async def get_products(request: Request):
    user = get_current_user(request)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM saved_products WHERE user_id = ? ORDER BY created_at DESC",
            (user["id"],),
        ).fetchall()
    return {"products": rows_to_dicts(rows)}


@router.post("/products")
async def save_product(body: SaveProductRequest, request: Request):
    user = get_current_user(request)
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO saved_products (user_id, name, hts_code, description, duty_rate, origin) VALUES (?, ?, ?, ?, ?, ?)",
            (user["id"], body.name, body.hts_code, body.description, body.duty_rate, body.origin),
        )
        conn.commit()
    return {"ok": True, "id": cursor.lastrowid}


@router.delete("/products/{product_id}")
async def delete_product(product_id: int, request: Request):
    user = get_current_user(request)
    with get_db() as conn:
        conn.execute(
            "DELETE FROM saved_products WHERE id = ? AND user_id = ?",
            (product_id, user["id"]),
        )
        conn.commit()
    return {"ok": True}
