#!/usr/bin/env python3
"""
Tischtennis-Mail-Checker
Liest die Ergebnis-Mails des XTTV-Benachrichtigungsdienstes aus Gmail
und leitet sie als Telegram-Nachricht weiter.
"""

import html
import os
import re
import sys
from datetime import datetime

from checker.config import TZ_VIENNA, load_config
from checker.mail import verbinde, hole_neue_mails, markiere_gesendet
from checker.telegram import send_telegram_message

# Mannschaften, deren Spiele nicht gemeldet werden sollen
IGNORIERTE_TEAMS = ["SIIM2"]
# Nur Mails, deren Absender diesen Text enthält
ABSENDER_FILTER = os.environ.get("XTTV_ABSENDER", "xttv")
MAX_LAENGE = 3500  # Telegram-Limit ist 4096 Zeichen

ERGEBNIS_RE = re.compile(r"([A-ZÄÖÜ]{2,6}\d+)\s*-\s*([A-ZÄÖÜ]{2,6}\d+)\s+(\d+:\d+)")
DATUM_RE = re.compile(r"\d{2}\.\d{2}\.\d{4}(?:\s+\d{2}:\d{2})?")
# Zeilen ohne Inhalt für dich (Abmeldelinks, Fußzeilen)
UNWICHTIG_RE = re.compile(r"(abmelden|abo .*lösch|löschen|abbestellen|https?://|datenschutz)", re.I)


def formatiere(betreff, text):
    """Baut aus einer XTTV-Mail eine Telegram-Nachricht. Gibt None zurück, wenn ignoriert."""
    treffer = ERGEBNIS_RE.search(text) or ERGEBNIS_RE.search(betreff)
    if treffer and any(t in (treffer.group(1), treffer.group(2)) for t in IGNORIERTE_TEAMS):
        return None

    zeilen = text.splitlines()
    if treffer:
        # Bei Ergebnis-Mails Fußzeilen/Links weglassen; andere Mails (z.B. Aktivierung) komplett
        zeilen = [z for z in zeilen if not UNWICHTIG_RE.search(z)]
    inhalt = "\n".join(zeilen)
    if len(inhalt) > MAX_LAENGE:
        inhalt = inhalt[:MAX_LAENGE] + "\n…"

    if treffer:
        heim, gast, ergebnis = treffer.groups()
        datum = DATUM_RE.search(text)
        kopf = "\U0001f3d3 <b>Neues Spiel eingetragen!</b>\n\n"
        if datum:
            kopf += f"\U0001f4c5 {datum.group(0)}\n"
        kopf += f"⚔️ <b>{heim}</b> <b>{ergebnis}</b> <b>{gast}</b>\n\n"
    else:
        kopf = f"\U0001f4e7 <b>{html.escape(betreff or 'XTTV-Nachricht')}</b>\n\n"

    return kopf + html.escape(inhalt)


def main():
    print(f"Mail-Checker gestartet: {datetime.now(TZ_VIENNA).isoformat()}")
    config = load_config()

    adresse = os.environ.get("GMAIL_ADDRESS")
    passwort = os.environ.get("GMAIL_APP_PASSWORD")
    if not adresse or not passwort:
        print("FEHLER: GMAIL_ADDRESS und GMAIL_APP_PASSWORD müssen gesetzt sein.")
        sys.exit(1)

    imap = verbinde(adresse, passwort)
    try:
        mails = hole_neue_mails(imap, ABSENDER_FILTER)
        print(f"Neue XTTV-Mails: {len(mails)}")

        fehler = 0
        for uid, betreff, text in mails:
            print(f"Mail: {betreff}")
            nachricht = formatiere(betreff, text)
            if nachricht is None:
                print("  -> ignoriert (Filter)")
                markiere_gesendet(imap, uid)
                continue
            if send_telegram_message(config, nachricht):
                print("  -> Gesendet!")
                markiere_gesendet(imap, uid)
            else:
                print("  -> Fehler! Wird beim nächsten Lauf erneut versucht.")
                fehler += 1
    finally:
        imap.logout()

    if fehler:
        sys.exit(1)
    print(f"Fertig: {datetime.now(TZ_VIENNA).isoformat()}")


if __name__ == "__main__":
    main()
