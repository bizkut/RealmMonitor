import os
import aiosqlite
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "data/bot.db")

async def init_db():
    """Initialize the SQLite database with required tables."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                bluesky_pref TEXT DEFAULT 'none', -- 'none', 'maintenance', 'all'
                wow_bluesky_pref TEXT DEFAULT 'none', -- 'none', 'all'
                classic_bluesky_pref TEXT DEFAULT 'none', -- 'none', 'all'
                timezone TEXT DEFAULT 'UTC'
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_realms (
                chat_id INTEGER,
                region TEXT,
                slug TEXT,
                name TEXT,
                game_version TEXT DEFAULT 'retail',
                PRIMARY KEY (chat_id, region, slug, game_version)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS bluesky_state (
                target_account TEXT PRIMARY KEY,
                last_seen_uri TEXT
            )
        ''')
        
        # Migration: Add game_version to existing tables if missing and recreate constraint
        async with db.execute("PRAGMA table_info(user_realms)") as cursor:
            columns = [col[1] for col in await cursor.fetchall()]
            if 'game_version' not in columns:
                await db.execute("ALTER TABLE user_realms RENAME TO user_realms_old")
                await db.execute('''
                    CREATE TABLE user_realms (
                        chat_id INTEGER,
                        region TEXT,
                        slug TEXT,
                        name TEXT,
                        game_version TEXT DEFAULT 'retail',
                        PRIMARY KEY (chat_id, region, slug, game_version)
                    )
                ''')
                await db.execute("INSERT INTO user_realms (chat_id, region, slug, name) SELECT chat_id, region, slug, name FROM user_realms_old")
                await db.execute("DROP TABLE user_realms_old")
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS known_realms (
                region TEXT,
                game_version TEXT,
                slug TEXT,
                name TEXT,
                PRIMARY KEY (region, game_version, slug)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS known_realms_meta (
                region TEXT,
                game_version TEXT,
                last_updated REAL,
                PRIMARY KEY (region, game_version)
            )
        ''')
        # Migration: Add wow_bluesky_pref to users if missing
        try:
            await db.execute('ALTER TABLE users ADD COLUMN wow_bluesky_pref TEXT DEFAULT "none"')
        except aiosqlite.OperationalError:
            pass # Column already exists
            
        # Migration: Add classic_bluesky_pref to users if missing
        try:
            await db.execute('ALTER TABLE users ADD COLUMN classic_bluesky_pref TEXT DEFAULT "none"')
        except aiosqlite.OperationalError:
            pass # Column already exists
            
        # Migration: Add timezone to users if missing
        try:
            await db.execute('ALTER TABLE users ADD COLUMN timezone TEXT DEFAULT "UTC"')
        except aiosqlite.OperationalError:
            pass # Column already exists
            
        await db.commit()
    logger.info("Database initialized at %s", DB_PATH)

async def register_user(chat_id: int):
    """Ensure a user exists in the database."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT OR IGNORE INTO users (chat_id) VALUES (?)',
            (chat_id,)
        )
        await db.commit()

async def update_bluesky_pref(chat_id: int, pref: str):
    """Update Support Bluesky preference for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'UPDATE users SET bluesky_pref = ? WHERE chat_id = ?',
            (pref, chat_id)
        )
        await db.commit()

async def update_wow_bluesky_pref(chat_id: int, pref: str):
    """Update Official WoW Bluesky preference for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'UPDATE users SET wow_bluesky_pref = ? WHERE chat_id = ?',
            (pref, chat_id)
        )
        await db.commit()

async def update_classic_bluesky_pref(chat_id: int, pref: str):
    """Update WoW Classic Devs Bluesky preference for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'UPDATE users SET classic_bluesky_pref = ? WHERE chat_id = ?',
            (pref, chat_id)
        )
        await db.commit()

async def update_user_timezone(chat_id: int, timezone: str):
    """Update timezone preference for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'UPDATE users SET timezone = ? WHERE chat_id = ?',
            (timezone, chat_id)
        )
        await db.commit()

