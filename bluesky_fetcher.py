import asyncio
import logging
from atproto import AsyncClient

logger = logging.getLogger(__name__)

class BlueskyFetcher:
    """Fetches updates from a specific Bluesky account using ATProto."""

    def __init__(self, handle: str, app_password: str, target_account: str = "support.blizzard.com", last_seen_uri: str = None):
        self.handle = handle
        self.app_password = app_password
        self.target_account = target_account
        self.client = AsyncClient()
        self.last_seen_uri = last_seen_uri
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
                # On first run (if no persistent state), don't alert on old posts, just set baseline
                self.last_seen_uri = feed.feed[0].post.uri
                return []

            new_posts = []
            # Cache current latest to update state at the end
            latest_uri_in_feed = feed.feed[0].post.uri
            
            # Use current time/baseline to avoid very old posts
            from datetime import datetime, timezone, timedelta
            now = datetime.now(timezone.utc)
            max_age = timedelta(hours=24)

            for item in feed.feed:
                uri = item.post.uri
                
                # If we've hit the last seen post, we can stop evaluating older posts
                if self.last_seen_uri == uri:
                    break
                
                # Skip replies and reposts (original posts only)
                if item.reply or item.reason:
                    continue
                
                # Time-based safety filter: skip posts older than 24h
                try:
                    # indexed_at is typically ISO 8601 string: 2024-03-24T16:41:13.123Z
                    # SDK may return it as string or datetime depending on version
                    post_time_str = getattr(item.post, 'indexed_at', None)
                    if isinstance(post_time_str, str):
                        # Simple parse for UTC (replacing Z with +00:00)
                        post_time = datetime.fromisoformat(post_time_str.replace('Z', '+00:00'))
                    else:
                        post_time = post_time_str # Hopefully a datetime object
                    
                    if post_time and (now - post_time) > max_age:
                        continue
                except Exception as te:
                    logger.warning("Could not parse post time for %s: %s", uri, te)

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

            # Always update the last seen URI to the most recent one we've encountered
            if feed.feed:
                self.last_seen_uri = latest_uri_in_feed

            return new_posts

        except Exception as e:
            logger.error("Error fetching Bluesky feed: %s", e)
            return []
