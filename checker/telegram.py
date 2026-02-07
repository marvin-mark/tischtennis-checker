"""Telegram-Benachrichtigungen."""

import requests


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
    msg = f"""\U0001f3d3 <b>Neues Spiel eingetragen!</b>

\U0001f4c5 {datum_zeit}
\u2694\ufe0f <b>{heim}</b> <b>{ergebnis}</b> <b>{gast}</b>
"""

    # Einzelspiele hinzufügen
    if einzelspiele:
        msg += "\n<b>Details:</b>\n"
        for es in einzelspiele:
            typ_icon = "\U0001f465" if es["typ"] == "Doppel" else "\U0001f464"
            msg += f"{typ_icon} {es['heim']} <b>{es['ergebnis']}</b> {es['gast']}\n"

    return msg
