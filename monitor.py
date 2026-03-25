import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
import zoneinfo
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

    def __init__(self, blizzard_api: BlizzardAPI, bot: Bot, bsky_fetcher: BlueskyFetcher, bsky_wow_fetcher: BlueskyFetcher = None, bsky_classic_fetcher: BlueskyFetcher = None):
        self.api = blizzard_api
        self.bot = bot
        self.bsky = bsky_fetcher
        self.bsky_wow = bsky_wow_fetcher
        self.bsky_classic = bsky_classic_fetcher
        
        self._last_status: dict[tuple[str, str, str], str | None] = {}
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

        for region, slug, original_name, game_version in unique_realms:
            realm_key = (region, slug, game_version)
            try:
                self.blizzard_fetches += 1
                realm_data, cache_max_age = await self.api.get_realm_status(session, region, slug, game_version)

                if cache_max_age > 0:
                    min_cache_age = min(min_cache_age, cache_max_age)

                if realm_data is None:
                    continue

                current_status = realm_data["status"]
                previous_status = self._last_status.get(realm_key)
                
                realm_name = str(realm_data.get("name", original_name)).title()
                region_upper = region.upper()

                if previous_status is not None and current_status != previous_status:
                    logger.info("Status change: %s -> %s for %s-%s (%s)", previous_status, current_status, region_upper, slug, game_version)
                    users = await database.get_users_for_realm(region, slug, game_version)
                    if users:
                        v_tag = f"[{game_version.title()}] " if game_version != "retail" else ""
                        tz_groups = await database.get_users_by_timezone(users)
                        for tz_name, user_group in tz_groups.items():
                            try:
                                tz = zoneinfo.ZoneInfo(tz_name)
                            except Exception:
                                tz = zoneinfo.ZoneInfo("UTC")
                            
                            now_local = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
                            if current_status == "UP":
                                local_msg = f"🟢 <b>Realm {v_tag}\"{realm_name}\" ({region_upper}) is back ONLINE</b>\n🕐 {now_local}"
                            else:
                                local_msg = f"🔴 <b>Realm {v_tag}\"{realm_name}\" ({region_upper}) went OFFLINE</b>\n🕐 {now_local}"
                                
                            await self.broadcast_telegram(user_group, local_msg)

                self._last_status[realm_key] = current_status

            except Exception as e:
                logger.error("Error checking realm %s-%s (%s): %s", region.upper(), slug, game_version, e)

        return max(min_cache_age, MIN_POLL_INTERVAL)

    async def check_bluesky(self):
        try:
            self.bluesky_fetches += 1
            posts = await self.bsky.fetch_new_posts()
            if posts:
                logger.info("Found %d new posts from %s", len(posts), self.bsky.target_account)
            for post in posts:
                logger.info("Processing post from %s: %s...", post['author_name'], post['text'][:50])
                if post['is_maintenance']:
                    targets = await database.get_bluesky_subscribers(['maintenance', 'all'])
                else:
                    targets = await database.get_bluesky_subscribers(['all'])
                
                if targets:
                    tz_groups = await database.get_users_by_timezone(targets)
                    for tz_name, user_group in tz_groups.items():
                        try:
                            tz = zoneinfo.ZoneInfo(tz_name)
                        except Exception:
                            tz = zoneinfo.ZoneInfo("UTC")
                        now_local = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
                        msg = (
                            f"🐦 <b>{post['author_name']} Update</b>\n\n"
                            f"{post['text']}\n\n"
                            f"🕐 {now_local}\n"
                            f"👉 <a href='{post['post_url']}'>View on Bluesky</a>"
                        )
                        await self.broadcast_telegram(user_group, msg)
        except Exception as e:
            logger.error("Error checking Bluesky: %s", e)
    async def check_wow_bluesky(self):
        if not self.bsky_wow:
            return
        try:
            self.bluesky_fetches += 1
            posts = await self.bsky_wow.fetch_new_posts()
            if posts:
                logger.info("Found %d new posts from %s", len(posts), self.bsky_wow.target_account)
            for post in posts:
                logger.info("Processing post from %s: %s...", post['author_name'], post['text'][:50])
                targets = await database.get_wow_bluesky_subscribers(['all'])
                
                if targets:
                    tz_groups = await database.get_users_by_timezone(targets)
                    for tz_name, user_group in tz_groups.items():
                        try:
                            tz = zoneinfo.ZoneInfo(tz_name)
                        except Exception:
                            tz = zoneinfo.ZoneInfo("UTC")
                        now_local = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
                        msg = (
                            f"🗡 <b>{post['author_name']} Update</b>\n\n"
                            f"{post['text']}\n\n"
                            f"🕐 {now_local}\n"
                            f"👉 <a href='{post['post_url']}'>View on Bluesky</a>"
                        )
                        await self.broadcast_telegram(user_group, msg)
        except Exception as e:
            logger.error("Error checking WoW Bluesky: %s", e)
            
    async def check_classic_bluesky(self):
        if not self.bsky_classic:
            return
        try:
            self.bluesky_fetches += 1
            posts = await self.bsky_classic.fetch_new_posts()
            if posts:
                logger.info("Found %d new posts from %s", len(posts), self.bsky_classic.target_account)
            for post in posts:
                logger.info("Processing post from %s: %s...", post['author_name'], post['text'][:50])
                targets = await database.get_classic_bluesky_subscribers(['all'])
                
                if targets:
                    tz_groups = await database.get_users_by_timezone(targets)
                    for tz_name, user_group in tz_groups.items():
                        try:
                            tz = zoneinfo.ZoneInfo(tz_name)
                        except Exception:
                            tz = zoneinfo.ZoneInfo("UTC")
                        now_local = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
                        msg = (
                            f"🛡 <b>{post['author_name']} Update</b>\n\n"
                            f"{post['text']}\n\n"
                            f"🕐 {now_local}\n"
                            f"👉 <a href='{post['post_url']}'>View on Bluesky</a>"
                        )
                        await self.broadcast_telegram(user_group, msg)
        except Exception as e:
            logger.error("Error checking Classic Bluesky: %s", e)
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
            await self.check_wow_bluesky()
            await self.check_classic_bluesky()
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
