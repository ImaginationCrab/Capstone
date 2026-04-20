# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Import HTS data (chapter 1 only, for quick testing)
python scripts/import_hts.py --test

# Import full dataset (chapters 1–99, takes several minutes)
python scripts/import_hts.py

# Run the dev server
uvicorn main:app --reload
```

The app is then available at http://localhost:8000.

## Architecture

This is a single-file FastAPI backend (`main.py`) with a single-file vanilla JS frontend (`static/index.html`) and a SQLite database (`hts.db`).

**Database schema (`hts.db`):**
- `hts_codes` — structured HTS tariff data (code, description, duty rates, indent level)
- `hts_search` — FTS5 virtual table backed by `hts_codes`, kept in sync via triggers; uses porter stemmer tokenizer
- `users` — accounts with bcrypt-hashed passwords
- `saved_products` — per-user saved HTS codes with origin country
- `import_meta` — single-row table tracking last import timestamp

**Authentication:** JWT stored in an `httponly` cookie (`token`). `get_current_user()` in `main.py` is the auth dependency — pass `request: Request` and call it directly (not as a FastAPI `Depends`).

**Search:** `/api/search` uses FTS5 with prefix matching on the last term (`term*`). Falls back to a `LIKE` query if FTS fails (e.g., FTS table not yet built).

**Data import:** `scripts/import_hts.py` pulls from the USITC REST API (`hts.usitc.gov`), clears existing data, and rebuilds from scratch. Re-run to refresh data after USITC updates.

## Environment

- `SECRET_KEY` — JWT signing key (defaults to `dev-secret-change-in-production`)
