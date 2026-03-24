# WoW Realm Monitor

A lightweight bot that monitors World of Warcraft realm status via the [Blizzard Battle.net API](https://develop.battle.net/) and sends Telegram notifications when realms go offline or come back online.

## Features

- 🔔 **Instant notifications** — alerts when a realm goes offline or comes back online
- ⏱ **Smart polling** — uses Blizzard API cache headers to schedule checks efficiently
- 🌏 **Multi-realm** — monitor multiple realms at once
- 🐳 **Docker ready** — run anywhere with Docker Compose

## Notifications

- 🔴 **Realm "Frostmourne" (US) went OFFLINE** — timestamp
- 🟢 **Realm "Frostmourne" (US) is back ONLINE** — timestamp

## Setup

### 1. Clone & configure

```bash
git clone https://github.com/<your-username>/RealmMonitor.git
cd RealmMonitor
cp .env.example .env
```

Edit `.env` with your credentials:

| Variable | Description |
|----------|-------------|
| `BLIZZARD_CLIENT_ID` | From [Blizzard Developer Portal](https://develop.battle.net/) |
| `BLIZZARD_CLIENT_SECRET` | From Blizzard Developer Portal |
| `TELEGRAM_BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | Your Telegram chat/group ID |
| `REGION` | `us`, `eu`, `kr`, or `tw` |
| `REALMS` | Comma-separated realm names (e.g. `Frostmourne,Gundrak`) |

### 2a. Run with Docker (recommended)

```bash
docker compose up -d --build
```

View logs:
```bash
docker compose logs -f
```

### 2b. Run with Python

```bash
pip install -r requirements.txt
python main.py
```

## How It Works

1. Authenticates with Blizzard OAuth (auto-refreshes tokens)
2. Resolves realm names to connected realm IDs
3. Polls the Connected Realm API on cache expiry intervals (~60s)
4. Sends a Telegram message only when a realm's status **changes**

## License

MIT
