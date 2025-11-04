# database.py
DB_PATH = "/app/data/chemeng_bot.db"
import aiosqlite
from config import DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")

        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                national_id TEXT,
                student_id TEXT,
                phone TEXT,
                created_at TEXT
            );

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
                deactivation_reason TEXT
            );

            CREATE TABLE IF NOT EXISTS registrations (
                registration_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event_id INTEGER,
                registered_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id),
                FOREIGN KEY(event_id) REFERENCES events(event_id)
            );

            CREATE TABLE IF NOT EXISTS payments (
                payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event_id INTEGER,
                amount INTEGER,
                confirmed_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id),
                FOREIGN KEY(event_id) REFERENCES events(event_id)
            );

            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                added_at TEXT
            );

            CREATE TABLE IF NOT EXISTS operator_messages (
                message_id INTEGER PRIMARY KEY,
                chat_id INTEGER,
                user_id INTEGER,
                event_id INTEGER,
                message_type TEXT,
                sent_at TEXT
            );

            CREATE TABLE IF NOT EXISTS feedback_requests (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER UNIQUE,
                sent_at TEXT,
                deadline TEXT
            );

            CREATE TABLE IF NOT EXISTS feedbacks (
                feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event_id INTEGER,
                rating INTEGER CHECK(rating BETWEEN 1 AND 5),
                submitted_at TEXT,
                UNIQUE(user_id, event_id)
            );
        """)
        await db.commit()
