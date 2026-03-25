# WoW Realm Monitor

A lightweight, multi-user Telegram bot that monitors World of Warcraft realm status via the [Blizzard Battle.net API](https://develop.battle.net/) and fetches updates from Blizzard Customer Support on Bluesky.

🚀 **Don't want to host it yourself?**  
You can use the public, ready-to-use Telegram bot directly here: **[@wowrealm_bot](https://t.me/wowrealm_bot)**

## Features

- 👥 **Multi-User Personalized Alerts** — every user can configure their own list of realms to monitor via an interactive Telegram menu (`/menu`).
- 🔔 **Instant Realm Notifications** — alerts when your specific realms go offline or come back online.
- 🐦 **Bluesky Integration** — optionally receive posts from `support.blizzard.com` via ATProto (choose "Maintenance Only" or "All Feeds").
- ⏱ **Smart caching & Rate Limiting** — perfectly batches realm API requests so checking for thousands of users only requires one API call per realm, safely throttling Telegram broadcasts to avoid rate limits.
- 🐳 **Docker ready** — run anywhere with Docker Compose and a persistent SQLite database.

## Setup & Hosting

If you wish to host your own instance rather than using `@wowrealm_bot`:

### 1. Clone & configure

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

### 2a. Run with Docker (recommended)

```bash
docker compose up -d --build
```
This automatically mounts a `./data` folder to persist the SQLite users database (`bot.db`).

View logs:
```bash
docker compose logs -f
```

### 2b. Run with Python 3.12+

```bash
pip install -r requirements.txt
python main.py
```

## How It Works

1. Users chat with the bot and use `/menu` to add their desired realms and Bluesky preference.
2. Background tasks poll the connected realms APIs globally—fetching unique realms only once, minimizing overhead.
3. Upon detecting a status change, the bot dips into the SQLite database to locate all subscribed users and smoothly dispatches tailored messages.

## License

MIT
