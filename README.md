# 🏓 Tischtennis-Ergebnis-Checker

Automatische Telegram-Benachrichtigungen für neue Tischtennis-Spielergebnisse der [OETTV Landesliga](https://oettv.xttv.at/).

![GitHub Actions](https://github.com/marvin-mark/tischtennis-checker/actions/workflows/tischtennis.yml/badge.svg)

## Features

- ✅ **Automatische Prüfung** alle 30 Minuten via GitHub Actions
- ✅ **Telegram-Benachrichtigungen** mit Spieldetails
- ✅ **Einzelspiel-Details** (wer gegen wen, Ergebnis)
- ✅ **Filterung** bestimmter Mannschaften
- ✅ **Kostenlos** - läuft auf GitHub Servern

## Beispiel-Nachricht

```
🏓 Neues Tischtennis-Ergebnis eingetragen!

📅 27.01.2026 20:00
⚔️ HALT1 vs INZI1
📊 Ergebnis: 6:2

Details:
👤 Richard Madersbacher vs Bernhard Beiler 3:0
👤 Josef Felderer vs Uwe Förtsch 3:0
👥 Weitlaner / Felderer vs Förtsch / Scirtuicchio 3:1
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

- **Python 3.11** mit requests & BeautifulSoup
- **GitHub Actions** für automatische Ausführung
- **Telegram Bot API** für Benachrichtigungen

## Lizenz

MIT - Frei verwendbar und anpassbar.
