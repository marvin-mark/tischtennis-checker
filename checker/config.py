"""Konfiguration & Konstanten."""

import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

# Pfade (parent.parent weil diese Datei in checker/ liegt)
SCRIPT_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = SCRIPT_DIR / "config.json"

# URL
BASE_URL = "https://oettv.xttv.at/ed/index.php"

# Timezone
TZ_VIENNA = ZoneInfo("Europe/Vienna")


def load_config():
    """
    Lädt die Konfiguration.
    Priorität: Umgebungsvariablen > config.json
    """
    # Versuche zuerst Umgebungsvariablen (für GitHub Actions)
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if bot_token and chat_id:
        print("Konfiguration aus Umgebungsvariablen geladen.")
        return {"bot_token": bot_token, "chat_id": chat_id}

    # Fallback: config.json (für lokale Ausführung)
    if not CONFIG_FILE.exists():
        print(f"Fehler: Weder Umgebungsvariablen noch {CONFIG_FILE} gefunden!")
        print("Setze TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID oder erstelle config.json")
        sys.exit(1)

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    if not config.get("bot_token") or config.get("bot_token") == "DEIN_BOT_TOKEN_HIER":
        print("Fehler: bot_token muss in config.json gesetzt sein!")
        sys.exit(1)

    if not config.get("chat_id") or config.get("chat_id") == "DEINE_CHAT_ID_HIER":
        print("Fehler: chat_id muss in config.json gesetzt sein!")
        sys.exit(1)

    print("Konfiguration aus config.json geladen.")
    return config
