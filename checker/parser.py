"""HTML-Parsing der OETTV-Spielplan-Seite."""

import re
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

from checker.config import TZ_VIENNA


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
