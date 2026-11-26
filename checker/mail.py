"""Liest XTTV-Benachrichtigungsmails aus einem Gmail-Postfach (IMAP)."""

import email
import imaplib
import re
from email.header import decode_header, make_header

from bs4 import BeautifulSoup

IMAP_HOST = "imap.gmail.com"
# Gmail-Label, mit dem bereits weitergeleitete Mails markiert werden
LABEL_GESENDET = "tt-gesendet"


def verbinde(adresse, app_passwort):
    imap = imaplib.IMAP4_SSL(IMAP_HOST)
    imap.login(adresse, app_passwort)
    imap.select("INBOX")
    return imap


def _header(msg, name):
    wert = msg.get(name, "")
    try:
        return str(make_header(decode_header(wert)))
    except Exception:
        return wert


def _text_aus_mail(msg):
    """Liefert den lesbaren Text einer Mail (bevorzugt text/plain, sonst HTML -> Text)."""
    plain, html = None, None
    for teil in msg.walk() if msg.is_multipart() else [msg]:
        typ = teil.get_content_type()
        if teil.get_content_disposition() == "attachment":
            continue
        if typ not in ("text/plain", "text/html"):
            continue
        roh = teil.get_payload(decode=True) or b""
        text = roh.decode(teil.get_content_charset() or "utf-8", errors="replace")
        if typ == "text/plain" and plain is None:
            plain = text
        elif typ == "text/html" and html is None:
            html = text

    if html and not plain:
        plain = BeautifulSoup(html, "html.parser").get_text(separator="\n")
    text = plain or ""
    # Leerzeilen/Leerzeichen zusammenfassen
    zeilen = [re.sub(r"[ \t\xa0]+", " ", z).strip() for z in text.splitlines()]
    return "\n".join(z for z in zeilen if z)


def hole_neue_mails(imap, absender_filter, tage=14):
    """
    Sucht Mails vom XTTV-System, die noch nicht weitergeleitet wurden.
    Gibt Liste von (uid, betreff, text) zurück. Mails werden dabei NICHT als gelesen markiert.
    """
    suche = f'from:{absender_filter} -label:{LABEL_GESENDET} newer_than:{tage}d'
    status, daten = imap.uid("SEARCH", "X-GM-RAW", f'"{suche}"')
    if status != "OK":
        raise RuntimeError(f"IMAP-Suche fehlgeschlagen: {daten}")

    mails = []
    for uid in daten[0].split():
        status, teile = imap.uid("FETCH", uid, "(BODY.PEEK[])")
        if status != "OK" or not teile or not isinstance(teile[0], tuple):
            continue
        msg = email.message_from_bytes(teile[0][1])
        mails.append((uid, _header(msg, "Subject"), _text_aus_mail(msg)))
    return mails


def markiere_gesendet(imap, uid):
    imap.uid("STORE", uid, "+X-GM-LABELS", f"({LABEL_GESENDET})")
