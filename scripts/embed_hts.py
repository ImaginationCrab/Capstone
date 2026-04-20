"""
HTS Embedding Builder
=====================
One-time script that encodes every HTS description into a 384-dim vector
using all-MiniLM-L6-v2 and stores the result in hts.db.

Run after importing HTS data:
    python scripts/embed_hts.py

Re-run any time you re-import HTS data to keep embeddings in sync.
"""

import sqlite3
import sys
from pathlib import Path

import numpy as np

DB_PATH = Path(__file__).resolve().parent.parent / "hts.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS hts_embeddings (
    hts_id    INTEGER PRIMARY KEY REFERENCES hts_codes(id),
    embedding BLOB NOT NULL
);
"""


def main():
    if not DB_PATH.exists():
        print("hts.db not found. Run scripts/import_hts.py first.")
        sys.exit(1)

    # Import here so the script fails fast if not installed
    from sentence_transformers import SentenceTransformer

    print("Loading model (downloads ~90 MB on first run)...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA)

    rows = conn.execute(
        "SELECT id, hts_code, description FROM hts_codes ORDER BY id"
    ).fetchall()

    if not rows:
        print("No HTS codes found in database.")
        conn.close()
        sys.exit(1)

    print(f"Encoding {len(rows)} HTS descriptions...")

    ids = [r[0] for r in rows]
    texts = [f"{r[1]} {r[2]}" for r in rows]  # code + description for richer signal

    # batch_size=256 is fast on CPU; show_progress_bar prints a tqdm bar
    embeddings = model.encode(
        texts,
        batch_size=256,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,  # pre-normalize so dot product == cosine similarity
    )

    print("Writing embeddings to database...")
    conn.execute("DELETE FROM hts_embeddings")
    conn.executemany(
        "INSERT INTO hts_embeddings (hts_id, embedding) VALUES (?, ?)",
        [(int(ids[i]), embeddings[i].astype(np.float32).tobytes()) for i in range(len(ids))],
    )
    conn.commit()
    conn.close()

    print(f"\nDone — {len(ids)} embeddings stored in {DB_PATH}")
    print("Restart the server to load the new embeddings.")


if __name__ == "__main__":
    main()