async def get_bluesky_pref(chat_id: int) -> str:
    """Get Bluesky preference for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT bluesky_pref FROM users WHERE chat_id = ?', (chat_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 'none'
    return 'none'

async def get_bluesky_subscribers(pref_match: list[str]) -> list[int]:
    """Get all chat_ids subscribed to one of the provided bluesky_pref types."""
    async with aiosqlite.connect(DB_PATH) as db:
        placeholders = ','.join(['?'] * len(pref_match))
        query = f'SELECT chat_id FROM users WHERE bluesky_pref IN ({placeholders})'
        async with db.execute(query, pref_match) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]
    return []

async def get_wow_bluesky_pref(chat_id: int) -> str:
    """Get Official WoW Bluesky preference for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT wow_bluesky_pref FROM users WHERE chat_id = ?', (chat_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 'none'
    return 'none'

async def get_wow_bluesky_subscribers(pref_match: list[str]) -> list[int]:
    """Get all chat_ids subscribed to one of the provided wow_bluesky_pref types."""
    async with aiosqlite.connect(DB_PATH) as db:
        placeholders = ','.join(['?'] * len(pref_match))
        query = f'SELECT chat_id FROM users WHERE wow_bluesky_pref IN ({placeholders})'
        async with db.execute(query, pref_match) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]
    return []

async def get_classic_bluesky_pref(chat_id: int) -> str:
    """Get WoW Classic Devs Bluesky preference for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT classic_bluesky_pref FROM users WHERE chat_id = ?', (chat_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 'none'
    return 'none'

async def get_classic_bluesky_subscribers(pref_match: list[str]) -> list[int]:
    """Get all chat_ids subscribed to one of the provided classic_bluesky_pref types."""
    async with aiosqlite.connect(DB_PATH) as db:
        placeholders = ','.join(['?'] * len(pref_match))
        query = f'SELECT chat_id FROM users WHERE classic_bluesky_pref IN ({placeholders})'
        async with db.execute(query, pref_match) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]
    return []

async def get_user_timezone(chat_id: int) -> str:
    """Get timezone preference for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT timezone FROM users WHERE chat_id = ?', (chat_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 'UTC'
    return 'UTC'

async def get_users_by_timezone(chat_ids: list[int]) -> dict[str, list[int]]:
    """Group a list of chat_ids by their timezone preference."""
    if not chat_ids:
        return {}
        
    async with aiosqlite.connect(DB_PATH) as db:
        placeholders = ','.join(['?'] * len(chat_ids))
        query = f'SELECT chat_id, timezone FROM users WHERE chat_id IN ({placeholders})'
        async with db.execute(query, chat_ids) as cursor:
            rows = await cursor.fetchall()
            tz_map = {}
            for cid, tz in rows:
                if tz not in tz_map:
                    tz_map[tz] = []
                tz_map[tz].append(cid)
            return tz_map
    return {}

