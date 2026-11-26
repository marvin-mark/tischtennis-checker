#!/usr/bin/env python3
"""
Tischtennis-Spiele Checker
Prüft auf neue eingetragene Spielergebnisse und sendet Telegram-Benachrichtigungen.
"""

import sys
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from checker.config import BASE_URL, LEAGUE_ID, TZ_VIENNA, load_config
from checker.cache import load_cache, save_cache
from checker.parser import parse_spielplan_page, filter_spiele
from checker.telegram import send_telegram_message, format_spiel_nachricht

# Alle gespielten Spiele der Liga in EINER Anfrage (statt seitenweise)
SPIELE_PARAMS = {"lid": LEAGUE_ID, "do": "spiele", "zeit": "done", "limit": "500"}


def erstelle_session():
    """HTTP-Session mit Wiederholung bei kurzzeitigen Serverfehlern."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=10,  # Wartezeit 10s, 20s, 40s
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "TischtennisChecker/1.1"})
    return session


def hole_spielplan(session):
    """Ruft die Spielliste ab. Beendet das Skript mit Fehler, wenn keine echten Daten kommen."""
    try:
        response = session.get(BASE_URL, params=SPIELE_PARAMS, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"FEHLER: Spielplan nicht abrufbar: {e}")
        sys.exit(1)

    html = response.text
    if "gameSummary" not in html:
        # Statt Spielliste kam eine Sicherheitsprüfung / leere Seite.
        # Nicht als "keine neuen Ergebnisse" werten, sondern Lauf fehlschlagen lassen.
        print("FEHLER: Seite hat keine Spielliste geliefert (Sicherheitsprüfung oder leere Seite).")
        print(html[:500])
        sys.exit(1)

    return html


def main():
    print(f"Tischtennis-Checker gestartet: {datetime.now(TZ_VIENNA).isoformat()}")

    config = load_config()

    # Bekannte Spiele laden
    cache_data = load_cache()
    bekannte_spiele = set(cache_data.get("spiele", []))
    print(f"Bekannte Spiele: {len(bekannte_spiele)}")

    html = hole_spielplan(erstelle_session())
    alle_spiele_mit_ergebnis, _ = parse_spielplan_page(html)
    print(f"Gesamt Spiele mit Ergebnis: {len(alle_spiele_mit_ergebnis)}")

    # SIIM2 herausfiltern
    gefilterte_spiele = filter_spiele(alle_spiele_mit_ergebnis)
    print(f"Nach Filter (ohne SIIM2): {len(gefilterte_spiele)}")

    # Neue Spiele finden
    neue_spiele = [s for s in gefilterte_spiele if s.get("id") and s["id"] not in bekannte_spiele]
    print(f"Neue Ergebnisse: {len(neue_spiele)}")

    # Benachrichtigungen senden - nur bei Erfolg als bekannt markieren
    gesendet = 0
    for spiel in neue_spiele:
        nachricht = format_spiel_nachricht(spiel)
        print(f"Sende: {spiel.get('heim')} vs {spiel.get('gast')} [{spiel.get('ergebnis')}]")
        if send_telegram_message(config, nachricht):
            print("  -> Gesendet!")
            bekannte_spiele.add(spiel["id"])
            gesendet += 1
        else:
            print("  -> Fehler! Wird beim nächsten Lauf erneut versucht.")

    # Nur speichern, wenn sich etwas geändert hat (vermeidet Commits bei jedem Lauf)
    if gesendet:
        cache_data["spiele"] = sorted(bekannte_spiele)
        save_cache(cache_data)
        print(f"Gespeichert: {len(bekannte_spiele)} bekannte Spiele")
    else:
        print("Keine neuen Ergebnisse.")

    if gesendet < len(neue_spiele):
        print("FEHLER: Nicht alle Nachrichten konnten gesendet werden.")
        sys.exit(1)

    print(f"Fertig: {datetime.now(TZ_VIENNA).isoformat()}")


if __name__ == "__main__":
    main()
