"""
HTS Code Lookup API — with Authentication
==========================================
Run with:  uvicorn main:app --reload

Endpoints:
    GET  /                          → frontend (SPA)
    POST /api/register              → create account
    POST /api/login                 → sign in, returns JWT cookie
    POST /api/logout                → clear auth cookie
    GET  /api/me                    → current user info
    GET  /api/search?q=...          → HTS full-text search
    GET  /api/semantic-search?q=... → semantic search with confidence scores
    GET  /api/lookup/{code}         → exact HTS code lookup
    GET  /api/products              → user's saved products
    POST /api/products              → save a product
    DELETE /api/products/{id}       → delete a saved product
    GET  /api/health                → health check
"""

import sqlite3
import os
import time
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from fastapi import FastAPI, Query, HTTPException, Request, Response, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jose import jwt, JWTError
import bcrypt
from pydantic import BaseModel

# ── Config ───────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "hts.db"
STATIC_DIR = BASE_DIR / "static"

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

app = FastAPI(title="HTS Code Lookup", version="0.2.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── Semantic search (loaded once at startup in a background thread) ────────

_sem_model      = None   # SentenceTransformer instance
_sem_embeddings = None   # float32 ndarray, shape (N, 384), pre-normalized
_sem_ids        = None   # list[int] — hts_codes.id for each row
_sem_ready      = False
_sem_lock       = threading.Lock()


def _load_semantic_index():
    global _sem_model, _sem_embeddings, _sem_ids, _sem_ready
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("[semantic] sentence-transformers not installed — semantic search disabled")
        return

    if not DB_PATH.exists():
        print("[semantic] DB not found — skipping")
        return

    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT e.hts_id, e.embedding FROM hts_embeddings e ORDER BY e.hts_id"
    ).fetchall()
    conn.close()

    if not rows:
        print("[semantic] No embeddings found — run scripts/embed_hts.py first")
        return

    ids   = [r[0] for r in rows]
    vecs  = np.frombuffer(b"".join(r[1] for r in rows), dtype=np.float32).reshape(len(rows), -1)

    print(f"[semantic] Loading model...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    with _sem_lock:
        _sem_model      = model
        _sem_embeddings = vecs
        _sem_ids        = ids
        _sem_ready      = True

    print(f"[semantic] Ready — {len(ids)} vectors loaded")


# Load in background so the server starts instantly
threading.Thread(target=_load_semantic_index, daemon=True).start()

# ── Models ───────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class SaveProductRequest(BaseModel):
    name: str
    hts_code: str
    description: str
    duty_rate: str
    origin: str = ""

# ── Database ─────────────────────────────────────────────────────────────

USER_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    email      TEXT NOT NULL UNIQUE,
    password   TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS saved_products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    name        TEXT NOT NULL,
    hts_code    TEXT NOT NULL,
    description TEXT,
    duty_rate   TEXT,
    origin      TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""

def init_user_tables():
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(USER_SCHEMA)
    conn.commit()
    conn.close()

init_user_tables()

@contextmanager
def get_db():
    if not DB_PATH.exists():
        raise HTTPException(503, "Database not found. Run: python scripts/import_hts.py")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def rows_to_dicts(rows) -> list[dict]:
    return [dict(row) for row in rows]

# ── Auth helpers ─────────────────────────────────────────────────────────

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
        user = conn.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        raise HTTPException(401, "User not found")
    return dict(user)

# ── Auth routes ──────────────────────────────────────────────────────────

@app.post("/api/register")
async def register(body: RegisterRequest, response: Response):
    if len(body.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")

    hashed = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()

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
    return {"ok": True, "user": {"id": user_id, "name": body.name, "email": body.email}}

@app.post("/api/login")
async def login(body: LoginRequest, response: Response):
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (body.email.strip().lower(),)).fetchone()

    if not user or not bcrypt.checkpw(body.password.encode(), user["password"].encode()):
        raise HTTPException(401, "Invalid email or password")

    token = create_token(user["id"], user["email"])
    response.set_cookie("token", token, httponly=True, samesite="lax", max_age=TOKEN_EXPIRE_HOURS * 3600)
    return {"ok": True, "user": {"id": user["id"], "name": user["name"], "email": user["email"]}}

@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie("token")
    return {"ok": True}

@app.get("/api/me")
async def me(request: Request):
    return get_current_user(request)

# ── Saved products ───────────────────────────────────────────────────────

@app.get("/api/products")
async def get_products(request: Request):
    user = get_current_user(request)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM saved_products WHERE user_id = ? ORDER BY created_at DESC", (user["id"],)
        ).fetchall()
    return {"products": rows_to_dicts(rows)}

