#!/usr/bin/env python3
"""
Tischtennis-Spiele Checker
Prüft auf neue eingetragene Spielergebnisse und sendet Telegram-Benachrichtigungen.
Enthält Smart-Checking: Checkt nur, wenn ein Ergebnis erwartet wird.
"""

import sys
from datetime import datetime

import requests

from checker.config import BASE_URL, TZ_VIENNA, load_config
from checker.cache import load_cache, save_cache, soll_check_durchgefuehrt_werden, aktualisiere_ausstehende_spiele
from checker.parser import parse_spielplan_page, filter_spiele
from checker.telegram import send_telegram_message, format_spiel_nachricht


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
