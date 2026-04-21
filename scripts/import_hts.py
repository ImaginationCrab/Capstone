"""
HTS Data Importer
=================
Downloads the HTS schedule from the USITC REST API and imports it into
SQLite with full-text search (FTS5).

Data source: USITC HTS REST API
    Export:  https://hts.usitc.gov/reststop/exportList?from=XXXX&to=XXXX&format=JSON
    Search:  https://hts.usitc.gov/reststop/search?keyword=XXXX

The exportList endpoint returns JSON for a range of HTS codes.  We pull
the full schedule by iterating through chapter ranges (01-99), normalize
the data, and insert it into two tables:

    hts_codes   – the raw structured data
    hts_search  – an FTS5 virtual table for fast text search

Usage:
    python scripts/import_hts.py          # full import (chapters 1-99)
    python scripts/import_hts.py --test   # import only chapter 1 for quick testing
"""

import argparse
import json
import sqlite3
import sys
import urllib.request
import urllib.error
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "hts.db"
EXPORT_URL = "https://hts.usitc.gov/reststop/exportList"

# ── Schema ───────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS hts_codes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hts_code    TEXT NOT NULL,
    indent      INTEGER DEFAULT 0,
    description TEXT NOT NULL,
    unit        TEXT,
    general     TEXT,          -- general duty rate
    special     TEXT,          -- special duty rate
    other       TEXT,          -- "column 2" duty rate
    chapter     INTEGER,
    UNIQUE(hts_code, description)
);

CREATE INDEX IF NOT EXISTS idx_hts_code ON hts_codes(hts_code);

-- FTS5 virtual table for fast full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS hts_search USING fts5(
    hts_code,
    description,
    content='hts_codes',
    content_rowid='id',
    tokenize='porter unicode61'
);

-- Triggers to keep FTS in sync when the main table changes
CREATE TRIGGER IF NOT EXISTS hts_ai AFTER INSERT ON hts_codes BEGIN
    INSERT INTO hts_search(rowid, hts_code, description)
    VALUES (new.id, new.hts_code, new.description);
END;

CREATE TRIGGER IF NOT EXISTS hts_ad AFTER DELETE ON hts_codes BEGIN
    INSERT INTO hts_search(hts_search, rowid, hts_code, description)
    VALUES ('delete', old.id, old.hts_code, old.description);
END;

CREATE TRIGGER IF NOT EXISTS hts_au AFTER UPDATE ON hts_codes BEGIN
    INSERT INTO hts_search(hts_search, rowid, hts_code, description)
    VALUES ('delete', old.id, old.hts_code, old.description);
    INSERT INTO hts_search(rowid, hts_code, description)
    VALUES (new.id, new.hts_code, new.description);
END;

-- Track when the data was last imported
CREATE TABLE IF NOT EXISTS import_meta (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    imported_at TEXT NOT NULL,
    chapters    INTEGER NOT NULL
);
"""


def init_db(db_path: Path) -> sqlite3.Connection:
    """Create the database and tables if they don't exist."""
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def fetch_chapter(chapter: int) -> list[dict]:
    """
    Fetch a single chapter's HTS data using the exportList endpoint.

    Each chapter maps to a range: chapter 1 -> from=0100, to=0200
    Chapter 99 -> from=9900, to=9999
    """
    from_code = f"{chapter:02d}00"
    to_code = f"{chapter:02d}99"

    url = f"{EXPORT_URL}?from={from_code}&to={to_code}&format=JSON&styles=false"

    try:
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "HTS-Lookup-Importer/1.0",
        })
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            data = json.loads(raw)

            if isinstance(data, list):
                return data
            # If wrapped in an object, try common keys
            if isinstance(data, dict):
                for key in ("data", "results", "lines", "items"):
                    if key in data and isinstance(data[key], list):
                        return data[key]
                return []
            return []

    except urllib.error.HTTPError as e:
        print(f"  [!] Chapter {chapter:02d}: HTTP {e.code} — skipping")
        return []
    except json.JSONDecodeError as e:
        print(f"  [!] Chapter {chapter:02d}: Invalid JSON — skipping ({e})")
        return []
    except Exception as e:
        print(f"  [!] Chapter {chapter:02d}: {e} — skipping")
        return []


def parse_row(row: dict, chapter: int) -> dict | None:
    """
    Normalize a single API row into our schema.

    Actual USITC API fields (confirmed from live response):
        htsno       - e.g. "2603.00.00" or "2603.00.00.10"
        description - e.g. "Copper ores and concentrates"
        indent      - string "0", "1", "2", etc.
        units       - array like ["Cu kg"] or null
        general     - e.g. "1.7¢/kg on lead content" or "Free"
        special     - e.g. "Free (A,AU,BH,...)" or ""
        other       - e.g. "8.8¢/kg on copper content..."
    """
    hts = (row.get("htsno") or "").strip()
    desc = (row.get("description") or "").strip()

    if not desc:
        return None

    # `units` comes as an array — join into a string
    units_raw = row.get("units")
    if isinstance(units_raw, list):
        unit = ", ".join(str(u) for u in units_raw if u)
    else:
        unit = str(units_raw) if units_raw else ""

    # `indent` comes as a string from the API
    try:
        indent = int(row.get("indent", 0) or 0)
    except (ValueError, TypeError):
        indent = 0

    return {
        "hts_code": hts,
        "indent": indent,
        "description": desc,
        "unit": unit,
        "general": (row.get("general") or "").strip(),
        "special": (row.get("special") or "").strip(),
        "other": (row.get("other") or "").strip(),
        "chapter": chapter,
    }


def import_data(db_path: Path, chapters: range) -> None:
    """Main import routine."""
    conn = init_db(db_path)
    cursor = conn.cursor()

    # Clear existing data for a clean import
    cursor.execute("DELETE FROM hts_codes")
    cursor.execute("INSERT INTO hts_search(hts_search) VALUES('rebuild')")

    total = 0

    for ch in chapters:
        print(f"  Fetching chapter {ch:02d} ... ", end="", flush=True)
        rows = fetch_chapter(ch)

        if not rows:
            print("0 rows (empty or error)")
            continue

        count = 0
        for row in rows:
            parsed = parse_row(row, ch)
            if parsed:
                try:
                    cursor.execute(
                        """INSERT OR IGNORE INTO hts_codes
                           (hts_code, indent, description, unit, general, special, other, chapter)
                           VALUES (:hts_code, :indent, :description, :unit, :general, :special, :other, :chapter)""",
                        parsed,
                    )
                    count += cursor.rowcount
                except sqlite3.Error as e:
                    print(f"\n    DB error: {e}")

        total += count
        print(f"{count} rows (from {len(rows)} records)")

        # Be polite to the API
        time.sleep(0.5)

    # Record import metadata
    cursor.execute(
        """INSERT OR REPLACE INTO import_meta (id, imported_at, chapters)
           VALUES (1, datetime('now'), ?)""",
        (len(list(chapters)),),
    )

    conn.commit()
    conn.close()

    print(f"\nDone — imported {total} total rows into {db_path}")


# ── CLI ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import HTS data from USITC")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Import only chapter 1 (for quick testing)",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=str(DB_PATH),
        help=f"Path to SQLite database (default: {DB_PATH})",
    )
    args = parser.parse_args()

    db = Path(args.db)
    chapters = range(1, 2) if args.test else range(1, 100)

    print(f"Importing HTS data → {db}")
    print(f"Chapters: {chapters.start}–{chapters.stop - 1}")
    print(f"API: {EXPORT_URL}\n")

    import_data(db, chapters)