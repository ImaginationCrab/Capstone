import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "hts.db"
STATIC_DIR = BASE_DIR / "static"
LANDING_PAGE = STATIC_DIR / "landing.html"

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24
