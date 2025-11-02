# handlers/admin_events.py
import re
import logging
from enum import Enum, auto
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)

import database as db
from config import CARD_NUMBER
from handlers.common import get_admin_menu, cancel, is_user_admin

logger = logging.getLogger(__name__)

# --- States ---
class EventState(Enum):
    TYPE = auto()
    TITLE = auto()
    DESCRIPTION = auto()
    COST = auto()
    DATE = auto()
    LOCATION = auto()
    CAPACITY = auto()
    CONFIRM = auto()

class EditEventState(Enum):
    CHOOSE_EVENT = auto()
    CHOOSE_FIELD = auto()
    GET_NEW_VALUE = auto()

class ToggleEventState(Enum):
    CHOOSE_EVENT = auto()
    GET_REASON = auto()

# --- 1. Add Event Conversation ---

async def add_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await is_user_admin(update.effective_user.id):
        await update.message.reply_text("شما دسترسی ادمین ندارید! 🚫")
        return ConversationHandler.END
    await update.message.reply_text(
        "نوع رویداد را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("دوره 📚", callback_data="دوره")],
            [InlineKeyboardButton("بازدید 🏭", callback_data="بازدید")]
        ])
    )
    return EventState.TYPE.value  # Enum value برای state

async def event_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["event_type"] = query.data
    await query.message.edit_text("لطفاً عنوان رویداد را وارد کنید (حداقل 3 کاراکتر):")
    return EventState.TITLE.value

async def event_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    title = update.message.text
    if len(title) < 3:
        await update.message.reply_text("عنوان باید حداقل 3 کاراکتر باشد. دوباره وارد کنید:")
        return EventState.TITLE.value
    context.user_data["event_title"] = title
    hashtag = "#" + "_".join(title.split())
    context.user_data["event_hashtag"] = hashtag
    await update.message.reply_text("لطفاً توضیحات رویداد را وارد کنید (حداقل 10 کاراکتر):")
    return EventState.DESCRIPTION.value

async def event_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    description = update.message.text or update.message.caption or ""
    if len(description) < 10:
        await update.message.reply_text("توضیحات باید حداقل 10 کاراکتر باشد. دوباره وارد کنید:")
        return EventState.DESCRIPTION.value
    context.user_data["event_description"] = description
    if update.message.photo:
        context.user_data["event_photo"] = update.message.photo[-1].file_id
    await update.message.reply_text("هزینه رویداد را وارد کنید (0 برای رایگان، یا مبلغ به تومان):")
    return EventState.COST.value

async def event_cost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cost = update.message.text
    if not re.match(r"^\d+$", cost):
        await update.message.reply_text("هزینه باید عدد باشد. دوباره وارد کنید:")
        return EventState.COST.value
    context.user_data["event_cost"] = int(cost)
    await update.message.reply_text("تاریخ رویداد را با فرمت YYYY-MM-DD وارد کنید:")
    return EventState.DATE.value

async def event_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    date = update.message.text
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:  # اصلاح شد
        await update.message.reply_text("فرمت تاریخ باید YYYY-MM-DD باشد. دوباره وارد کنید:")
        return EventState.DATE.value
    context.user_data["event_date"] = date
    await update.message.reply_text("محل رویداد را وارد کنید (حداقل 5 کاراکتر):")
    return EventState.LOCATION.value

async def event_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    location = update.message.text
    if len(location) < 5:
        await update.message.reply_text("محل باید حداقل 5 کاراکتر باشد. دوباره وارد کنید:")
        return EventState.LOCATION.value
    context.user_data["event_location"] = location
    if context.user_data["event_type"] == "دوره":
        context.user_data["event_capacity"] = 0
        return await confirm_event(update, context)  # Skip capacity step
    await update.message.reply_text("ظرفیت رویداد را وارد کنید (عدد مثبت):")
    return EventState.CAPACITY.value

async def event_capacity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    capacity = update.message.text
    if not re.match(r"^\d+$", capacity) or int(capacity) <= 0:
        await update.message.reply_text("ظرفیت باید عدد مثبت باشد. دوباره وارد کنید:")
        return EventState.CAPACITY.value
    context.user_data["event_capacity"] = int(capacity)
    return await confirm_event(update, context)

async def confirm_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    event_data = context.user_data
    cost_text = "رایگان" if event_data["event_cost"] == 0 else f"{event_data['event_cost']:,} تومان"
    capacity_text = "نامحدود" if event_data["event_type"] == "دوره" else f"{event_data['event_capacity']}"
    text = (
        f"نوع: {event_data['event_type']}\n"
        f"عنوان: {event_data['event_title']}\n"
        f"هشتگ: {event_data['event_hashtag']}\n"
        f"توضیحات: {event_data['event_description']}\n"
        f"هزینه: {cost_text}\n"
        f"تاریخ: {event_data['event_date']}\n"
        f"محل: {event_data['event_location']}\n"
        f"ظرفیت: {capacity_text}"
    )
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("تأیید ✅", callback_data="confirm_event"),
        InlineKeyboardButton("لغو 🚫", callback_data="cancel_event")
    ]])
    
    if "event_photo" in event_data:
        await update.message.reply_photo(
            event_data["event_photo"], caption=text, reply_markup=markup
        )
    else:
        await update.message.reply_text(text, reply_markup=markup)
    return EventState.CONFIRM.value

async def save_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel_event":
        await query.message.edit_text("ایجاد رویداد لغو شد.", reply_markup=get_admin_menu())
        return ConversationHandler.END
        
    event_data = context.user_data
    try:
        async with db.get_db_connection() as conn:
            await conn.execute(
                """
                INSERT INTO events (title, type, date, location, capacity, description, is_active, hashtag, cost, card_number)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (
                    event_data['event_title'],
                    event_data['event_type'],
                    event_data['event_date'],
                    event_data['event_location'],
                    event_data.get('event_capacity', 0),
                    event_data['event_description'],
                    event_data['event_hashtag'],
                    event_data['event_cost'],
                    CARD_NUMBER
                )
            )
            await conn.commit()
        await query.message.edit_text("رویداد با موفقیت ایجاد شد! ✅", reply_markup=get_admin_menu())
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error saving event: {e}")
        await query.message.edit_text("خطایی در ذخیره رویداد رخ داد.", reply_markup=get_admin_menu())
        return ConversationHandler.END

add_event_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(اضافه کردن رویداد جدید ➕)$"), add_event)],
    states={
        EventState.TYPE.value: [CallbackQueryHandler(event_type)],
        EventState.TITLE.value: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_title)],
        EventState.DESCRIPTION.value: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, event_description),
            MessageHandler(filters.PHOTO, event_description),
        ],
        EventState.COST.value: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_cost)],
        EventState.DATE.value: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_date)],
        EventState.LOCATION.value: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_location)],
        EventState.CAPACITY.value: [MessageHandler(filters.TEXT & ~filters.COMMAND, event_capacity)],
        EventState.CONFIRM.value: [CallbackQueryHandler(save_event)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=False
)

# --- 2. Edit Event Conversation --- (بقیه کد بدون تغییر، فقط Enum.value اضافه برای states)
# ... (برای اختصار، بقیه رو بدون تغییر فرض کن، فقط ValueError اصلاح شد)
