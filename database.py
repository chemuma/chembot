# database.py
import aiosqlite
from datetime import datetime
from typing import Optional, List, Dict, Any
from config import DB_PATH

# تنظیمات اتصال به دیتابیس
DATABASE_URL = DB_PATH
WAL_MODE = True  # فعال‌سازی Write-Ahead Logging برای عملکرد بهتر در حالت همزمان


async def init_db() -> None:
    """
    ایجاد دیتابیس و جداول در صورت عدم وجود.
    استفاده از row_factory برای دسترسی به ستون‌ها با نام.
    فعال‌سازی WAL برای عملکرد بهتر.
    """
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row

        # --- جدول کاربران ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                national_id TEXT UNIQUE NOT NULL,
                student_id TEXT UNIQUE NOT NULL,
                phone TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # --- جدول رویدادها ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('دوره', 'بازدید')),
                date TEXT NOT NULL,
                location TEXT NOT NULL,
                capacity INTEGER,  -- NULL = نامحدود
                current_capacity INTEGER DEFAULT 0,
                description TEXT,
                is_active INTEGER DEFAULT 1,
                hashtag TEXT,
                cost INTEGER DEFAULT 0,
                card_number TEXT,
                deactivation_reason TEXT,
                feedback_sent INTEGER DEFAULT 0
            )
        """)

        # --- جدول ثبت‌نام‌ها ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS registrations (
                registration_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_id INTEGER NOT NULL,
                registered_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY(event_id) REFERENCES events(event_id) ON DELETE CASCADE,
                UNIQUE(user_id, event_id)
            )
        """)

        # --- جدول پرداخت‌ها ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                confirmed_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY(event_id) REFERENCES events(event_id) ON DELETE CASCADE
            )
        """)

        # --- جدول ادمین‌ها ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                added_at TEXT NOT NULL
            )
        """)

        # --- جدول پیام‌های اپراتور ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS operator_messages (
                message_id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                event_id INTEGER,
                message_type TEXT NOT NULL,
                sent_at TEXT NOT NULL
            )
        """)

        # --- جدول امتیازدهی (جدید) ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                rating_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_id INTEGER NOT NULL,
                rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
                rated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY(event_id) REFERENCES events(event_id) ON DELETE CASCADE,
                UNIQUE(user_id, event_id)
            )
        """)

        # --- فعال‌سازی WAL ---
        if WAL_MODE:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")
            await db.execute("PRAGMA cache_size=10000;")

        await db.commit()


# ==============================
# توابع کمکی دسترسی به دیتابیس
# ==============================

async def fetch_one(query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    """اجرای کوئری و برگرداندن یک ردیف به صورت دیکشنری"""
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def fetch_all(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """اجرای کوئری و برگرداندن همه ردیف‌ها به صورت لیست دیکشنری"""
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def execute(query: str, params: tuple = ()) -> int:
    """اجرای کوئری INSERT/UPDATE/DELETE و برگرداندن lastrowid"""
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(query, params)
        await db.commit()
        return db.total_changes


async def execute_many(query: str, params_list: List[tuple]) -> None:
    """اجرای چندین کوئری INSERT/UPDATE"""
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        await db.executemany(query, params_list)
        await db.commit()


# ==============================
# توابع خاص برای کاربران
# ==============================

async def get_user_info(user_id: int) -> Optional[Dict]:
    return await fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))


