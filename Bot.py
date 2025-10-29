import os
import re
import sqlite3
import logging
from datetime import datetime, timedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)

# تنظیمات لاگر
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "7996022698:AAG65GXEjbDbgMGFVT9ExeGFmkvj0UDqbXE"
CHANNEL_ID = "@chemical_eng_uma"
OPERATOR_GROUP_ID = -1002574996302
ADMIN_IDS = [5701423397, 158893761]
CARD_NUMBER = "6219-8619-2120-2437"
DB_PATH = "chemeng_bot.db"
DB_PATH = "jehad_ardabil.db"

# === وضعیت‌های گفتگو ===
# ثبت‌نام کاربر
FULL_NAME, CONFIRM_FULL_NAME, NATIONAL_ID, CONFIRM_NATIONAL_ID, STUDENT_ID, CONFIRM_STUDENT_ID, PHONE, CONFIRM_PHONE = range(8)

# ادمین: افزودن رویداد
EVENT_TYPE, EVENT_TITLE, EVENT_DESC, EVENT_COST, EVENT_DATE, EVENT_CAPACITY, CONFIRM_EVENT = range(7)

# ادمین: ویرایش رویداد
EDIT_EVENT_SELECT, EDIT_EVENT_TEXT = range(2)

# ادمین: فعال/غیرفعال
TOGGLE_EVENT = 0

# ادمین: گزارش
REPORT_TYPE, REPORT_EVENT, REPORT_PERIOD = range(3)

# ادمین: اعلان
ANNOUNCE_TARGET, ANNOUNCE_TEXT = range(2)

# ادمین: ثبت دستی
MANUAL_EVENT, MANUAL_STUDENT_ID, CONFIRM_MANUAL = range(3)

