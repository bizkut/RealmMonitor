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

    # Parse realms into (region, slug, name)
    raw_realms = [r.strip() for r in config["REALMS"].split(",") if r.strip()]
    if not raw_realms:
        logger.error("REALMS must contain at least one realm in REGION-RealmName format.")
        sys.exit(1)

    parsed_realms = []
    for raw in raw_realms:
        if "-" not in raw:
            logger.error("Invalid format for realm '%s'. Must be REGION-RealmName (e.g. US-Frostmourne)", raw)
            sys.exit(1)
        
        region, name = raw.split("-", 1)
        region = region.strip().lower()
        if region not in ["us", "eu", "kr", "tw"]:
            logger.error("Invalid region '%s' for realm '%s'. Valid regions: us, eu, kr, tw", region, raw)
            sys.exit(1)
            
        slug = BlizzardAPI.to_slug(name)
        parsed_realms.append((region, slug, name.strip()))

    config["PARSED_REALMS"] = parsed_realms
    return config


async def main():
    """Initialize and run the realm monitor."""
    config = load_config()

    logger.info("=== WoW Realm Monitor ===")
    
    realm_display = [f"{r[0].upper()}-{r[2]}" for r in config["PARSED_REALMS"]]
    logger.info("Monitoring Realms: %s", ", ".join(realm_display))

    api = BlizzardAPI(
        client_id=config["BLIZZARD_CLIENT_ID"],
        client_secret=config["BLIZZARD_CLIENT_SECRET"],
    )

    monitor = RealmMonitor(
        blizzard_api=api,
        telegram_token=config["TELEGRAM_BOT_TOKEN"],
        chat_id=config["TELEGRAM_CHAT_ID"],
        realms=config["PARSED_REALMS"],
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
