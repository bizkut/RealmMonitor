"""Realm status monitor with cache-based polling and Telegram notifications."""

import asyncio
import logging
from datetime import datetime, timezone

import aiohttp

from blizzard_api import BlizzardAPI

logger = logging.getLogger(__name__)

# Minimum polling interval (seconds) to avoid hammering the API
MIN_POLL_INTERVAL = 60
# Fallback polling interval if cache header is missing
FALLBACK_POLL_INTERVAL = 300


class RealmMonitor:
    """Monitors WoW realm statuses and sends Telegram alerts on changes."""

    def __init__(
        self,
        blizzard_api: BlizzardAPI,
        telegram_token: str,
        chat_id: str,
        region: str,
        realm_slugs: list[str],
    ):
        self.api = blizzard_api
        self.telegram_token = telegram_token
        self.chat_id = chat_id
        self.region = region.lower()
        self.realm_slugs = realm_slugs
        # Track last known status per realm: {slug: "UP" | "DOWN" | None}
        self._last_status: dict[str, str | None] = {s: None for s in realm_slugs}
        self._running = False

    async def send_telegram(self, session: aiohttp.ClientSession, message: str):
        """Send a message to the configured Telegram chat."""
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
        }
        try:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error("Telegram API error %s: %s", resp.status, body)
        except Exception as e:
            logger.error("Failed to send Telegram message: %s", e)

    async def check_realms(self, session: aiohttp.ClientSession) -> int:
        """
        Check all monitored realms and send notifications on status changes.

        Returns:
            The minimum cache max-age across all realm checks (for scheduling).
        """
        min_cache_age = FALLBACK_POLL_INTERVAL

        for slug in self.realm_slugs:
            try:
                realm_data, cache_max_age = await self.api.get_realm_status(
                    session, self.region, slug
                )

                if cache_max_age > 0:
                    min_cache_age = min(min_cache_age, cache_max_age)

                if realm_data is None:
                    logger.warning("Could not fetch status for realm: %s", slug)
                    continue

                current_status = realm_data["status"]
                previous_status = self._last_status.get(slug)
                realm_name = realm_data.get("name", slug)
                region_upper = self.region.upper()

                # Only notify on status CHANGE (skip first check to establish baseline)
                if previous_status is not None and current_status != previous_status:
                    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    if current_status == "UP":
                        msg = (
                            f"🟢 <b>Realm \"{realm_name}\" ({region_upper}) "
                            f"is back ONLINE</b>\n🕐 {now}"
                        )
                    else:
                        msg = (
                            f"🔴 <b>Realm \"{realm_name}\" ({region_upper}) "
                            f"went OFFLINE</b>\n🕐 {now}"
                        )
                    logger.info("Status change: %s -> %s for %s", previous_status, current_status, slug)
                    await self.send_telegram(session, msg)

                self._last_status[slug] = current_status

            except Exception as e:
                logger.error("Error checking realm %s: %s", slug, e)

        return max(min_cache_age, MIN_POLL_INTERVAL)

    async def run(self):
        """Main monitoring loop. Runs until stopped."""
        self._running = True
        logger.info(
            "Starting realm monitor for %s realm(s) in %s: %s",
            len(self.realm_slugs),
            self.region.upper(),
            ", ".join(self.realm_slugs),
        )

        async with aiohttp.ClientSession() as session:
            # Send startup message
            realm_list = ", ".join(s.title() for s in self.realm_slugs)
            startup_msg = (
                f"🔔 <b>WoW Realm Monitor Started</b>\n"
                f"📍 Region: <b>{self.region.upper()}</b>\n"
                f"🎮 Realms: <b>{realm_list}</b>\n"
                f"⏱ Polling: cache-based (min {MIN_POLL_INTERVAL}s, "
                f"fallback {FALLBACK_POLL_INTERVAL}s)"
            )
            await self.send_telegram(session, startup_msg)

            # Initial check to establish baseline
            logger.info("Running initial status check...")
            next_interval = await self.check_realms(session)

            # Build initial status message
            status_lines = []
            for slug in self.realm_slugs:
                status = self._last_status.get(slug, "UNKNOWN")
                icon = "🟢" if status == "UP" else "🔴" if status == "DOWN" else "❓"
                status_lines.append(f"  {icon} {slug.title()}: {status}")

            initial_msg = (
                f"📊 <b>Initial Realm Status</b>\n"
                + "\n".join(status_lines)
                + f"\n\n⏱ Next check in {next_interval}s"
            )
            await self.send_telegram(session, initial_msg)

            # Continuous monitoring loop
            while self._running:
                logger.info("Next check in %d seconds...", next_interval)
                await asyncio.sleep(next_interval)

                try:
                    next_interval = await self.check_realms(session)
                except Exception as e:
                    logger.error("Monitor loop error: %s", e)
                    next_interval = FALLBACK_POLL_INTERVAL

    def stop(self):
        """Signal the monitor to stop."""
        self._running = False
