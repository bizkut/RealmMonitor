import asyncio
import logging
from datetime import datetime, timezone
from atproto import AsyncClient
import database

logger = logging.getLogger(__name__)

class BlueskyFetcher:
    """Fetches updates from a specific Bluesky account using ATProto."""

    def __init__(self, handle: str, app_password: str, target_account: str = "support.blizzard.com"):
        self.handle = handle
        self.app_password = app_password
        self.target_account = target_account
        self.client = AsyncClient()
        self._authenticated = False
        logger.info("BlueskyFetcher for %s initialized.", target_account)

    async def authenticate(self):
        """Authenticate with the Bluesky server."""
        try:
            await self.client.login(self.handle, self.app_password)
            self._authenticated = True
            logger.info("Successfully authenticated with Bluesky.")
        except Exception as e:
            logger.error("Failed to authenticate with Bluesky: %s", e)
            self._authenticated = False

    async def fetch_new_posts(self) -> list[dict]:
        """
        Fetch new posts from the target account.
        Uses a DB-persisted last_seen_uri to ensure each post is only ever
        forwarded once, even across restarts.
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

            # Load the last URI we already sent, from persistent DB storage
            last_seen_uri = await database.get_bluesky_state(self.target_account)

            if last_seen_uri is None:
                # First run: silently record the latest post as baseline, send nothing.
                latest_uri = feed.feed[0].post.uri
                await database.update_bluesky_state(self.target_account, latest_uri)
                logger.info("BlueskyFetcher[%s]: First run, bootstrapped last_seen_uri.", self.target_account)
                return []

            new_posts = []
            for item in feed.feed:
                uri = item.post.uri

                # Stop when we hit a post we've already seen
                if uri == last_seen_uri:
                    break

                # Skip replies and reposts (original posts only)
                if item.reply or item.reason:
                    continue

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

            if new_posts:
                # Persist the newest URI so we don't re-send on next poll
                newest_uri = feed.feed[0].post.uri
                await database.update_bluesky_state(self.target_account, newest_uri)
                logger.info("BlueskyFetcher[%s]: %d new post(s), advanced last_seen_uri.", self.target_account, len(new_posts))

            # Process chronologically (oldest first)
            new_posts.reverse()
            return new_posts

        except Exception as e:
            logger.error("Error fetching Bluesky feed for %s: %s", self.target_account, e)
            return []
