"""
Atlas Global — HTS Classification & Duty Estimation Platform
=============================================================
Run with:  uvicorn main:app --reload

Routes:
  GET  /          → Landing page
  GET  /app       → Application (SPA)
  API  /api/*     → JSON endpoints
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import STATIC_DIR, LANDING_PAGE
from app.database import init_tables
from app.routes.auth_routes import router as auth_router
from app.routes.product_routes import router as product_router
from app.routes.search_routes import router as search_router
from app.routes.health_routes import router as health_router

app = FastAPI(title="Atlas Global", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

init_tables()

app.include_router(auth_router)
app.include_router(product_router)
app.include_router(search_router)
app.include_router(health_router)


@app.get("/", response_class=HTMLResponse)
async def landing():
    return HTMLResponse(LANDING_PAGE.read_text())


@app.get("/app", response_class=HTMLResponse)
async def application():
    return HTMLResponse((STATIC_DIR / "index.html").read_text())
