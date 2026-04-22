# HTS Code Lookup — MVP

A minimal web app for searching the U.S. Harmonized Tariff Schedule.

## Stack

- **FastAPI** — one-file backend
- **SQLite + FTS5** — database with full-text search, zero infrastructure
- **Vanilla HTML/JS** — no build step, no framework

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Import HTS data (test with just chapter 1 first)
python scripts/import_hts.py --test

# 3. Run the server
uvicorn main:app --reload

# 4. Open http://localhost:8000
```

To import the full dataset (all 99 chapters):

```bash
python scripts/import_hts.py
```

This takes a few minutes — it pulls each chapter from the USITC API sequentially.

## Project Structure

```
hts-lookup/
├── main.py                 ← entire backend (FastAPI app)
├── hts.db                  ← SQLite database (created by import)
├── requirements.txt
├── scripts/
│   └── import_hts.py       ← data importer
└── static/
    └── index.html          ← entire frontend
```

## API Endpoints

| Endpoint               | Description                              |
|------------------------|------------------------------------------|
| `GET /`                | Serves the frontend                      |
| `GET /api/search?q=..` | Full-text search on item descriptions    |
| `GET /api/lookup/0101` | Exact or prefix lookup by HTS code       |
| `GET /api/health`      | Health check + import metadata           |

## Periodic Sync

The USITC updates the HTS a few times per year. To refresh your data,
just re-run the import script — it clears and rebuilds from scratch:

```bash
python scripts/import_hts.py
```

For automated sync, set up a cron job:

```cron
# Re-import HTS data every Sunday at 3 AM
0 3 * * 0 cd /path/to/hts-lookup && python scripts/import_hts.py >> /var/log/hts-import.log 2>&1
```

## Deployment

For a quick deploy, this runs well on Railway, Render, or Fly.io.
The SQLite file lives alongside the app — no external database needed.

Example `Procfile` (for Render/Railway):

```
web: uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
```
