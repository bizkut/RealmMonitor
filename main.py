"""WoW Realm Monitor - Entry point."""

import asyncio
import logging
import os
import sys
import signal

from dotenv import load_dotenv
from telegram.ext import Application

import database
from blizzard_api import BlizzardAPI
from bluesky_fetcher import BlueskyFetcher
from monitor import MonitorService
from bot_handlers import get_bot_handlers

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Load and validate configuration from .env file."""
    load_dotenv()

    required_keys = [
        "BLIZZARD_CLIENT_ID",
        "BLIZZARD_CLIENT_SECRET",
        "TELEGRAM_BOT_TOKEN",
        "BLUESKY_EMAIL",
        "BLUESKY_APP_PASSWORD",
    ]

    config = {}
    missing = []
    for key in required_keys:
        value = os.getenv(key)
        if not value:
            missing.append(key)
        else:
            config[key] = value

    if missing:
        logger.error("Missing required config keys: %s", ", ".join(missing))
        logger.error("Please fill in your .env file.")
        sys.exit(1)

    return config


async def main():
    """Initialize and run the realm monitor & Telegram bot."""
    config = load_config()

    logger.info("=== WoW Realm Monitor Multi-User ===")
    
    # Initialize SQLite database
    await database.init_db()

    # Build Telegram Application
    app = Application.builder().token(config["TELEGRAM_BOT_TOKEN"]).build()
    
    # Register handlers
    for handler in get_bot_handlers():
        app.add_handler(handler)

    # Initialize APIs
    api = BlizzardAPI(
        client_id=config["BLIZZARD_CLIENT_ID"],
        client_secret=config["BLIZZARD_CLIENT_SECRET"],
    )
    
    bsky_fetcher = BlueskyFetcher(
        handle=config["BLUESKY_EMAIL"],
        app_password=config["BLUESKY_APP_PASSWORD"]
    )

    monitor = MonitorService(
        blizzard_api=api,
        bot=app.bot,
        bsky_fetcher=bsky_fetcher
    )
    app.bot_data['monitor'] = monitor

    # Start the services
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    monitor_task = asyncio.create_task(monitor.run())

    # Wait until interrupted
    stop_signal = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_signal.set)
        except NotImplementedError:
            pass

    try:
        await stop_signal.wait()
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Shutting down...")
        monitor.stop()
        if not monitor_task.done():
            await monitor_task
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