# === توابع کمکی ===
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, full_name TEXT, national_id TEXT,
            student_id TEXT, phone TEXT, created_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, type TEXT,
            date TEXT, cost INTEGER, capacity INTEGER, current_capacity INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1, hashtag TEXT, description TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS registrations (
            registration_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, event_id INTEGER, registered_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS payments (
            payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, event_id INTEGER, amount INTEGER, confirmed_at TEXT)""")
        conn.commit()

def validate_national_id(nid: str) -> bool:
    if not re.match(r"^\d{10}$", nid): return False
    check = int(nid[9])
    total = sum(int(nid[i]) * (10 - i) for i in range(9)) % 11
    return (total < 2 and check == total) or (total >= 2 and check == 11 - total)

def get_user(user_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return c.fetchone()

async def check_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, update.effective_user.id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

def main_menu(is_admin=False):
    buttons = [["رویدادهای فعال"], ["ویرایش مشخصات"], ["پشتیبانی"]]
    if is_admin:
        buttons.insert(0, ["پنل ادمین"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def admin_menu():
    return ReplyKeyboardMarkup([
        ["افزودن رویداد", "ویرایش رویداد"],
        ["فعال/غیرفعال", "اعلان عمومی"],
        ["ثبت دستی", "گزارش‌ها"],
        ["بازگشت"]
    ], resize_keyboard=True)

# === شروع ربات ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not await check_channel(update, context):
        await update.message.reply_text(
            f"لطفاً ابتدا در کانال عضو شوید:\n{CHANNEL_ID}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("عضو شدم", callback_data="check_membership")
            ]])
        )
        return ConversationHandler.END

    user = get_user(user_id)
    if not user:
        await update.message.reply_text("نام و نام خانوادگی خود را وارد کنید:")
        return FULL_NAME

    is_admin = user_id in ADMIN_IDS
    await update.message.reply_text(
        f"سلام {user[1]} عزیز!\nبه ربات جهاد دانشگاهی اردبیل خوش آمدید",
        reply_markup=main_menu(is_admin)
    )
    return ConversationHandler.END

async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if await check_channel(update, context):
        return await start(update, context)
    await query.edit_message_text("هنوز عضو کانال نشده‌اید!")
    return ConversationHandler.END

# === ثبت‌نام کاربر ===
async def full_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not re.match(r"^[آ-ی\s]{6,}$", text) or " " not in text:
        await update.message.reply_text("نام کامل باید فارسی و شامل نام و نام خانوادگی باشد.")
        return FULL_NAME
    context.user_data["full_name"] = text
    await update.message.reply_text(f"نام: {text}\nدرست است؟", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("بله", callback_data="yes_name"),
        InlineKeyboardButton("خیر", callback_data="no_name")
    ]]))
    return CONFIRM_FULL_NAME

async def confirm_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "no_name":
        await query.edit_message_text("دوباره نام را وارد کنید:")
        return FULL_NAME
    await query.edit_message_text("کد ملی ۱۰ رقمی:")
    return NATIONAL_ID

async def national_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if not validate_national_id(text):
        await update.message.reply_text("کد ملی نامعتبر است.")
        return NATIONAL_ID
    context.user_data["national_id"] = text
    await update.message.reply_text(f"کد ملی: {text}\nدرست است؟", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("بله", callback_data="yes_nid"),
        InlineKeyboardButton("خیر", callback_data="no_nid")
    ]]))
    return CONFIRM_NATIONAL_ID

async def confirm_nid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "no_nid":
        await query.edit_message_text("دوباره کد ملی:")
        return NATIONAL_ID
    await query.edit_message_text("شماره دانشجویی:")
    return STUDENT_ID

async def student_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if not text.isdigit():
        await update.message.reply_text("فقط عدد وارد کنید.")
        return STUDENT_ID
    context.user_data["student_id"] = text
    await update.message.reply_text(f"شماره دانشجویی: {text}\nدرست است؟", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("بله", callback_data="yes_sid"),
        InlineKeyboardButton("خیر", callback_data="no_sid")
    ]]))
    return CONFIRM_STUDENT_ID

async def confirm_sid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "no_sid":
        await query.edit_message_text("دوباره شماره دانشجویی:")
        return STUDENT_ID
    await query.edit_message_text("شماره تماس (یا دکمه):", reply_markup=ReplyKeyboardMarkup(
        [[KeyboardButton("ارسال شماره", request_contact=True)]], one_time_keyboard=True
    ))
    return PHONE

async def phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.contact:
        phone = update.message.contact.phone_number.replace("+98", "0")
    else:
        phone = update.message.text
        if not re.match(r"^09\d{9}$", phone):
            await update.message.reply_text("شماره باید ۱۱ رقم و با 09 شروع شود.")
            return PHONE
    context.user_data["phone"] = phone
    await update.message.reply_text(f"شماره: {phone}\nدرست است؟", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("بله", callback_data="yes_phone"),
        InlineKeyboardButton("خیر", callback_data="no_phone")
    ]]))
    return CONFIRM_PHONE

async def save_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "no_phone":
        await query.edit_message_text("دوباره شماره:")
        return PHONE

    user_id = update.effective_user.id
    data = context.user_data
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO users (user_id, full_name, national_id, student_id, phone, created_at)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                  (user_id, data["full_name"], data["national_id"], data["student_id"], data["phone"], datetime.now().isoformat()))
        conn.commit()

    await query.edit_message_text("ثبت‌نام موفق!", reply_markup=main_menu(user_id in ADMIN_IDS))
    return ConversationHandler.END

# === نمایش رویدادها ===
async def show_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_channel(update, context):
        await update.message.reply_text(f"عضو کانال شوید: {CHANNEL_ID}")
        return

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT event_id, title, type, cost, current_capacity, capacity FROM events WHERE is_active = 1")
        events = c.fetchall()

    if not events:
        await update.message.reply_text("رویدادی فعال نیست.")
        return

    buttons = []
    for e in events:
        cost = "رایگان" if e[3] == 0 else f"{e[3]:,} تومان"
        cap = "نامحدود" if e[2] == "دوره" else f"{e[5]-e[4]}/{e[5]}"
        buttons.append([InlineKeyboardButton(f"{e[1]} ({cost})", callback_data=f"event_{e[0]}")])
    await update.message.reply_text("رویدادهای فعال:", reply_markup=InlineKeyboardMarkup(buttons))

async def event_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split("_")[1])
    context.user_data["event_id"] = event_id

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM events WHERE event_id = ?", (event_id,))
        event = c.fetchone()

    if not event or not event[7]:
        await query.edit_message_text("رویداد غیرفعال است.")
        return

    cost = "رایگان" if event[4] == 0 else f"{event[4]:,} تومان"
    cap = "نامحدود" if event[2] == "دوره" else f"{event[6] - event[5]}/{event[6]}"

    text = f"""
عنوان: {event[1]}
نوع: {event[2]}
تاریخ: {event[3]}
هزینه: {cost}
ظرفیت: {cap}
توضیحات: {event[9]}
""".strip()

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("ثبت‌نام", callback_data=f"reg_{event_id}")
    ]]))

# === ثبت‌نام در رویداد ===
async def register_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split("_")[1])
    user_id = update.effective_user.id

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM events WHERE event_id = ? AND is_active = 1", (event_id,))
        event = c.fetchone()
        if not event:
            await query.edit_message_text("رویداد غیرفعال است.")
            return

        c.execute("SELECT 1 FROM registrations WHERE user_id = ? AND event_id = ?", (user_id, event_id))
        if c.fetchone():
            await query.edit_message_text("شما قبلاً ثبت‌نام کرده‌اید.")
            return

        if event[2] != "دوره" and event[5] >= event[6]:
            await query.edit_message_text("ظرفیت تکمیل شده.")
            return

    if event[4] == 0:
        await confirm_registration(user_id, event_id, context)
        await query.edit_message_text("ثبت‌نام موفق!")
    else:
        context.user_data["pending_event"] = event_id
        await query.edit_message_text(
            f"مبلغ {event[4]:,} تومان به کارت زیر واریز کنید:\n`{CARD_NUMBER}`\nسپس تصویر رسید را ارسال کنید.",
            parse_mode="Markdown"
        )

async def confirm_registration(user_id, event_id, context):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO registrations (user_id, event_id, registered_at) VALUES (?, ?, ?)",
                  (user_id, event_id, datetime.now().isoformat()))
        c.execute("UPDATE events SET current_capacity = current_capacity + 1 WHERE event_id = ?", (event_id,))
        c.execute("SELECT full_name, national_id, student_id, phone FROM users WHERE user_id = ?", (user_id,))
        user = c.fetchone()
        c.execute("SELECT COUNT(*) FROM registrations WHERE event_id = ?", (event_id,))
        count = c.fetchone()[0]
        conn.commit()

    hashtag = f"#{event[2]}_{event[8].replace(' ', '_')}"
    text = f"{hashtag}\n{count}:\nنام: {user[0]}\nکد ملی: {user[1]}\nشماره دانشجویی: {user[2]}\nتلفن: {user[3]}"
    await context.bot.send_message(OPERATOR_GROUP_ID, text)

async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "pending_event" not in context.user_data:
        return
    event_id = context.user_data["pending_event"]
    user_id = update.effective_user.id

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT title, cost, hashtag FROM events WHERE event_id = ?", (event_id,))
        event = c.fetchone()
        c.execute("SELECT full_name, national_id FROM users WHERE user_id = ?", (user_id,))
        user = c.fetchone()

    text = f"رسید #{event[2]}\nنام: {user[0]}\nکد ملی: {user[1]}\nمبلغ: {event[1]:,} تومان"
    await context.bot.send_photo(
        OPERATOR_GROUP_ID,
        update.message.photo[-1].file_id,
        caption=text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("تأیید", callback_data=f"pay_ok_{user_id}_{event_id}"),
            InlineKeyboardButton("رد", callback_data=f"pay_no_{user_id}_{event_id}")
        ]])
    )
    await update.message.reply_text("رسید ارسال شد.")

async def payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    if data[0] == "pay_ok":
        await confirm_registration(int(data[2]), int(data[3]), context)
        await context.bot.send_message(int(data[2]), "پرداخت تأیید شد!")
    else:
        await context.bot.send_message(int(data[2]), "پرداخت رد شد.")
    await query.message.delete()

# === پنل ادمین ===
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("دسترسی ندارید.")
        return
    await update.message.reply_text("پنل ادمین:", reply_markup=admin_menu())

# افزودن رویداد
async def add_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    await update.message.reply_text("نوع رویداد:", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("دوره", callback_data="دوره")],
        [InlineKeyboardButton("بازدید", callback_data="بازدید")]
    ]))
    return EVENT_TYPE

async def event_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["type"] = query.data
    await query.edit_message_text("عنوان رویداد:")
    return EVENT_TITLE

async def event_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["title"] = update.message.text
    await update.message.reply_text("توضیحات:")
    return EVENT_DESC

async def event_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["desc"] = update.message.text
    await update.message.reply_text("هزینه (0 = رایگان):")
    return EVENT_COST

async def event_cost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cost = update.message.text
    if not cost.isdigit():
        await update.message.reply_text("عدد وارد کنید.")
        return EVENT_COST
    context.user_data["cost"] = int(cost)
    await update.message.reply_text("تاریخ (YYYY-MM-DD):")
    return EVENT_DATE

async def event_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    date = update.message.text
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        await update.message.reply_text("فرمت: YYYY-MM-DD")
        return EVENT_DATE
    context.user_data["date"] = date
    if context.user_data["type"] == "دوره":
        context.user_data["capacity"] = 0
        return await confirm_event_add(update, context)
    await update.message.reply_text("ظرفیت:")
    return EVENT_CAPACITY

async def event_capacity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cap = update.message.text
    if not cap.isdigit() or int(cap) <= 0:
        await update.message.reply_text("عدد مثبت.")
        return EVENT_CAPACITY
    context.user_data["capacity"] = int(cap)
    return await confirm_event_add(update, context)

async def confirm_event_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data
    hashtag = "#" + "_".join(data["title"].split())
    text = f"""
عنوان: {data["title"]}
نوع: {data["type"]}
تاریخ: {data["date"]}
هزینه: {'رایگان' if data["cost"] == 0 else f'{data["cost"]:,} تومان'}
ظرفیت: {'نامحدود' if data["type"] == 'دوره' else data["capacity"]}
توضیحات: {data["desc"]}
""".strip()
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("تأیید", callback_data="save_event"),
        InlineKeyboardButton("لغو", callback_data="cancel_event")
    ]]))
    return CONFIRM_EVENT

async def save_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel_event":
        await query.edit_message_text("لغو شد.", reply_markup=admin_menu())
        return ConversationHandler.END

    data = context.user_data
    hashtag = "#" + "_".join(data["title"].split())
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO events (title, type, date, cost, capacity, hashtag, description, is_active)
                     VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
                  (data["title"], data["type"], data["date"], data["cost"], data["capacity"], hashtag, data["desc"]))
        conn.commit()

    await query.edit_message_text("رویداد اضافه شد!", reply_markup=admin_menu())
    return ConversationHandler.END

# ویرایش رویداد
async def edit_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT event_id, title, type FROM events")
        events = c.fetchall()
    if not events:
        await update.message.reply_text("رویدادی نیست.")
        return ConversationHandler.END
    buttons = [[InlineKeyboardButton(f"{e[1]} ({e[2]})", callback_data=f"edit_select_{e[0]}")] for e in events]
    await update.message.reply_text("رویداد را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
    return EDIT_EVENT_SELECT

async def edit_event_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split("_")[2])
    context.user_data["edit_event_id"] = event_id
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM events WHERE event_id = ?", (event_id,))
        event = c.fetchone()
    text = f"نوع: {event[2]}\nعنوان: {event[1]}\nهشتگ: {event[8]}\nتوضیحات: {event[9]}\nهزینه: {event[4]}\nتاریخ: {event[3]}\nظرفیت: {event[5] if event[2] != 'دوره' else 'نامحدود'}"
    await query.edit_message_text("متن ویرایش شده را وارد کنید:\n" + text)
    return EDIT_EVENT_TEXT

async def save_edited_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    event_id = context.user_data["edit_event_id"]
    lines = [l for l in text.split("\n") if ":" in l]
    data = {}
    for line in lines:
        k, v = line.split(":", 1)
        data[k.strip()] = v.strip()

    required = ["نوع", "عنوان", "هشتگ", "توضیحات", "هزینه", "تاریخ"]
    if event[2] != "دوره":
        required.append("ظرفیت")
    if any(k not in data for k in required):
        await update.message.reply_text("همه فیلدها را پر کنید.")
        return EDIT_EVENT_TEXT

    hashtag = data["هشتگ"]
    cost = 0 if data["هزینه"] == "رایگان" else int(data["هزینه"].replace(",", ""))
    capacity = 0 if data["نوع"] == "دوره" else int(data["ظرفیت"])

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""UPDATE events SET title=?, type=?, date=?, cost=?, capacity=?, hashtag=?, description=?
                     WHERE event_id=?""",
                  (data["عنوان"], data["نوع"], data["تاریخ"], cost, capacity, hashtag, data["توضیحات"], event_id))
        conn.commit()

    await update.message.reply_text("ویرایش شد!", reply_markup=admin_menu())
    return ConversationHandler.END

