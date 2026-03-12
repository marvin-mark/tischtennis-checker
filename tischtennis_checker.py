#!/usr/bin/env python3
"""
Tischtennis-Spiele Checker
Prüft auf neue eingetragene Spielergebnisse und sendet Telegram-Benachrichtigungen.
"""

import sys
from datetime import datetime

import requests

from checker.config import BASE_URL, TZ_VIENNA, load_config
from checker.cache import load_cache, save_cache
from checker.parser import parse_spielplan_page, filter_spiele
from checker.telegram import send_telegram_message, format_spiel_nachricht


def main():
    print(f"Tischtennis-Checker gestartet: {datetime.now(TZ_VIENNA).isoformat()}")

    config = load_config()

    # Bekannte Spiele laden
    cache_data = load_cache()
    bekannte_spiele = set(cache_data.get("spiele", []))
    print(f"Bekannte Spiele: {len(bekannte_spiele)}")

    # Spiele von Webseite abrufen (alle Seiten)
    alle_spiele_mit_ergebnis = []
    seite = 1

    while True:
        url = f"{BASE_URL}?lid=8615&do=spiele&seite={seite}"
        print(f"Rufe URL ab: {url}")

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Fehler beim Abrufen von Seite {seite}: {e}")
            if seite == 1:
                sys.exit(1)
            break

        spiele_mit_ergebnis, _ = parse_spielplan_page(response.text)
        print(f"Seite {seite}: {len(spiele_mit_ergebnis)} Spiele mit Ergebnis")

        if not spiele_mit_ergebnis and seite > 1:
            break

        alle_spiele_mit_ergebnis.extend(spiele_mit_ergebnis)
        seite += 1

        if seite > 10:  # Sicherheitslimit
            break

    print(f"Gesamt Spiele mit Ergebnis: {len(alle_spiele_mit_ergebnis)}")

    # SIIM2 herausfiltern
    gefilterte_spiele = filter_spiele(alle_spiele_mit_ergebnis)
    print(f"Nach Filter (ohne SIIM2): {len(gefilterte_spiele)}")

    # Neue Spiele finden
    neue_spiele = [s for s in gefilterte_spiele if s.get("id") and s["id"] not in bekannte_spiele]
    print(f"Neue Ergebnisse: {len(neue_spiele)}")

    # Benachrichtigungen senden - nur bei Erfolg als bekannt markieren
    for spiel in neue_spiele:
        nachricht = format_spiel_nachricht(spiel)
        print(f"Sende: {spiel.get('heim')} vs {spiel.get('gast')} [{spiel.get('ergebnis')}]")
        if send_telegram_message(config, nachricht):
            print("  -> Gesendet!")
            bekannte_spiele.add(spiel["id"])
        else:
            print("  -> Fehler! Wird beim nächsten Lauf erneut versucht.")

    # Speichern
    cache_data["spiele"] = list(bekannte_spiele)
    save_cache(cache_data)
    print(f"Gespeichert: {len(bekannte_spiele)} bekannte Spiele")

    if not neue_spiele:
        print("Keine neuen Ergebnisse.")

    print(f"Fertig: {datetime.now(TZ_VIENNA).isoformat()}")


if __name__ == "__main__":
    main()
