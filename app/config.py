import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "hts.db"
STATIC_DIR = BASE_DIR / "static"
LANDING_PAGE = BASE_DIR / "atlas-global-landing (1).html"

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24