async def create_user(user_id: int, full_name: str, national_id: str, student_id: str, phone: str) -> None:
    await execute("""
        INSERT INTO users (user_id, full_name, national_id, student_id, phone, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, full_name, national_id, student_id, phone, datetime.now().isoformat()))


async def update_user_field(user_id: int, field: str, value: str) -> None:
    await execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))


# ==============================
# توابع خاص برای ادمین‌ها
# ==============================

async def get_admin_info(user_id: int) -> Optional[Dict]:
    return await fetch_one("SELECT * FROM admins WHERE user_id = ?", (user_id,))


async def add_admin(user_id: int) -> None:
    await execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)",
                  (user_id, datetime.now().isoformat()))


async def remove_admin(user_id: int) -> None:
    await execute("DELETE FROM admins WHERE user_id = ?", (user_id,))


# ==============================
# توابع خاص برای رویدادها
# ==============================

async def get_event(event_id: int) -> Optional[Dict]:
    return await fetch_one("SELECT * FROM events WHERE event_id = ?", (event_id,))


async def get_active_events() -> List[Dict]:
    return await fetch_all("SELECT event_id, title, type FROM events WHERE is_active = 1 ORDER BY event_id DESC")


async def get_all_events() -> List[Dict]:
    return await fetch_all("SELECT event_id, title, type, is_active FROM events ORDER BY event_id DESC")


async def create_event(title: str, type_: str, date: str, location: str, capacity: Optional[int],
                       description: str, hashtag: str, cost: int, card_number: str) -> int:
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            INSERT INTO events (title, type, date, location, capacity, description, hashtag, cost, card_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (title, type_, date, location, capacity, description, hashtag, cost, card_number))
        await db.commit()
        return cursor.lastrowid


async def update_event_field(event_id: int, field: str, value: Any) -> None:
    await execute(f"UPDATE events SET {field} = ? WHERE event_id = ?", (value, event_id))


async def deactivate_event(event_id: int, reason: str) -> None:
    await execute("""
        UPDATE events SET is_active = 0, deactivation_reason = ? WHERE event_id = ?
    """, (reason, event_id))


async def activate_event(event_id: int) -> None:
    await execute("""
        UPDATE events SET is_active = 1, deactivation_reason = NULL WHERE event_id = ?
    """, (event_id,))


async def increment_event_capacity(event_id: int) -> None:
    await execute("""
        UPDATE events SET current_capacity = current_capacity + 1 WHERE event_id = ?
    """, (event_id,))


# ==============================
# ثبت‌نام و امتیازدهی
# ==============================

async def register_user_to_event(user_id: int, event_id: int) -> bool:
    """ثبت‌نام کاربر — در صورت موفقیت True برمی‌گرداند"""
    try:
        await execute("""
            INSERT INTO registrations (user_id, event_id, registered_at)
            VALUES (?, ?, ?)
        """, (user_id, event_id, datetime.now().isoformat()))
        await increment_event_capacity(event_id)
        return True
    except aiosqlite.IntegrityError:
        return False  # قبلاً ثبت‌نام کرده یا خطای یکتا


async def get_registrations_for_event(event_id: int) -> List[Dict]:
    return await fetch_all("""
        SELECT u.user_id, u.full_name, u.national_id, u.student_id, u.phone, r.registered_at
        FROM users u
        JOIN registrations r ON u.user_id = r.user_id
        WHERE r.event_id = ?
        ORDER BY r.registered_at
    """, (event_id,))


async def get_user_registration_count(event_id: int) -> int:
    row = await fetch_one("SELECT COUNT(*) as count FROM registrations WHERE event_id = ?", (event_id,))
    return row['count'] if row else 0


async def submit_rating(user_id: int, event_id: int, rating: int) -> bool:
    """ثبت امتیاز — در صورت موفقیت True"""
    try:
        await execute("""
            INSERT INTO ratings (user_id, event_id, rating, rated_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, event_id, rating, datetime.now().isoformat()))
        return True
    except aiosqlite.IntegrityError:
        return False  # قبلاً امتیاز داده


async def get_average_rating(event_id: int) -> Optional[float]:
    row = await fetch_one("""
        SELECT AVG(rating) as avg_rating FROM ratings WHERE event_id = ?
    """, (event_id,))
    return round(row['avg_rating'], 1) if row and row['avg_rating'] else None


async def has_user_rated(user_id: int, event_id: int) -> bool:
    row = await fetch_one("""
        SELECT 1 FROM ratings WHERE user_id = ? AND event_id = ?
    """, (user_id, event_id))
    return bool(row)


async def mark_feedback_sent(event_id: int) -> None:
    await execute("UPDATE events SET feedback_sent = 1 WHERE event_id = ?", (event_id,))


async def is_feedback_sent(event_id: int) -> bool:
    row = await fetch_one("SELECT feedback_sent FROM events WHERE event_id = ?", (event_id,))
    return bool(row and row['feedback_sent'])
