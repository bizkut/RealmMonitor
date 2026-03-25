import asyncio
import logging
import time
from datetime import datetime, timezone
from datetime import timedelta

import aiohttp
from telegram import Bot

from blizzard_api import BlizzardAPI
import database
from bluesky_fetcher import BlueskyFetcher

logger = logging.getLogger(__name__)

MIN_POLL_INTERVAL = 60
FALLBACK_POLL_INTERVAL = 300
BLUESKY_POLL_INTERVAL = 300


class MonitorService:
    """Monitors WoW realm statuses and Bluesky updates."""

    def __init__(self, blizzard_api: BlizzardAPI, bot: Bot, bsky_fetcher: BlueskyFetcher):
        self.api = blizzard_api
        self.bot = bot
        self.bsky = bsky_fetcher
        
        self._last_status: dict[tuple[str, str], str | None] = {}
        self._running = False
        self.start_time = time.time()
        self.blizzard_fetches = 0
        self.bluesky_fetches = 0

    async def broadcast_telegram(self, chat_ids: list[int], message: str):
        """Send a message to multiple users, strictly rate-limited."""
        for cid in chat_ids:
            try:
                await self.bot.send_message(chat_id=cid, text=message, parse_mode="HTML")
            except Exception as e:
                logger.error("Failed to send to %s: %s", cid, e)
            await asyncio.sleep(0.05)  # Telegram limit: ~30 msgs/sec

    async def check_realms(self, session: aiohttp.ClientSession) -> int:
        unique_realms = await database.get_unique_realms()
        if not unique_realms:
            return FALLBACK_POLL_INTERVAL

        min_cache_age = FALLBACK_POLL_INTERVAL

        for region, slug, original_name in unique_realms:
            realm_key = (region, slug)
            try:
                self.blizzard_fetches += 1
                realm_data, cache_max_age = await self.api.get_realm_status(session, region, slug)

                if cache_max_age > 0:
                    min_cache_age = min(min_cache_age, cache_max_age)

                if realm_data is None:
                    continue

                current_status = realm_data["status"]
                previous_status = self._last_status.get(realm_key)
                
                realm_name = realm_data.get("name", original_name)
                region_upper = region.upper()

                if previous_status is not None and current_status != previous_status:
                    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    if current_status == "UP":
                        msg = f"🟢 <b>Realm \"{realm_name}\" ({region_upper}) is back ONLINE</b>\n🕐 {now}"
                    else:
                        msg = f"🔴 <b>Realm \"{realm_name}\" ({region_upper}) went OFFLINE</b>\n🕐 {now}"
                    
                    logger.info("Status change: %s -> %s for %s-%s", previous_status, current_status, region_upper, slug)
                    users = await database.get_users_for_realm(region, slug)
                    if users:
                        await self.broadcast_telegram(users, msg)

                self._last_status[realm_key] = current_status

            except Exception as e:
                logger.error("Error checking realm %s-%s: %s", region.upper(), slug, e)

        return max(min_cache_age, MIN_POLL_INTERVAL)

    async def check_bluesky(self):
        try:
            self.bluesky_fetches += 1
            posts = await self.bsky.fetch_new_posts()
            for post in posts:
                if post['is_maintenance']:
                    targets = await database.get_bluesky_subscribers(['maintenance', 'all'])
                else:
                    targets = await database.get_bluesky_subscribers(['all'])
                
                if targets:
                    msg = (
                        f"🐦 <b>Blizzard Support Update</b>\n\n"
                        f"{post['text']}\n\n"
                        # Bluesky post URIs are 'at://...', we can't easily deep link the exact post without parsing
                        # But we can at least drop a general link. Usually AT URIs look like: at://did:plc:x/app.bsky.feed.post/y
                        f"👉 <a href='https://bsky.app/profile/support.blizzard.com'>View on Bluesky</a>"
                    )
                    await self.broadcast_telegram(targets, msg)
        except Exception as e:
            logger.error("Error checking Bluesky: %s", e)

    async def _realm_loop(self):
        async with aiohttp.ClientSession() as session:
            # First check purely populates the baseline state if we just restarted
            next_interval = await self.check_realms(session)
            while self._running:
                await asyncio.sleep(next_interval)
                next_interval = await self.check_realms(session)

    async def _bluesky_loop(self):
        while self._running:
            await self.check_bluesky()
            await asyncio.sleep(BLUESKY_POLL_INTERVAL)

    async def run(self):
        self._running = True
        logger.info("Starting background monitor service...")
        
        # Run both tasks concurrently
        await asyncio.gather(
            self._realm_loop(),
            self._bluesky_loop()
        )

    def stop(self):
        self._running = False

    def get_stats(self) -> dict:
        """Calculate and return system stats."""
        uptime = time.time() - self.start_time
        up_minutes = max(1.0, float(uptime / 60.0))
        
        td = timedelta(seconds=int(uptime))
        
        return {
            "uptime": str(td),
            "blizzard_rpm": f"{self.blizzard_fetches / up_minutes:.2f}",
            "bluesky_rpm": f"{self.bluesky_fetches / up_minutes:.2f}"
        }
