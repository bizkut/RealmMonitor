# WoW Realm Monitor

A lightweight, multi-user Telegram bot that monitors World of Warcraft realm status via the [Blizzard Battle.net API](https://develop.battle.net/) and delivers official Blizzard news from Bluesky directly to Telegram.

🚀 **Don't want to host it yourself?**  
You can use the public, ready-to-use Telegram bot directly here: **[@wowrealm_bot](https://t.me/wowrealm_bot)**

## Features

- 👥 **Multi-User Personalized Alerts** — every user configures their own realm watchlist and preferences via `/menu`.
- 🔔 **Instant Realm Notifications** — alerts when your realms go offline or come back online.
- ⚡ **Live Inline Checking** — use `/check [version]-<region>-<realmname>` to instantly peek at any realm without adding it to your watchlist (e.g. `/check us-Frostmourne`, `/check classic-eu-Firemaw`). Retail is the default version if omitted.
- 🖱️ **One-Click Check from Menu** — tap any realm name in your `/menu` list to trigger an instant status check.
- 🐦 **Multi-Feed Bluesky Integration** — toggle each feed independently from `/menu`:
  - **Support Feed** (`support.blizzard.com`) — maintenance and outage alerts.
  - **Official WoW Feed** (`worldofwarcraft.blizzard.com`) — retail news and announcements.
  - **Classic Devs Feed** (`wowclassicdevs.blizzard.com`) — WoW Classic ecosystem updates.
- 🌐 **Per-User DST-Aware Timezones** — set your IANA timezone (e.g. `America/New_York`, `Europe/London`) from `/menu`. All timestamps in alerts auto-adjust for Daylight Saving Time.
- ⏱ **Smart Caching & Rate Limiting** — a single API call per unique realm, safely throttled Telegram broadcasts.
- 📋 **Native Command Menu** — all commands are registered with Telegram for autocomplete and discoverability.
- 🐳 **Docker Ready** — runs anywhere with Docker Compose and a persistent SQLite database.

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Register and show welcome message |
| `/menu` | Manage realms, Bluesky feeds & timezone |
| `/check <realm>` | Quick status check (e.g. `us-Frostmourne`) |
| `/addrealm` | Add a realm to your watchlist |
| `/stats` | Bot statistics *(admin only)* |

## Setup & Hosting

If you wish to host your own instance rather than using `@wowrealm_bot`:

### 1. Clone & Configure

```bash
git clone https://github.com/bizkut/RealmMonitor.git
cd RealmMonitor
cp .env.example .env
```

Edit `.env` with your credentials:

| Variable | Description |
|----------|-------------|
| `BLIZZARD_CLIENT_ID` | From [Blizzard Developer Portal](https://develop.battle.net/) |
| `BLIZZARD_CLIENT_SECRET` | From Blizzard Developer Portal |
| `TELEGRAM_BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) |
| `BLUESKY_EMAIL` | Bluesky account email/handle |
| `BLUESKY_APP_PASSWORD` | App password from Bluesky settings |

### 2a. Run with Docker (Recommended)

```bash
docker compose up -d --build
```

This automatically mounts a `./data` folder to persist the SQLite database (`bot.db`).

**View logs:**
```bash
docker compose logs -f
```

### 2b. Run with Python 3.12+

```bash
pip install -r requirements.txt
python main.py
```

## How It Works

1. Users interact with the bot via `/menu` to add realms, configure Bluesky feeds, and set their timezone.
2. Background tasks poll the Blizzard Connected Realm APIs globally — each unique realm is fetched only once per cycle, regardless of how many users track it.
3. On a status change, the bot groups users by timezone to render accurate local timestamps, then dispatches personalized alerts.
4. Bluesky feeds are polled every 5 minutes. Each feed tracks the last dispatched post URI in the database to guarantee every post is delivered exactly once, even across restarts.

## License

MIT
