#!/usr/bin/env python3
"""
Tischtennis-Spiele Checker
Prüft auf neue eingetragene Spielergebnisse und sendet Telegram-Benachrichtigungen.
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# Pfade
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
CACHE_FILE = SCRIPT_DIR / "bekannte_spiele.json"

# URL
BASE_URL = "https://oettv.xttv.at/ed/index.php"


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


def load_cache():
    """Lädt bekannte Spiele aus dem Cache."""
    if not CACHE_FILE.exists():
        return set()

    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    return set(data.get("spiele", []))


def save_cache(spiele):
    """Speichert bekannte Spiele im Cache."""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "spiele": list(spiele),
            "letzte_aktualisierung": datetime.now().isoformat()
        }, f, ensure_ascii=False, indent=2)


def parse_einzelspiele(gamedetail_text):
    """
    Parst die Einzelspiele aus dem gamedetail Text.
    Format: Spieler1|Spieler2|3:0 oder Spieler1|/|Spieler2|Spieler3|/|Spieler4|3:1
    """
    if not gamedetail_text or "Spiel noch nicht eingegeben" in gamedetail_text:
        return []

    einzelspiele = []
    parts = [p.strip() for p in gamedetail_text.split("|")]

    i = 0
    while i < len(parts):
        # Suche nach Ergebnis-Pattern (X:Y)
        if re.match(r'^\d:\d$', parts[i]):
            ergebnis = parts[i]

            # Schaue zurück um Spieler zu finden
            if i >= 2:
                # Prüfe ob Doppel (hat "/" davor)
                if i >= 6 and parts[i-5] == "/" and parts[i-2] == "/":
                    # Doppel: Spieler1 / Spieler2 vs Spieler3 / Spieler4
                    spieler1 = parts[i-6]
                    spieler2 = parts[i-4]
                    spieler3 = parts[i-3]
                    spieler4 = parts[i-1]
                    einzelspiele.append({
                        "typ": "Doppel",
                        "heim": f"{spieler1} / {spieler2}",
                        "gast": f"{spieler3} / {spieler4}",
                        "ergebnis": ergebnis
                    })
                else:
                    # Einzel: Spieler1 vs Spieler2
                    spieler1 = parts[i-2]
                    spieler2 = parts[i-1]

                    # Überspringe wenn einer der "Spieler" ein "/" oder "w.o." ist
                    if spieler1 not in ["/", ""] and spieler2 not in ["/", ""]:
                        # Überspringe auch Nicht-Namen (z.B. "Spielbericht anzeigen")
                        if not any(x in spieler1.lower() for x in ["spielbericht", "bestätigt", "anzeigen"]):
                            einzelspiele.append({
                                "typ": "Einzel",
                                "heim": spieler1,
                                "gast": spieler2,
                                "ergebnis": ergebnis
                            })
            i += 1
        else:
            i += 1

    return einzelspiele


def parse_spielplan_page(html_content):
    """
    Parst die Spielplan-Seite und extrahiert Spiele.
    Die Seite verwendet <li class="gameSummary"> Elemente.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    spiele = []
    today = datetime.now().date()

    # Suche nach allen gameSummary Einträgen
    game_entries = soup.find_all("li", class_="gameSummary")

    for entry in game_entries:
        text = entry.get_text(separator=" ", strip=True)

        # Extrahiere Datum (Format: "Di. 27.01.2026" oder ähnlich)
        datum_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', text)
        if not datum_match:
            continue
        datum_str = datum_match.group(1)

        # Datum parsen und prüfen ob in Vergangenheit oder heute
        try:
            spiel_datum = datetime.strptime(datum_str, "%d.%m.%Y").date()
        except ValueError:
            continue

        # Nur Spiele die bereits stattgefunden haben (Datum <= heute)
        if spiel_datum > today:
            continue

        # Extrahiere Uhrzeit
        zeit_match = re.search(r'(\d{2}:\d{2})', text)
        zeit = zeit_match.group(1) if zeit_match else ""

        # Extrahiere Mannschaften und Ergebnis (Format: "HALT1 - INZI1 6:2")
        match = re.search(r'([A-ZÄÖÜ]{2,6}\d+)\s*-\s*([A-ZÄÖÜ]{2,6}\d+)\s+(\d+):(\d+)', text)
        if not match:
            # Kein Ergebnis eingetragen - überspringen!
            continue
        heim = match.group(1)
        gast = match.group(2)
        ergebnis = f"{match.group(3)}:{match.group(4)}"

        # Extrahiere Einzelspiele aus gamedetail
        gamedetail = entry.find(class_="gamedetail")
        einzelspiele = []
        if gamedetail:
            gamedetail_text = gamedetail.get_text(separator="|", strip=True)
            einzelspiele = parse_einzelspiele(gamedetail_text)

        # Erstelle eindeutige ID (inkl. Ergebnis, damit Änderungen erkannt werden)
        spiel_id = f"{datum_str}_{heim}_vs_{gast}_{ergebnis}"

        spiele.append({
            "id": spiel_id,
            "datum": datum_str,
            "zeit": zeit,
            "heim": heim,
            "gast": gast,
            "ergebnis": ergebnis,
            "einzelspiele": einzelspiele
        })

    return spiele