# فعال/غیرفعال
async def toggle_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT event_id, title, type, is_active FROM events")
        events = c.fetchall()
    buttons = [[InlineKeyboardButton(f"{e[1]} - {'فعال' if e[3] else 'غیرفعال'}", callback_data=f"toggle_{e[0]}")] for e in events]
    await update.message.reply_text("انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
    return TOGGLE_EVENT

async def toggle_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split("_")[1])
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT is_active FROM events WHERE event_id = ?", (event_id,))
        is_active = c.fetchone()[0]
        c.execute("UPDATE events SET is_active = ? WHERE event_id = ?", (0 if is_active else 1, event_id))
        conn.commit()
    await query.edit_message_text(f"وضعیت تغییر کرد: {'غیرفعال' if is_active else 'فعال'}", reply_markup=admin_menu())
    return ConversationHandler.END

# گزارش‌ها
async def report_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    await update.message.reply_text("نوع گزارش:", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("ثبت‌نام‌ها", callback_data="reg_report")],
        [InlineKeyboardButton("مالی", callback_data="fin_report")]
    ]))
    return REPORT_TYPE

async def report_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["report_type"] = query.data
    if query.data == "reg_report":
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT event_id, title FROM events")
            events = c.fetchall()
        buttons = [[InlineKeyboardButton(e[1], callback_data=f"reg_event_{e[0]}")] for e in events]
        await query.edit_message_text("رویداد:", reply_markup=InlineKeyboardMarkup(buttons))
        return REPORT_EVENT
    else:
        await query.edit_message_text("دوره زمانی:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("امروز", callback_data="period_today")],
            [InlineKeyboardButton("هفته", callback_data="period_week")],
            [InlineKeyboardButton("همه", callback_data="period_all")]
        ]))
        return REPORT_PERIOD

