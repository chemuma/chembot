# handlers/admin_events.py
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, filters, CallbackQueryHandler, MessageHandler
from .common import get_admin_row, get_main_menu, cancel, show_main_menu
from config import ADMIN_IDS, CARD_NUMBER
from datetime import datetime
import aiosqlite
import asyncio
from enum import IntEnum

class EventState(IntEnum):
    TYPE = 0
    TITLE = 1
    DESCRIPTION = 2
    COST = 3
    DATE = 4
    LOCATION = 5
    CAPACITY = 6
    CONFIRM = 7
    EDIT_SELECT = 8
    EDIT_FIELD = 9
    EDIT_VALUE = 10
    TOGGLE_SELECT = 11
    TOGGLE_REASON = 12

# --- Add Event ---
async def add_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS and not await get_admin_row(user_id):
        await update.message.reply_text("دسترسی ندارید!")
        return ConversationHandler.END

    await update.message.reply_text(
        "نوع رویداد:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("دوره", callback_data="دوره")],
            [InlineKeyboardButton("بازدید", callback_data="بازدید")]
        ])
    )
    return EventState.TYPE

async def event_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["event_type"] = query.data
    await query.message.reply_text("عنوان رویداد (حداقل 3 کاراکتر):")
    await query.message.delete()
    return EventState.TITLE

async def event_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    title = update.message.text.strip()
    if len(title) < 3:
        await update.message.reply_text("عنوان کوتاه است. دوباره وارد کنید:")
        return EventState.TITLE
    context.user_data["event_title"] = title
    context.user_data["event_hashtag"] = "#" + "_".join(title.split())
    await update.message.reply_text("توضیحات (حداقل 10 کاراکتر، می‌توانید عکس هم بفرستید):")
    return EventState.DESCRIPTION

async def event_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    desc = update.message.text or update.message.caption or ""
    if len(desc) < 10:
        await update.message.reply_text("توضیحات کوتاه است.")
        return EventState.DESCRIPTION
    context.user_data["event_description"] = desc
    if update.message.photo:
        context.user_data["event_photo"] = update.message.photo[-1].file_id
    await update.message.reply_text("هزینه (0 = رایگان):")
    return EventState.COST

async def event_cost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.text.isdigit():
        await update.message.reply_text("هزینه باید عدد باشد.")
        return EventState.COST
    context.user_data["event_cost"] = int(update.message.text)
    await update.message.reply_text("تاریخ (YYYY-MM-DD):")
    return EventState.DATE

async def event_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", update.message.text):
        await update.message.reply_text("فرمت تاریخ نادرست است.")
        return EventState.DATE
    context.user_data["event_date"] = update.message.text
    await update.message.reply_text("محل (حداقل 5 کاراکتر):")
    return EventState.LOCATION

async def event_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if len(update.message.text) < 5:
        await update.message.reply_text("محل کوتاه است.")
        return EventState.LOCATION
    context.user_data["event_location"] = update.message.text
    if context.user_data["event_type"] == "دوره":
        context.user_data["event_capacity"] = 0
        return await confirm_event(update, context)
    await update.message.reply_text("ظرفیت (عدد مثبت):")
    return EventState.CAPACITY

async def event_capacity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.text.isdigit() or int(update.message.text) <= 0:
        await update.message.reply_text("ظرفیت باید عدد مثبت باشد.")
        return EventState.CAPACITY
    context.user_data["event_capacity"] = int(update.message.text)
    return await confirm_event(update, context)

