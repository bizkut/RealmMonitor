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
                bluesky_pref TEXT DEFAULT 'none' -- 'none', 'maintenance', 'all'
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_realms (
                chat_id INTEGER,
                region TEXT,
                slug TEXT,
                name TEXT,
                PRIMARY KEY (chat_id, region, slug)
            )
        ''')
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
    """Update Bluesky preference for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'UPDATE users SET bluesky_pref = ? WHERE chat_id = ?',
            (pref, chat_id)
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

async def add_realm(chat_id: int, region: str, slug: str, name: str):
    """Add a realm to the user's monitor list."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT OR IGNORE INTO user_realms (chat_id, region, slug, name) VALUES (?, ?, ?, ?)',
            (chat_id, region, slug, name)
        )
        await db.commit()

async def remove_realm(chat_id: int, region: str, slug: str):
    """Remove a realm from the user's monitor list."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'DELETE FROM user_realms WHERE chat_id = ? AND region = ? AND slug = ?',
            (chat_id, region, slug)
        )
        await db.commit()

async def get_user_realms(chat_id: int) -> list[tuple[str, str, str]]:
    """Get all realms monitored by a specific user. Returns (region, slug, name)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT region, slug, name FROM user_realms WHERE chat_id = ?', (chat_id,)) as cursor:
            return await cursor.fetchall()
    return []

async def get_unique_realms() -> list[tuple[str, str, str]]:
    """Get a list of unique realms being monitored across all users. Returns (region, slug, name)."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Group by region and slug to get unique realms to monitor
        async with db.execute('SELECT region, slug, MAX(name) FROM user_realms GROUP BY region, slug') as cursor:
            return await cursor.fetchall()
    return []

async def get_users_for_realm(region: str, slug: str) -> list[int]:
    """Get all chat_ids monitoring a specific realm."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT chat_id FROM user_realms WHERE region = ? AND slug = ?', (region, slug)) as cursor:
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

async def get_total_realms() -> int:
    """Return total number of tracked realms across all users."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT COUNT(*) FROM user_realms') as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
    return 0