async def generate_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    rtype = context.user_data["report_type"]
    if rtype == "reg_report":
        event_id = int(query.data.split("_")[2])
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT title, hashtag FROM events WHERE event_id = ?", (event_id,))
            event = c.fetchone()
            c.execute("""SELECT u.full_name, u.national_id, u.student_id, u.phone
                         FROM users u JOIN registrations r ON u.user_id = r.user_id
                         WHERE r.event_id = ?""", (event_id,))
            regs = c.fetchall()
        text = f"#{event[1]}\n"
        for i, r in enumerate(regs, 1):
            text += f"{i}: {r[0]} / {r[1]} / {r[2]} / {r[3]}\n"
        await query.edit_message_text(text, reply_markup=admin_menu())
    else:
        period = query.data.split("_")[1]
        now = datetime.now()
        start = now if period == "today" else now - timedelta(days=7) if period == "week" else datetime(1970,1,1)
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("""SELECT e.title, u.full_name, p.amount
                         FROM payments p JOIN events e ON p.event_id = e.event_id
                         JOIN users u ON p.user_id = u.user_id
                         WHERE p.confirmed_at >= ?""", (start.isoformat(),))
            payments = c.fetchall()
        text = "گزارش مالی:\n"
        for p in payments:
            text += f"{p[0]} - {p[1]}: {p[2]:,} تومان\n"
        await query.edit_message_text(text or "هیچ پرداختی نیست.", reply_markup=admin_menu())
    return ConversationHandler.END

