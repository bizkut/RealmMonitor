import asyncio
import logging
from datetime import datetime, timezone
from atproto import AsyncClient

logger = logging.getLogger(__name__)

class BlueskyFetcher:
    """Fetches updates from a specific Bluesky account using ATProto."""

    def __init__(self, handle: str, app_password: str, target_account: str = "support.blizzard.com"):
        self.handle = handle
        self.app_password = app_password
        self.target_account = target_account
        self.client = AsyncClient()
        self._authenticated = False
        # Only posts created AFTER this timestamp will be forwarded
        self._start_time = datetime.now(timezone.utc)
        logger.info("BlueskyFetcher for %s initialized. Will only forward posts after %s", 
                     target_account, self._start_time.isoformat())

    async def authenticate(self):
        """Authenticate with the Bluesky server."""
        try:
            await self.client.login(self.handle, self.app_password)
            self._authenticated = True
            logger.info("Successfully authenticated with Bluesky.")
        except Exception as e:
            logger.error("Failed to authenticate with Bluesky: %s", e)
            self._authenticated = False

    def _parse_post_time(self, item) -> datetime | None:
        """Parse the indexed_at timestamp from a feed item."""
        try:
            post_time_str = getattr(item.post, 'indexed_at', None)
            if isinstance(post_time_str, str):
                return datetime.fromisoformat(post_time_str.replace('Z', '+00:00'))
            elif isinstance(post_time_str, datetime):
                return post_time_str
        except Exception as e:
            logger.warning("Could not parse post time: %s", e)
        return None

    async def fetch_new_posts(self) -> list[dict]:
        """
        Fetch new posts from the target account.
        Only returns posts created AFTER the bot started.
        """
        if not self._authenticated:
            await self.authenticate()
            if not self._authenticated:
                return []

        try:
            feed = await self.client.app.bsky.feed.get_author_feed({
                'actor': self.target_account,
                'limit': 10
            })

            if not feed.feed:
                return []

            new_posts = []
            for item in feed.feed:
                # Skip replies and reposts (original posts only)
                if item.reply or item.reason:
                    continue

                # Only forward posts created AFTER bot start time
                post_time = self._parse_post_time(item)
                if post_time is None or post_time <= self._start_time:
                    continue

                uri = item.post.uri
                text = getattr(item.post.record, 'text', '')
                is_maintenance = "MAINTENANCE SCHEDULE" in text.upper()

                # Build direct post URL
                rkey = uri.split('/')[-1]
                author_handle = getattr(item.post.author, 'handle', self.target_account)
                post_url = f"https://bsky.app/profile/{author_handle}/post/{rkey}"

                new_posts.append({
                    'uri': uri,
                    'text': text,
                    'is_maintenance': is_maintenance,
                    'post_url': post_url,
                    'author_name': getattr(item.post.author, 'display_name', self.target_account)
                })

            # Process chronologically (oldest first)
            new_posts.reverse()
            return new_posts

        except Exception as e:
            logger.error("Error fetching Bluesky feed: %s", e)
            return []
