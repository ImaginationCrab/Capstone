"""
Simple in-memory TTL cache for AI API responses.

Avoids redundant OpenAI calls for identical queries.
Entries expire after `ttl` seconds and the cache is capped at `maxsize`.
"""

import time
import hashlib
import json

_caches: dict[str, dict] = {}


def _get_store(namespace: str, maxsize: int) -> dict:
    """Get or create a cache store for a given namespace."""
    if namespace not in _caches:
        _caches[namespace] = {"maxsize": maxsize, "entries": {}}
    return _caches[namespace]


def cache_key(*args) -> str:
    """Build a deterministic key from arbitrary args."""
    raw = json.dumps(args, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def get(namespace: str, key: str, ttl: int = 3600):
    """Return cached value if it exists and hasn't expired, else None."""
    store = _caches.get(namespace)
    if not store:
        return None
    entry = store["entries"].get(key)
    if not entry:
        return None
    if time.time() - entry["ts"] > ttl:
        del store["entries"][key]
        return None
    return entry["val"]


def put(namespace: str, key: str, value, maxsize: int = 256):
    """Store a value in the cache, evicting oldest if full."""
    store = _get_store(namespace, maxsize)
    entries = store["entries"]

    # Evict oldest entries if at capacity
    while len(entries) >= store["maxsize"]:
        oldest_key = min(entries, key=lambda k: entries[k]["ts"])
        del entries[oldest_key]

    entries[key] = {"val": value, "ts": time.time()}


def stats() -> dict:
    """Return cache statistics for monitoring."""
    result = {}
    for ns, store in _caches.items():
        entries = store["entries"]
        result[ns] = {
            "size": len(entries),
            "maxsize": store["maxsize"],
        }
    return result