# اعلان عمومی
async def announce_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT event_id, title FROM events")
        events = c.fetchall()
    buttons = [[InlineKeyboardButton(e[1], callback_data=f"ann_event_{e[0]}")] for e in events]
    buttons.append([InlineKeyboardButton("همه کاربران", callback_data="ann_all")])
    await update.message.reply_text("مخاطب:", reply_markup=InlineKeyboardMarkup(buttons))
    return ANNOUNCE_TARGET

async def announce_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["ann_target"] = query.data
    await query.edit_message_text("متن اعلان:")
    return ANNOUNCE_TEXT

async def send_announcement(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    target = context.user_data["ann_target"]
    if target == "ann_all":
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT user_id FROM users")
            users = c.fetchall()
        for u in users:
            await context.bot.send_message(u[0], f"اطلاعیه:\n{text}")
    else:
        event_id = int(target.split("_")[2])
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT user_id FROM registrations WHERE event_id = ?", (event_id,))
            users = c.fetchall()
        for u in users:
            await context.bot.send_message(u[0], f"رویداد:\n{text}")
    await update.message.reply_text("ارسال شد!", reply_markup=admin_menu())
    return ConversationHandler.END

# ثبت دستی
async def manual_reg_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT event_id, title FROM events WHERE is_active = 1")
        events = c.fetchall()
    buttons = [[InlineKeyboardButton(e[1], callback_data=f"man_event_{e[0]}")] for e in events]
    await update.message.reply_text("رویداد:", reply_markup=InlineKeyboardMarkup(buttons))
    return MANUAL_EVENT

async def manual_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["man_event"] = int(query.data.split("_")[2])
    await query.edit_message_text("شماره دانشجویی:")
    return MANUAL_STUDENT_ID

async def manual_student_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    sid = update.message.text
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, full_name FROM users WHERE student_id = ?", (sid,))
        user = c.fetchone()
    if not user:
        await update.message.reply_text("کاربر یافت نشد.")
        return MANUAL_STUDENT_ID
    context.user_data["man_user"] = user[0]
    await update.message.reply_text(f"کاربر: {user[1]}\nتأیید؟", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("بله", callback_data="man_confirm"),
        InlineKeyboardButton("خیر", callback_data="man_cancel")
    ]]))
    return CONFIRM_MANUAL

