"""Blizzard Battle.net API client for WoW realm status."""

import time
import logging
import aiohttp

logger = logging.getLogger(__name__)

# Region to API host mapping
REGION_HOSTS = {
    "us": "us.api.blizzard.com",
    "eu": "eu.api.blizzard.com",
    "kr": "kr.api.blizzard.com",
    "tw": "tw.api.blizzard.com",
}

OAUTH_URL = "https://oauth.battle.net/token"


class BlizzardAPI:
    """Handles Blizzard API authentication and realm status queries."""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: str | None = None
        self._token_expiry: float = 0
        # Cache: realm_slug -> connected_realm_id
        self._realm_id_cache: dict[str, int] = {}

    async def _ensure_token(self, session: aiohttp.ClientSession) -> str:
        """Fetch or refresh the OAuth access token if expired."""
        if self._access_token and time.time() < self._token_expiry - 60:
            return self._access_token

        async with session.post(
            OAUTH_URL,
            data={"grant_type": "client_credentials"},
            auth=aiohttp.BasicAuth(self.client_id, self.client_secret),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            self._access_token = data["access_token"]
            self._token_expiry = time.time() + data.get("expires_in", 86400)
            logger.info("OAuth token refreshed, expires in %ds", data.get("expires_in", 0))
            return self._access_token

    async def _get_headers(self, session: aiohttp.ClientSession) -> dict:
        """Get request headers with Bearer token."""
        token = await self._ensure_token(session)
        return {"Authorization": f"Bearer {token}"}

    async def _resolve_realm_id(
        self, session: aiohttp.ClientSession, region: str, realm_slug: str, game_version: str
    ) -> int | None:
        """Look up the connected realm ID for a given realm slug."""
        cache_key = f"{region}_{realm_slug}_{game_version}"
        if cache_key in self._realm_id_cache:
            return self._realm_id_cache[cache_key]

        host = REGION_HOSTS[region]
        headers = await self._get_headers(session)

        # Use the realm endpoint to get the connected realm ID
        url = f"https://{host}/data/wow/realm/{realm_slug}"
        
        ns = f"dynamic-classic-{region}" if game_version == "classic" else (f"dynamic-classic-era-{region}" if game_version == "classic-era" else f"dynamic-{region}")
        params = {"namespace": ns, "locale": "en_US"}

        async with session.get(url, params=params, headers=headers) as resp:
            if resp.status != 200:
                logger.error("Failed to look up realm '%s': HTTP %s", realm_slug, resp.status)
                return None
            data = await resp.json()
            cr_href = data.get("connected_realm", {}).get("href", "")
            # Extract ID from href like .../connected-realm/3725?namespace=...
            try:
                cr_id = int(cr_href.split("/connected-realm/")[1].split("?")[0])
                self._realm_id_cache[cache_key] = cr_id
                logger.info("Resolved realm '%s' (%s) -> connected realm ID %d", realm_slug, game_version, cr_id)
                return cr_id
            except (IndexError, ValueError):
                logger.error("Could not parse connected realm ID from: %s", cr_href)
                return None

    async def get_realm_status(
        self, session: aiohttp.ClientSession, region: str, realm_slug: str, game_version: str = "retail"
    ) -> tuple[dict | None, int]:
        """
        Get the status of a specific realm.

        Returns:
            (realm_data, cache_max_age) where realm_data contains status info
            and cache_max_age is the seconds from Cache-Control header.
        """
        host = REGION_HOSTS.get(region.lower())
        if not host:
            raise ValueError(f"Unknown region: {region}. Use: {list(REGION_HOSTS.keys())}")

        # Resolve the connected realm ID
        cr_id = await self._resolve_realm_id(session, region.lower(), realm_slug, game_version)
        if cr_id is None:
            return None, 0

        headers = await self._get_headers(session)
        url = f"https://{host}/data/wow/connected-realm/{cr_id}"
        
        ns = f"dynamic-classic-{region.lower()}" if game_version == "classic" else (f"dynamic-classic-era-{region.lower()}" if game_version == "classic-era" else f"dynamic-{region.lower()}")
        params = {"namespace": ns, "locale": "en_US"}

        async with session.get(url, params=params, headers=headers) as resp:
            cache_max_age = self._parse_cache_max_age(resp.headers)

            if resp.status != 200:
                logger.error("Failed to get connected realm %d: HTTP %s", cr_id, resp.status)
                return None, cache_max_age

            data = await resp.json()
            status_type = data.get("status", {}).get("type", "UNKNOWN")

            # Find the specific realm name in the connected realm
            realm_name = realm_slug
            for r in data.get("realms", []):
                if r.get("slug", "").lower() == realm_slug.lower():
                    name = r.get("name", realm_slug)
                    if isinstance(name, dict):
                        name = name.get("en_US", realm_slug)
                    realm_name = name
                    break

            return {
                "slug": realm_slug,
                "name": realm_name,
                "status": status_type,  # "UP" or "DOWN"
                "region": region.upper(),
            }, cache_max_age

    @staticmethod
    def _parse_cache_max_age(headers) -> int:
        """Extract max-age from Cache-Control header. Returns seconds."""
        cache_control = headers.get("Cache-Control", "")
        for directive in cache_control.split(","):
            directive = directive.strip()
            if directive.lower().startswith("max-age="):
                try:
                    return int(directive.split("=", 1)[1])
                except (ValueError, IndexError):
                    pass
        return 0

    @staticmethod
    def to_slug(realm_name: str) -> str:
        """Convert a realm name to a slug (e.g., 'Area 52' -> 'area-52')."""
        return realm_name.strip().lower().replace(" ", "-").replace("'", "")
