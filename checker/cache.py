"""Cache-Verwaltung für bekannte Spiele."""

import json
from datetime import datetime

from checker.config import SCRIPT_DIR, TZ_VIENNA

CACHE_FILE = SCRIPT_DIR / "bekannte_spiele.json"


def load_cache():
    """Lädt bekannte Spiele aus der JSON-Datei."""
    if not CACHE_FILE.exists():
        return {"spiele": []}

    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {"spiele": data.get("spiele", [])}


def save_cache(cache_data):
    """Speichert bekannte Spiele in die JSON-Datei."""
    cache_data["letzte_aktualisierung"] = datetime.now(TZ_VIENNA).isoformat()
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)