async def confirm_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "man_cancel":
        await query.edit_message_text("لغو شد.", reply_markup=admin_menu())
        return ConversationHandler.END
    user_id = context.user_data["man_user"]
    event_id = context.user_data["man_event"]
    await confirm_registration(user_id, event_id, context)
    await query.edit_message_text("ثبت شد!", reply_markup=admin_menu())
    return ConversationHandler.END

# پشتیبانی
async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    info = get_user(user.id)
    identifier = f"@{user.username}" if user.username else info[4]
    await context.bot.send_message(OPERATOR_GROUP_ID, f"پشتیبانی از {identifier}:\n{update.message.text}")
    await update.message.reply_text("پیام ارسال شد.")

# بازگشت
async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("بازگشت به منو", reply_markup=main_menu(user_id in ADMIN_IDS))

# === main ===
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # ثبت‌نام کاربر
    reg_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, full_name)],
            CONFIRM_FULL_NAME: [CallbackQueryHandler(confirm_name)],
            NATIONAL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, national_id)],
            CONFIRM_NATIONAL_ID: [CallbackQueryHandler(confirm_nid)],
            STUDENT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, student_id)],
            CONFIRM_STUDENT_ID: [CallbackQueryHandler(confirm_sid)],
            PHONE: [MessageHandler(filters.CONTACT | filters.TEXT, phone)],
            CONFIRM_PHONE: [CallbackQueryHandler(save_user)],
        },
        fallbacks=[]
    )

    # افزودن رویداد
    add_event_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^افزودن رویداد$"), add_event_start)],
        states={
            EVENT_TYPE: [CallbackQueryHandler(event_type)],
            EVENT_TITLE: [MessageHandler(filters.TEXT, event_title)],
            EVENT_DESC: [MessageHandler(filters.TEXT, event_desc)],
            EVENT_COST: [MessageHandler(filters.TEXT, event_cost)],
            EVENT_DATE: [MessageHandler(filters.TEXT, event_date)],
            EVENT_CAPACITY: [MessageHandler(filters.TEXT, event_capacity)],
            CONFIRM_EVENT: [CallbackQueryHandler(save_event)],
        },
        fallbacks=[]
    )

    # ویرایش رویداد
    edit_event_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^ویرایش رویداد$"), edit_event_start)],
        states={
            EDIT_EVENT_SELECT: [CallbackQueryHandler(edit_event_select)],
            EDIT_EVENT_TEXT: [MessageHandler(filters.TEXT, save_edited_event)],
        },
        fallbacks=[]
    )

    # فعال/غیرفعال
    toggle_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^فعال/غیرفعال$"), toggle_event_start)],
        states={TOGGLE_EVENT: [CallbackQueryHandler(toggle_event)]},
        fallbacks=[]
    )

    # گزارش
    report_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^گزارش‌ها$"), report_start)],
        states={
            REPORT_TYPE: [CallbackQueryHandler(report_type)],
            REPORT_EVENT: [CallbackQueryHandler(generate_report)],
            REPORT_PERIOD: [CallbackQueryHandler(generate_report)],
        },
        fallbacks=[]
    )

    # اعلان
    announce_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^اعلان عمومی$"), announce_start)],
        states={
            ANNOUNCE_TARGET: [CallbackQueryHandler(announce_target)],
            ANNOUNCE_TEXT: [MessageHandler(filters.TEXT, send_announcement)],
        },
        fallbacks=[]
    )

    # ثبت دستی
    manual_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^ثبت دستی$"), manual_reg_start)],
        states={
            MANUAL_EVENT: [CallbackQueryHandler(manual_event)],
            MANUAL_STUDENT_ID: [MessageHandler(filters.TEXT, manual_student_id)],
            CONFIRM_MANUAL: [CallbackQueryHandler(confirm_manual)],
        },
        fallbacks=[]
    )

    app.add_handler(reg_conv)
    app.add_handler(add_event_conv)
    app.add_handler(edit_event_conv)
    app.add_handler(toggle_conv)
    app.add_handler(report_conv)
    app.add_handler(announce_conv)
    app.add_handler(manual_conv)
    app.add_handler(MessageHandler(filters.Regex("^رویدادهای فعال$"), show_events))
    app.add_handler(MessageHandler(filters.Regex("^پنل ادمین$"), admin_panel))
    app.add_handler(MessageHandler(filters.Regex("^پشتیبانی$"), support))
    app.add_handler(MessageHandler(filters.Regex("^بازگشت$"), back_to_main))
    app.add_handler(CallbackQueryHandler(event_detail, pattern="^event_"))
    app.add_handler(CallbackQueryHandler(register_event, pattern="^reg_"))
    app.add_handler(CallbackQueryHandler(payment_callback, pattern="^pay_"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_receipt))
    app.add_handler(CallbackQueryHandler(check_membership, pattern="^check_membership$"))

    print("ربات جهاد دانشگاهی اردبیل - نسخه کامل فعال شد")
    app.run_polling()

if __name__ == "__main__":
    main()
