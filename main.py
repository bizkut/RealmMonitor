"""WoW Realm Monitor - Entry point."""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

from blizzard_api import BlizzardAPI
from monitor import RealmMonitor

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
        "TELEGRAM_CHAT_ID",
        "REGION",
        "REALMS",
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
        logger.error("Please fill in your .env file. See .env.example for reference.")
        sys.exit(1)

    # Parse realms into slugs
    realm_names = [r.strip() for r in config["REALMS"].split(",") if r.strip()]
    if not realm_names:
        logger.error("REALMS must contain at least one realm name.")
        sys.exit(1)

    config["REALM_SLUGS"] = [BlizzardAPI.to_slug(name) for name in realm_names]
    config["REALM_NAMES"] = realm_names

    return config


async def main():
    """Initialize and run the realm monitor."""
    config = load_config()

    logger.info("=== WoW Realm Monitor ===")
    logger.info("Region: %s", config["REGION"].upper())
    logger.info("Realms: %s", ", ".join(config["REALM_NAMES"]))

    api = BlizzardAPI(
        client_id=config["BLIZZARD_CLIENT_ID"],
        client_secret=config["BLIZZARD_CLIENT_SECRET"],
    )

    monitor = RealmMonitor(
        blizzard_api=api,
        telegram_token=config["TELEGRAM_BOT_TOKEN"],
        chat_id=config["TELEGRAM_CHAT_ID"],
        region=config["REGION"],
        realm_slugs=config["REALM_SLUGS"],
    )

    try:
        await monitor.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        monitor.stop()
    except Exception as e:
        logger.error("Fatal error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