async def confirm_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data
    cost_text = "رایگان" if data["event_cost"] == 0 else f"{data['event_cost']:,} تومان"
    cap_text = "نامحدود" if data["event_type"] == "دوره" else str(data["event_capacity"])
    text = (
        f"نوع: {data['event_type']}\n"
        f"عنوان: {data['event_title']}\n"
        f"هشتگ: {data['event_hashtag']}\n"
        f"توضیحات: {data['event_description']}\n"
        f"هزینه: {cost_text}\n"
        f"تاریخ: {data['event_date']}\n"
        f"محل: {data['event_location']}\n"
        f"ظرفیت: {cap_text}"
    )
    buttons = [[
        InlineKeyboardButton("تأیید", callback_data="save_event"),
        InlineKeyboardButton("لغو", callback_data="cancel_event")
    ]]
    if "event_photo" in data:
        await update.message.reply_photo(data["event_photo"], caption=text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    return EventState.CONFIRM

async def save_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel_event":
        await query.message.reply_text("لغو شد.", reply_markup=get_admin_menu())
        await query.message.delete()
        return ConversationHandler.END

    data = context.user_data
    async with aiosqlite.connect("chemeng_bot.db") as db:
        await db.execute(
            """
            INSERT INTO events (title, type, date, location, capacity, description, is_active, hashtag, cost, card_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["event_title"], data["event_type"], data["event_date"], data["event_location"],
                data.get("event_capacity", 0), data["event_description"], 1, data["event_hashtag"],
                data["event_cost"], CARD_NUMBER if data["event_cost"] > 0 else ""
            )
        )
        event_id = db.lastrowid
        await db.commit()

    # Notify all users
    async with aiosqlite.connect("chemeng_bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id, full_name FROM users") as cursor:
            users = await cursor.fetchall()

    for user in users:
        await context.bot.send_message(
            user["user_id"],
            f"{user['full_name']} عزیز،\n"
            f"یک #{data['event_type']} {data['event_hashtag']} اضافه شد.\n"
            "جزئیات در کانال..."
        )
        if "event_photo" in data:
            await context.bot.send_photo(user["user_id"], data["event_photo"], caption=data["event_description"])
        else:
            await context.bot.send_message(user["user_id"], f"توضیحات: {data['event_description']}")
        await context.bot.send_message(
            user["user_id"], "ثبت‌نام کن",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("ثبت‌نام", callback_data=f"register_{event_id}")
            ]])
        )
        await asyncio.sleep(0.05)  # Anti-flood

    await query.message.reply_text("رویداد اضافه شد!", reply_markup=get_admin_menu())
    await query.message.delete()
    return ConversationHandler.END

# --- Edit Event (Field-by-Field) ---
async def edit_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS and not await get_admin_row(user_id):
        await update.message.reply_text("دسترسی ندارید!")
        return ConversationHandler.END

    async with aiosqlite.connect("chemeng_bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT event_id, title, type FROM events") as cursor:
            events = await cursor.fetchall()

    if not events:
        await update.message.reply_text("رویدادی وجود ندارد!", reply_markup=get_admin_menu())
        return ConversationHandler.END

    buttons = [[InlineKeyboardButton(f"{e['title']} ({e['type']})", callback_data=f"edit_select_{e['event_id']}")] for e in events]
    await update.message.reply_text("رویداد را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
    return EventState.EDIT_SELECT

async def edit_event_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split("_")[2])
    context.user_data["edit_event_id"] = event_id

    async with aiosqlite.connect("chemeng_bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)) as cursor:
            event = await cursor.fetchone()

    buttons = [
        [InlineKeyboardButton("عنوان", callback_data="edit_field_title")],
        [InlineKeyboardButton("توضیحات", callback_data="edit_field_description")],
        [InlineKeyboardButton("هزینه", callback_data="edit_field_cost")],
        [InlineKeyboardButton("تاریخ", callback_data="edit_field_date")],
        [InlineKeyboardButton("محل", callback_data="edit_field_location")],
        [InlineKeyboardButton("ظرفیت", callback_data="edit_field_capacity")],
        [InlineKeyboardButton("لغو", callback_data="cancel_edit")]
    ]
    await query.message.reply_text("کدام فیلد را ویرایش می‌کنید؟", reply_markup=InlineKeyboardMarkup(buttons))
    await query.message.delete()
    return EventState.EDIT_FIELD

async def edit_event_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel_edit":
        await query.message.reply_text("لغو شد.", reply_markup=get_admin_menu())
        await query.message.delete()
        return ConversationHandler.END

    field = query.data.split("_")[2]
    context.user_data["edit_field"] = field
    labels = {
        "title": "عنوان جدید",
        "description": "توضیحات جدید",
        "cost": "هزینه جدید (0 = رایگان)",
        "date": "تاریخ جدید (YYYY-MM-DD)",
        "location": "محل جدید",
        "capacity": "ظرفیت جدید"
    }
    await query.message.reply_text(f"{labels[field]}:")
    await query.message.delete()
    return EventState.EDIT_VALUE

async def edit_event_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = update.message.text.strip()
    event_id = context.user_data["edit_event_id"]
    field = context.user_data["edit_field"]

    # Validation
    if field == "title" and len(value) < 3:
        await update.message.reply_text("عنوان کوتاه است.")
        return EventState.EDIT_VALUE
    if field == "description" and len(value) < 10:
        await update.message.reply_text("توضیحات کوتاه است.")
        return EventState.EDIT_VALUE
    if field == "cost" and not value.isdigit():
        await update.message.reply_text("هزینه باید عدد باشد.")
        return EventState.EDIT_VALUE
    if field == "date" and not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        await update.message.reply_text("فرمت تاریخ نادرست.")
        return EventState.EDIT_VALUE
    if field == "location" and len(value) < 5:
        await update.message.reply_text("محل کوتاه است.")
        return EventState.EDIT_VALUE
    if field == "capacity" and (not value.isdigit() or int(value) <= 0):
        await update.message.reply_text("ظرفیت باید مثبت باشد.")
        return EventState.EDIT_VALUE

    async with aiosqlite.connect("chemeng_bot.db") as db:
        if field == "title":
            hashtag = "#" + "_".join(value.split())
            await db.execute("UPDATE events SET title = ?, hashtag = ? WHERE event_id = ?", (value, hashtag, event_id))
        else:
            await db.execute(f"UPDATE events SET {field} = ? WHERE event_id = ?", (value if field != "cost" else int(value), event_id))
        await db.commit()

    await update.message.reply_text("رویداد ویرایش شد!", reply_markup=get_admin_menu())
    return ConversationHandler.END

# Conversation Handler
admin_events_conv = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex("^(اضافه کردن رویداد جدید)$"), add_event),
        MessageHandler(filters.Regex("^(تغییر رویداد فعال)$"), edit_event_start)
    ],
    states={
        EventState.TYPE: [CallbackQueryHandler(event_type)],
        EventState.TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_title)],
        EventState.DESCRIPTION: [MessageHandler(filters.TEXT | filters.PHOTO, event_description)],
        EventState.COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_cost)],
        EventState.DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_date)],
        EventState.LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_location)],
        EventState.CAPACITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_capacity)],
        EventState.CONFIRM: [CallbackQueryHandler(save_event)],
        EventState.EDIT_SELECT: [CallbackQueryHandler(edit_event_select)],
        EventState.EDIT_FIELD: [CallbackQueryHandler(edit_event_field)],
        EventState.EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_event_value)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=False
)
