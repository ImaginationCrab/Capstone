import sqlite3
from fastapi import APIRouter, Request, Response, HTTPException
from ..models import (
    RegisterRequest,
    LoginRequest,
    UpdateProfileRequest,
    ChangePasswordRequest,
    DeleteAccountRequest,
)
from ..database import get_db
from ..auth import hash_password, verify_password, create_token, get_current_user
from ..config import TOKEN_EXPIRE_HOURS

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/register")
async def register(body: RegisterRequest, response: Response):
    if len(body.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    hashed = hash_password(body.password)
    with get_db() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                (body.name.strip(), body.email.strip().lower(), hashed),
            )
            conn.commit()
            user_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Email already registered")
    token = create_token(user_id, body.email)
    response.set_cookie("token", token, httponly=True, samesite="lax", max_age=TOKEN_EXPIRE_HOURS * 3600)
    return {"ok": True, "user": {"id": user_id, "name": body.name.strip(), "email": body.email.strip().lower()}}


@router.post("/login")
async def login(body: LoginRequest, response: Response):
    with get_db() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (body.email.strip().lower(),)
        ).fetchone()
    if not user or not verify_password(body.password, user["password"]):
        raise HTTPException(401, "Invalid email or password")
    token = create_token(user["id"], user["email"])
    response.set_cookie("token", token, httponly=True, samesite="lax", max_age=TOKEN_EXPIRE_HOURS * 3600)
    return {"ok": True, "user": {"id": user["id"], "name": user["name"], "email": user["email"]}}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("token")
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    user = get_current_user(request)
    with get_db() as conn:
        products_count = conn.execute(
            "SELECT COUNT(*) as n FROM saved_products WHERE user_id = ?", (user["id"],)
        ).fetchone()["n"]
        searches_count = conn.execute(
            "SELECT COUNT(*) as n FROM search_history WHERE user_id = ?", (user["id"],)
        ).fetchone()["n"]
    return {**user, "products_count": products_count, "searches_count": searches_count}


@router.patch("/me")
async def update_profile(body: UpdateProfileRequest, request: Request):
    user = get_current_user(request)
    if not body.name.strip():
        raise HTTPException(400, "Name cannot be empty")
    with get_db() as conn:
        conn.execute("UPDATE users SET name = ? WHERE id = ?", (body.name.strip(), user["id"]))
        conn.commit()
    return {"ok": True, "name": body.name.strip()}


@router.post("/me/password")
async def change_password(body: ChangePasswordRequest, request: Request):
    user = get_current_user(request)
    if len(body.new_password) < 6:
        raise HTTPException(400, "New password must be at least 6 characters")
    if body.current_password == body.new_password:
        raise HTTPException(400, "New password must be different from current password")
    with get_db() as conn:
        row = conn.execute(
            "SELECT password FROM users WHERE id = ?", (user["id"],)
        ).fetchone()
        if not row or not verify_password(body.current_password, row["password"]):
            raise HTTPException(401, "Current password is incorrect")
        conn.execute(
            "UPDATE users SET password = ? WHERE id = ?",
            (hash_password(body.new_password), user["id"]),
        )
        conn.commit()
    return {"ok": True}


@router.delete("/me")
async def delete_account(body: DeleteAccountRequest, request: Request, response: Response):
    user = get_current_user(request)
    with get_db() as conn:
        row = conn.execute(
            "SELECT password FROM users WHERE id = ?", (user["id"],)
        ).fetchone()
        if not row or not verify_password(body.current_password, row["password"]):
            raise HTTPException(401, "Current password is incorrect")
        conn.execute("DELETE FROM saved_products WHERE user_id = ?", (user["id"],))
        conn.execute("DELETE FROM search_history WHERE user_id = ?", (user["id"],))
        conn.execute("DELETE FROM users WHERE id = ?", (user["id"],))
        conn.commit()
    response.delete_cookie("token")
    return {"ok": True}
