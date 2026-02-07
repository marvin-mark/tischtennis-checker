"""Cache-Verwaltung & Smart-Check-Logik."""

import json
from datetime import datetime, timedelta

from checker.config import SCRIPT_DIR, TZ_VIENNA

# Cache-Datei im Repo-Root
CACHE_FILE = SCRIPT_DIR / "bekannte_spiele.json"


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