async def get_bluesky_state(target_account: str) -> str | None:
    """Get the last seen URI for a Bluesky account."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT last_seen_uri FROM bluesky_state WHERE target_account = ?', (target_account,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def update_bluesky_state(target_account: str, uri: str):
    """Update the last seen URI for a Bluesky account."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''INSERT INTO bluesky_state (target_account, last_seen_uri) 
               VALUES (?, ?) 
               ON CONFLICT(target_account) DO UPDATE SET last_seen_uri=excluded.last_seen_uri''',
            (target_account, uri)
        )
        await db.commit()

async def add_realm(chat_id: int, region: str, slug: str, name: str, game_version: str = 'retail'):
    """Add a realm to the user's monitor list."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT OR IGNORE INTO user_realms (chat_id, region, slug, name, game_version) VALUES (?, ?, ?, ?, ?)',
            (chat_id, region, slug, name, game_version)
        )
        await db.commit()

async def remove_realm(chat_id: int, region: str, slug: str, game_version: str = 'retail'):
    """Remove a realm from the user's monitor list."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'DELETE FROM user_realms WHERE chat_id = ? AND region = ? AND slug = ? AND game_version = ?',
            (chat_id, region, slug, game_version)
        )
        await db.commit()

async def get_user_realms(chat_id: int) -> list[tuple[str, str, str, str]]:
    """Get all realms monitored by a specific user. Returns (region, slug, name, game_version)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT region, slug, name, game_version FROM user_realms WHERE chat_id = ?', (chat_id,)) as cursor:
            return await cursor.fetchall()
    return []

async def get_unique_realms() -> list[tuple[str, str, str, str]]:
    """Get a list of unique realms being monitored across all users. Returns (region, slug, name, game_version)."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Group by region, slug, and game_version to get unique realms to monitor
        async with db.execute('SELECT region, slug, MAX(name), game_version FROM user_realms GROUP BY region, slug, game_version') as cursor:
            return await cursor.fetchall()
    return []

async def get_users_for_realm(region: str, slug: str, game_version: str) -> list[int]:
    """Get all chat_ids monitoring a specific realm."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT chat_id FROM user_realms WHERE region = ? AND slug = ? AND game_version = ?', (region, slug, game_version)) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]
    return []

async def get_admin() -> int | None:
    """Return the first registered user as admin."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT chat_id FROM users ORDER BY rowid ASC LIMIT 1') as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def get_total_users() -> int:
    """Return total number of registered users."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM users') as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
    return 0

import time

async def is_realm_index_expired(region: str, game_version: str) -> bool:
    """Returns True if the known_realms cache for this region/version is older than 24h or missing."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            'SELECT last_updated FROM known_realms_meta WHERE region = ? AND game_version = ?',
            (region, game_version)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return True
            last_updated = row[0]
            # Expire after 24 hours (86400 seconds)
            if time.time() - last_updated > 86400:
                return True
            return False

async def update_realm_index(region: str, game_version: str, realms: list[dict]):
    """Bulk upsert known realms into the cache and update the meta timestamp."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Clear old cache for this region/version
        await db.execute(
            'DELETE FROM known_realms WHERE region = ? AND game_version = ?',
            (region, game_version)
        )
        
        # Insert new records
        insert_data = [
            (region, game_version, r['slug'], r.get('name', r['slug']))
            for r in realms
        ]
        await db.executemany(
            'INSERT INTO known_realms (region, game_version, slug, name) VALUES (?, ?, ?, ?)',
            insert_data
        )
        
        # Update meta timestamp
        await db.execute(
            '''INSERT INTO known_realms_meta (region, game_version, last_updated) 
               VALUES (?, ?, ?) 
               ON CONFLICT(region, game_version) DO UPDATE SET last_updated=excluded.last_updated''',
            (region, game_version, time.time())
        )
        await db.commit()

async def find_known_realm(region: str, game_version: str, search_term: str) -> tuple[str, str] | None:
    """Search for an exact/case-insensitive match for a realm in the cached index.
       Returns (slug, official_name) or None."""
    
    # Try slug match first
    search_slug = search_term.strip().lower().replace(" ", "-").replace("'", "")
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            'SELECT slug, name FROM known_realms WHERE region = ? AND game_version = ? AND slug = ?',
            (region, game_version, search_slug)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return (row[0], row[1])
                
        # Try a direct name match (case-insensitive) just in case
        async with db.execute(
            'SELECT slug, name FROM known_realms WHERE region = ? AND game_version = ? AND LOWER(name) = ?',
            (region, game_version, search_term.strip().lower())
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return (row[0], row[1])

    return None

async def get_total_realms() -> int:
    """Return total number of tracked realms across all users."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM user_realms') as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
    return 0
