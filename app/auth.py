from datetime import datetime, timedelta, timezone
from fastapi import Request, HTTPException
from jose import jwt, JWTError
import bcrypt
from .config import SECRET_KEY, ALGORITHM, TOKEN_EXPIRE_HOURS
from .database import get_db


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: int, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": str(user_id), "email": email, "exp": expire}, SECRET_KEY, ALGORITHM)


def get_current_user(request: Request) -> dict:
    token = request.cookies.get("token")
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(401, "Invalid token")
    with get_db() as conn:
        user = conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if not user:
        raise HTTPException(401, "User not found")
    return dict(user)


def try_get_current_user(request: Request) -> dict | None:
    """Returns the current user or None (no exception)."""
    try:
        return get_current_user(request)
    except HTTPException:
        return None
