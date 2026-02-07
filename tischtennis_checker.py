#!/usr/bin/env python3
"""
Tischtennis-Spiele Checker
Prüft auf neue eingetragene Spielergebnisse und sendet Telegram-Benachrichtigungen.
Enthält Smart-Checking: Checkt nur, wenn ein Ergebnis erwartet wird.
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

# Pfade
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"
CACHE_FILE = SCRIPT_DIR / "bekannte_spiele.json"

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


def load_cache():
    """Lädt Cache-Daten inkl. ausstehender Spiele. Abwärtskompatibel mit altem Format."""
    defaults = {
        "spiele": [],
        "ausstehende_spiele": [],
        "letzter_spielplan_abruf": None,
        "letzte_aktualisierung": None,
    }

    if not CACHE_FILE.exists():
        return defaults

    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Abwärtskompatibilität: alte Felder übernehmen, neue mit Defaults füllen
    result = dict(defaults)
    result["spiele"] = data.get("spiele", [])
    result["ausstehende_spiele"] = data.get("ausstehende_spiele", [])
    result["letzter_spielplan_abruf"] = data.get("letzter_spielplan_abruf", None)
    result["letzte_aktualisierung"] = data.get("letzte_aktualisierung", None)

    return result


def save_cache(cache_data):
    """Speichert das vollständige Cache-Dict."""
    cache_data["letzte_aktualisierung"] = datetime.now(TZ_VIENNA).isoformat()
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)


def berechne_erwartetes_ende(datum_str, zeit):
    """
    Berechnet, ab wann ein Ergebnis erwartet wird (Spielzeit + 2h Puffer).
    Keine Uhrzeit bekannt → Annahme 20:00.
    Gibt ISO-Timestamp mit Timezone zurück.
    """
    if not zeit:
        zeit = "20:00"

    try:
        spiel_start = datetime.strptime(f"{datum_str} {zeit}", "%d.%m.%Y %H:%M")
    except ValueError:
        # Fallback bei unerwartetem Format
        spiel_start = datetime.strptime(f"{datum_str} 20:00", "%d.%m.%Y %H:%M")

    spiel_start = spiel_start.replace(tzinfo=TZ_VIENNA)
    erwartetes_ende = spiel_start + timedelta(hours=2)
    return erwartetes_ende.isoformat()


def soll_check_durchgefuehrt_werden(cache_data):
    """
    Entscheidet, ob ein HTTP-Check nötig ist.
    Gibt (bool, grund_text) zurück.
    """
    jetzt = datetime.now(TZ_VIENNA)

    # 1. Kein vorheriger Abruf → CHECK (erster Lauf/Migration)
    letzter_abruf_str = cache_data.get("letzter_spielplan_abruf")
    if not letzter_abruf_str:
        return True, "Erster Lauf oder Migration - kein vorheriger Abruf bekannt"

    # 2. Letzter Abruf > 12h → CHECK (Spielplan-Refresh)
    try:
        letzter_abruf = datetime.fromisoformat(letzter_abruf_str)
    except (ValueError, TypeError):
        return True, "Letzter Abruf-Zeitstempel ungültig"

    if jetzt - letzter_abruf > timedelta(hours=12):
        return True, f"Spielplan-Refresh fällig (letzter Abruf: {letzter_abruf.strftime('%d.%m. %H:%M')})"

    # 3. Ausstehendes Spiel mit erwartetes_ende <= jetzt → CHECK
    ausstehende = cache_data.get("ausstehende_spiele", [])
    for spiel in ausstehende:
        ende_str = spiel.get("erwartetes_ende")
        if not ende_str:
            continue
        try:
            erwartetes_ende = datetime.fromisoformat(ende_str)
        except (ValueError, TypeError):
            continue
        if erwartetes_ende <= jetzt:
            heim = spiel.get("heim", "?")
            gast = spiel.get("gast", "?")
            return True, f"Ergebnis erwartet: {heim} vs {gast} (Ende: {erwartetes_ende.strftime('%d.%m. %H:%M')})"

    # 4. Kein Grund zu checken
    naechstes = None
    for spiel in ausstehende:
        ende_str = spiel.get("erwartetes_ende")
        if not ende_str:
            continue
        try:
            ende = datetime.fromisoformat(ende_str)
            if naechstes is None or ende < naechstes:
                naechstes = ende
        except (ValueError, TypeError):
            continue

    if naechstes:
        diff = naechstes - jetzt
        stunden = int(diff.total_seconds() // 3600)
        minuten = int((diff.total_seconds() % 3600) // 60)
        return False, f"Nächstes erwartetes Ergebnis in {stunden}h {minuten}min"

    refresh_in = timedelta(hours=12) - (jetzt - letzter_abruf)
    stunden = int(refresh_in.total_seconds() // 3600)
    minuten = int((refresh_in.total_seconds() % 3600) // 60)
    return False, f"Keine ausstehenden Spiele, nächster Refresh in {stunden}h {minuten}min"


def aktualisiere_ausstehende_spiele(cache_data, neue_ausstehende, spiele_mit_ergebnis):
    """
    Aktualisiert die Liste ausstehender Spiele im Cache.
    - Entfernt Spiele die nun ein Ergebnis haben
    - Fügt neue geplante Spiele hinzu
    - Wendet SIIM2-Filter an
    """
    # IDs der Spiele mit Ergebnis (Heim_vs_Gast_Datum)
    ergebnis_keys = set()
    for spiel in spiele_mit_ergebnis:
        key = f"{spiel['heim']}_vs_{spiel['gast']}_{spiel['datum']}"
        ergebnis_keys.add(key)

    # Bestehende ausstehende Spiele filtern (entferne die mit Ergebnis)
    bestehende = cache_data.get("ausstehende_spiele", [])
    verbleibend = [s for s in bestehende if s.get("spiel_id") not in ergebnis_keys]

    # Neue ausstehende Spiele hinzufügen (nur wenn noch nicht vorhanden)
    vorhandene_ids = {s.get("spiel_id") for s in verbleibend}
    for spiel in neue_ausstehende:
        # SIIM2-Filter
        if "SIIM2" in spiel.get("heim", "") or "SIIM2" in spiel.get("gast", ""):
            continue
        if spiel.get("spiel_id") not in vorhandene_ids:
            verbleibend.append(spiel)

    cache_data["ausstehende_spiele"] = verbleibend


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
    Gibt zwei Listen zurück: (spiele_mit_ergebnis, ausstehende_spiele)
    """
    soup = BeautifulSoup(html_content, "html.parser")
    spiele_mit_ergebnis = []
    ausstehende_spiele = []
    today = datetime.now(TZ_VIENNA).date()

    # Suche nach allen gameSummary Einträgen
    game_entries = soup.find_all("li", class_="gameSummary")

    for entry in game_entries:
        text = entry.get_text(separator=" ", strip=True)

        # Extrahiere Datum (Format: "Di. 27.01.2026" oder ähnlich)
        datum_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', text)
        if not datum_match:
            continue
        datum_str = datum_match.group(1)

        # Datum parsen
        try:
            spiel_datum = datetime.strptime(datum_str, "%d.%m.%Y").date()
        except ValueError:
            continue

        # Extrahiere Uhrzeit
        zeit_match = re.search(r'(\d{2}:\d{2})', text)
        zeit = zeit_match.group(1) if zeit_match else ""

        # Versuche Mannschaften + Ergebnis zu extrahieren (Format: "HALT1 - INZI1 6:2")
        match_ergebnis = re.search(r'([A-ZÄÖÜ]{2,6}\d+)\s*-\s*([A-ZÄÖÜ]{2,6}\d+)\s+(\d+):(\d+)', text)

        if match_ergebnis:
            # Spiel MIT Ergebnis
            if spiel_datum > today:
                continue  # Zukunftsspiel mit Ergebnis? Unwahrscheinlich, überspringen

            heim = match_ergebnis.group(1)
            gast = match_ergebnis.group(2)
            ergebnis = f"{match_ergebnis.group(3)}:{match_ergebnis.group(4)}"

            # Extrahiere Einzelspiele aus gamedetail
            gamedetail = entry.find(class_="gamedetail")
            einzelspiele = []
            if gamedetail:
                gamedetail_text = gamedetail.get_text(separator="|", strip=True)
                einzelspiele = parse_einzelspiele(gamedetail_text)

            spiel_id = f"{datum_str}_{heim}_vs_{gast}_{ergebnis}"

            spiele_mit_ergebnis.append({
                "id": spiel_id,
                "datum": datum_str,
                "zeit": zeit,
                "heim": heim,
                "gast": gast,
                "ergebnis": ergebnis,
                "einzelspiele": einzelspiele,
            })
        else:
            # Spiel OHNE Ergebnis → ausstehend
            match_teams = re.search(r'([A-ZÄÖÜ]{2,6}\d+)\s*-\s*([A-ZÄÖÜ]{2,6}\d+)', text)
            if not match_teams:
                continue

            heim = match_teams.group(1)
            gast = match_teams.group(2)
            spiel_id = f"{heim}_vs_{gast}_{datum_str}"
            erwartetes_ende = berechne_erwartetes_ende(datum_str, zeit)

            ausstehende_spiele.append({
                "datum": datum_str,
                "zeit": zeit,
                "heim": heim,
                "gast": gast,
                "spiel_id": spiel_id,
                "erwartetes_ende": erwartetes_ende,
            })

    return spiele_mit_ergebnis, ausstehende_spiele


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
    """Hauptfunktion mit Smart-Checking."""
    print(f"Tischtennis-Checker gestartet: {datetime.now(TZ_VIENNA).isoformat()}")

    # Konfiguration laden
    config = load_config()

    # Cache laden
    cache_data = load_cache()
    bekannte_spiele = set(cache_data.get("spiele", []))
    print(f"Bekannte Spiele im Cache: {len(bekannte_spiele)}")

    # Smart-Check: Soll überhaupt gecheckt werden?
    soll_checken, grund = soll_check_durchgefuehrt_werden(cache_data)
    print(f"Smart-Check: {'JA' if soll_checken else 'NEIN'} - {grund}")

    if not soll_checken:
        print("Kein Check nötig - beende.")
        return

    # Spiele von Webseite abrufen
    url = f"{BASE_URL}?lid=8615&do=spiele"
    print(f"Rufe URL ab: {url}")

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Fehler beim Abrufen: {e}")
        sys.exit(1)

    # Spielplan-Abruf-Zeitstempel aktualisieren
    cache_data["letzter_spielplan_abruf"] = datetime.now(TZ_VIENNA).isoformat()

    # Spiele parsen (zwei Listen)
    spiele_mit_ergebnis, ausstehende_spiele = parse_spielplan_page(response.text)
    print(f"Spiele mit Ergebnis: {len(spiele_mit_ergebnis)}")
    print(f"Ausstehende Spiele (gesamt): {len(ausstehende_spiele)}")

    # SIIM2 herausfiltern
    gefilterte_spiele = filter_spiele(spiele_mit_ergebnis)
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

    # Ausstehende Spiele aktualisieren
    aktualisiere_ausstehende_spiele(cache_data, ausstehende_spiele, spiele_mit_ergebnis)
    ausstehend_count = len(cache_data.get("ausstehende_spiele", []))
    print(f"Ausstehende Spiele im Cache: {ausstehend_count}")

    # Cache speichern
    cache_data["spiele"] = list(bekannte_spiele)
    save_cache(cache_data)
    print(f"Cache aktualisiert: {len(bekannte_spiele)} bekannte Spiele, {ausstehend_count} ausstehend")

    if not neue_spiele:
        print("Keine neuen Ergebnisse gefunden.")

    print(f"Fertig: {datetime.now(TZ_VIENNA).isoformat()}")


if __name__ == "__main__":
    main()
