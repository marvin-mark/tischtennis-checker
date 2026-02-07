# 🏓 Tischtennis-Ergebnis-Checker

Automatische Telegram-Benachrichtigungen für neue Tischtennis-Spielergebnisse der [OETTV Landesliga](https://oettv.xttv.at/).

![GitHub Actions](https://github.com/marvin-mark/tischtennis-checker/actions/workflows/tischtennis.yml/badge.svg)

## Features

- ✅ **Smart-Checking** - checkt nur, wenn ein Ergebnis erwartet wird (spart ~63% GitHub Actions Minutes)
- ✅ **Telegram-Benachrichtigungen** mit Spieldetails
- ✅ **Einzelspiel-Details** (wer gegen wen, Ergebnis)
- ✅ **Ausstehende Spiele tracken** - erkennt geplante Spiele und checkt gezielt nach Spielende
- ✅ **Filterung** bestimmter Mannschaften (SIIM2)
- ✅ **Kostenlos** - läuft auf GitHub Servern

## So funktioniert's

Der Checker läuft nicht blind rund um die Uhr, sondern entscheidet intelligent:

1. **Abends (17:00-00:30 Wien)** - Cron alle 30 Minuten aktiv (Spielzeit)
2. **Tagsüber (01:00-17:00 Wien)** - Cron alle 2 Stunden (für Ergebnisse die am nächsten Tag eingetragen werden)
3. **Smart-Check im Script** - vor jedem HTTP-Request wird geprüft:
   - Gibt es ein ausstehendes Spiel, dessen erwartetes Ende erreicht ist? → **Check!**
   - Letzter Spielplan-Abruf > 12 Stunden? → **Refresh!**
   - Sonst → **Skip** (kein HTTP-Request, sofortiger Exit)

**Ergebnis:** Benachrichtigungen kommen abends innerhalb von max. 30 Minuten, tagsüber innerhalb von max. 2 Stunden - bei 50% weniger Ressourcenverbrauch.

## Beispiel-Nachricht

```
🏓 Neues Tischtennis-Ergebnis eingetragen!

📅 27.01.2026 20:00
⚔️ HALT1 6:2 INZI1

Details:
👤 Max Mustermann 3:0 Erika Musterfrau
👤 Hans Beispiel 3:0 Otto Normalverbraucher
👥 Mustermann / Beispiel 3:1 Musterfrau / Normalverbraucher
...
```

## Setup

### 1. Repository forken

Klicke oben rechts auf **Fork**.

### 2. Telegram Bot erstellen

1. Öffne [@BotFather](https://t.me/BotFather) in Telegram
2. Sende `/newbot` und folge den Anweisungen
3. Kopiere den **Bot-Token**
4. Starte deinen neuen Bot und sende `/start`
5. Öffne `https://api.telegram.org/bot<DEIN_TOKEN>/getUpdates`
6. Kopiere deine **Chat-ID** aus der Antwort

### 3. GitHub Secrets einrichten

1. Gehe zu **Settings** → **Secrets and variables** → **Actions**
2. Füge hinzu:
   - `TELEGRAM_BOT_TOKEN` - Dein Bot-Token
   - `TELEGRAM_CHAT_ID` - Deine Chat-ID

### 4. Anpassen (optional)

In `tischtennis_checker.py` kannst du anpassen:
- `BASE_URL` - andere Liga/Spielklasse
- `filter_spiele()` - andere Mannschaften filtern

## Lokale Ausführung

```bash
# Abhängigkeiten installieren
pip install -r requirements.txt

# config.json erstellen
cp config.example.json config.json
# Bot-Token und Chat-ID eintragen

# Ausführen
python tischtennis_checker.py
```

## Technologie

- **Python 3.11+** mit requests, BeautifulSoup & zoneinfo
- **GitHub Actions** mit optimiertem Cron-Schedule (abends alle 30 Min, tagsüber alle 2h)
- **Telegram Bot API** für Benachrichtigungen

## Lizenz

MIT - Frei verwendbar und anpassbar.