@app.post("/api/products")
async def save_product(body: SaveProductRequest, request: Request):
    user = get_current_user(request)
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO saved_products (user_id, name, hts_code, description, duty_rate, origin) VALUES (?, ?, ?, ?, ?, ?)",
            (user["id"], body.name, body.hts_code, body.description, body.duty_rate, body.origin),
        )
        conn.commit()
        product_id = cursor.lastrowid
    return {"ok": True, "id": product_id}

@app.delete("/api/products/{product_id}")
async def delete_product(product_id: int, request: Request):
    user = get_current_user(request)
    with get_db() as conn:
        conn.execute("DELETE FROM saved_products WHERE id = ? AND user_id = ?", (product_id, user["id"]))
        conn.commit()
    return {"ok": True}

# ── HTS search ──────────────────────────────────────────────────────────

@app.get("/api/search")
async def search(
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
                """SELECT hts_code, description, unit, general, special, other, chapter, indent
                   FROM hts_codes WHERE description LIKE ? ORDER BY hts_code LIMIT ?""",
                (f"%{q}%", limit),
            ).fetchall()
    return {"query": q, "count": len(results), "results": rows_to_dicts(results)}

@app.get("/api/lookup/{hts_code}")
async def lookup(hts_code: str):
    with get_db() as conn:
        results = conn.execute("SELECT * FROM hts_codes WHERE hts_code = ?", (hts_code,)).fetchall()
        if not results:
            results = conn.execute(
                "SELECT * FROM hts_codes WHERE hts_code LIKE ? ORDER BY hts_code LIMIT 100",
                (f"{hts_code}%",),
            ).fetchall()
        if not results:
            raise HTTPException(404, f"No HTS code found for '{hts_code}'")
    return {"code": hts_code, "count": len(results), "results": rows_to_dicts(results)}

@app.get("/api/health")
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
    }

# ── Semantic search ──────────────────────────────────────────────────────

@app.get("/api/semantic-search")
async def semantic_search(
    q:     str = Query(..., min_length=1, max_length=400),
    limit: int = Query(10, ge=1, le=50),
):
    if not _sem_ready:
        raise HTTPException(503, "Semantic search is still loading — try again in a few seconds")

    with _sem_lock:
        model      = _sem_model
        embeddings = _sem_embeddings
        ids        = _sem_ids

    # Encode query (normalize so dot product == cosine similarity)
    q_vec = model.encode(q, normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)

    # Dot product against all pre-normalized vectors — shape (N,)
    scores = embeddings @ q_vec

    # Take top-limit indices sorted descending
    top_idx = np.argpartition(scores, -limit)[-limit:]
    top_idx = top_idx[np.argsort(scores[top_idx])[::-1]]

    top_ids    = [ids[i] for i in top_idx]
    top_scores = [float(scores[i]) for i in top_idx]

    if not top_ids:
        return {"query": q, "count": 0, "results": []}

    placeholders = ",".join("?" * len(top_ids))
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM hts_codes WHERE id IN ({placeholders})", top_ids
        ).fetchall()

    # Build a score lookup and reorder rows to match ranking
    score_by_id = {top_ids[i]: top_scores[i] for i in range(len(top_ids))}
    row_by_id   = {dict(r)["id"]: dict(r) for r in rows}
    results     = []
    for hts_id in top_ids:
        if hts_id not in row_by_id:
            continue
        entry = row_by_id[hts_id]
        entry["confidence"] = round(score_by_id[hts_id] * 100, 1)
        results.append(entry)

    return {"query": q, "count": len(results), "results": results}


# ── Frontend ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse((STATIC_DIR / "index.html").read_text())