def filter_spiele(spiele):
    """Filtert Spiele die 'SIIM2' enthalten heraus."""
    return [s for s in spiele if "SIIM2" not in s.get("heim", "") and "SIIM2" not in s.get("gast", "")]


def send_telegram_message(config, message):
    """Sendet eine Nachricht via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{config['bot_token']}/sendMessage"
    payload = {
        "chat_id": config["chat_id"],
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Fehler beim Senden der Telegram-Nachricht: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return False


def format_spiel_nachricht(spiel):
    """Formatiert ein Spiel als Telegram-Nachricht."""
    datum = spiel.get("datum", "Unbekannt")
    zeit = spiel.get("zeit", "")
    heim = spiel.get("heim", "?")
    gast = spiel.get("gast", "?")
    ergebnis = spiel.get("ergebnis", "?")
    einzelspiele = spiel.get("einzelspiele", [])

    datum_zeit = f"{datum} {zeit}".strip() if zeit else datum

    # Basis-Nachricht
    msg = f"""🏓 <b>Neues Spiel eingetragen!</b>

📅 {datum_zeit}
⚔️ <b>{heim}</b> <b>{ergebnis}</b> <b>{gast}</b>
"""

    # Einzelspiele hinzufügen
    if einzelspiele:
        msg += "\n<b>Details:</b>\n"
        for es in einzelspiele:
            typ_icon = "👥" if es["typ"] == "Doppel" else "👤"
            msg += f"{typ_icon} {es['heim']} <b>{es['ergebnis']}</b> {es['gast']}\n"

    return msg


def main():
    """Hauptfunktion."""
    print(f"Tischtennis-Checker gestartet: {datetime.now().isoformat()}")

    # Konfiguration laden
    config = load_config()

    # Cache laden
    bekannte_spiele = load_cache()
    print(f"Bekannte Spiele im Cache: {len(bekannte_spiele)}")

    # Spiele von Webseite abrufen (ohne Datumsfilter um alle Spiele zu sehen)
    url = f"{BASE_URL}?lid=8615&do=spiele"
    print(f"Rufe URL ab: {url}")

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Fehler beim Abrufen: {e}")
        sys.exit(1)

    # Spiele parsen (nur vergangene mit eingetragenem Ergebnis)
    alle_spiele = parse_spielplan_page(response.text)
    print(f"Spiele mit Ergebnis (Datum <= heute): {len(alle_spiele)}")

    # SIIM2 herausfiltern
    gefilterte_spiele = filter_spiele(alle_spiele)
    print(f"Nach Filter (ohne SIIM2): {len(gefilterte_spiele)}")

    # Neue Spiele finden
    neue_spiele = []
    for spiel in gefilterte_spiele:
        spiel_id = spiel.get("id", "")
        if spiel_id and spiel_id not in bekannte_spiele:
            neue_spiele.append(spiel)
            bekannte_spiele.add(spiel_id)

    print(f"Neue Ergebnisse: {len(neue_spiele)}")

    # Benachrichtigungen senden
    for spiel in neue_spiele:
        nachricht = format_spiel_nachricht(spiel)
        print(f"Sende Benachrichtigung: {spiel.get('heim')} vs {spiel.get('gast')} [{spiel.get('ergebnis')}]")
        if send_telegram_message(config, nachricht):
            print("  -> Erfolgreich gesendet!")
        else:
            print("  -> Fehler beim Senden!")

    # Cache speichern
    save_cache(bekannte_spiele)
    print(f"Cache aktualisiert: {len(bekannte_spiele)} Spiele")

    if not neue_spiele:
        print("Keine neuen Ergebnisse gefunden.")

    print(f"Fertig: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
