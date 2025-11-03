# database.py
import aiosqlite
from datetime import datetime
from config import DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                national_id TEXT,
                student_id TEXT,
                phone TEXT,
                created_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                type TEXT,
                date TEXT,
                location TEXT,
                capacity INTEGER,
                current_capacity INTEGER DEFAULT 0,
                description TEXT,
                is_active INTEGER DEFAULT 1,
                hashtag TEXT,
                cost INTEGER,
                card_number TEXT,
                deactivation_reason TEXT,
                feedback_sent INTEGER DEFAULT 0
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS registrations (
                registration_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event_id INTEGER,
                registered_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id),
                FOREIGN KEY(event_id) REFERENCES events(event_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event_id INTEGER,
                amount INTEGER,
                confirmed_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id),
                FOREIGN KEY(event_id) REFERENCES events(event_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                added_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS operator_messages (
                message_id INTEGER PRIMARY KEY,
                chat_id INTEGER,
                user_id INTEGER,
                event_id INTEGER,
                message_type TEXT,
                sent_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                rating_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event_id INTEGER,
                rating INTEGER,
                rated_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id),
                FOREIGN KEY(event_id) REFERENCES events(event_id)
            )
        """)
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.commit()

async def get_user_info(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return await cursor.fetchone()

async def get_admin_info(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("SELECT * FROM admins WHERE user_id = ?", (user_id,))
        return await cursor.fetchone()

# Add other db functions similarly, making them async with aiosqlite
# For example:
async def get_event(event_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute("SELECT * FROM events WHERE event_id = ?", (event_id,))
        return await cursor.fetchone()

# ... (implement all other db interactions as async)
