import asyncio
import logging
from atproto import AsyncClient

logger = logging.getLogger(__name__)

class BlueskyFetcher:
    """Fetches updates from a specific Bluesky account using ATProto."""

    def __init__(self, handle: str, app_password: str, target_account: str = "support.blizzard.com"):
        self.handle = handle
        self.app_password = app_password
        self.target_account = target_account
        self.client = AsyncClient()
        self.last_seen_uri = None
        self._authenticated = False

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
        Returns a list of dicts: [{'uri': ..., 'text': ..., 'is_maintenance': bool}]
        """
        if not self._authenticated:
            await self.authenticate()
            if not self._authenticated:
                return []

        try:
            # Fetch author feed
            feed = await self.client.app.bsky.feed.get_author_feed({
                'actor': self.target_account,
                'limit': 5
            })

            if not feed.feed:
                return []

            if self.last_seen_uri is None:
                # On first run, don't alert on old posts, just set the baseline
                self.last_seen_uri = feed.feed[0].post.uri
                # We also assume we don't want to alert on startup, so return []
                return []

            new_posts = []
            for item in feed.feed:
                uri = item.post.uri
                
                # Skip replies and reposts (original posts only)
                if item.reply or item.reason:
                    continue
                
                # If we've hit the last seen post, we can stop evaluating older posts
                if self.last_seen_uri == uri:
                    break

                text = getattr(item.post.record, 'text', '')
                is_maintenance = "MAINTENANCE SCHEDULE" in text.upper()
                
                # Extract rkey from uri: at://did:.../app.bsky.feed.post/rkey
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

            # The feed is sorted newest first. 
            # We want to process them chronologically (oldest new post first).
            new_posts.reverse()

            if new_posts:
                # Update the last seen URI to the most recent one
                self.last_seen_uri = feed.feed[0].post.uri

            return new_posts

        except Exception as e:
            logger.error("Error fetching Bluesky feed: %s", e)
            return []
