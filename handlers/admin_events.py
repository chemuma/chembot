# handlers/admin_events.py
import re
import logging
from enum import Enum, auto
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    MessageHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)

import database as db
from config import CARD_NUMBER
from handlers.common import get_admin_menu, cancel, is_user_admin

logger = logging.getLogger(__name__)

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

# add_event_conv (از قبل)

# edit_event_conv (اضافه‌شده/اصلاح‌شده)
async def edit_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await is_user_admin(update.effective_user.id):
        await update.message.reply_text("دسترسی ندارید!")
        return ConversationHandler.END
    events = await db.get_all_events()
    buttons = [[InlineKeyboardButton(event['title'], callback_data=f"edit_event_{event['event_id']}")] for event in events]
    await update.message.reply_text("رویداد را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
    return EditEventState.CHOOSE_EVENT.value

async def edit_event_choose(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split("_")[2])
    context.user_data["edit_event_id"] = event_id
    buttons = [
        [InlineKeyboardButton("عنوان", callback_data="edit_title")],
        [InlineKeyboardButton("توضیحات", callback_data="edit_description")],
        # اضافه کن بقیه فیلدها...
        [InlineKeyboardButton("لغو", callback_data="cancel_edit")]
    ]
    await query.message.edit_text("فیلد را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
    return EditEventState.CHOOSE_FIELD.value

async def edit_event_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel_edit":
        await query.message.edit_text("لغو شد.", reply_markup=get_admin_menu())
        return ConversationHandler.END
    context.user_data["edit_field"] = query.data.split("_")[1]
    await query.message.edit_text("مقدار جدید را وارد کنید:")
    return EditEventState.GET_NEW_VALUE.value

async def save_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = update.message.text
    event_id = context.user_data["edit_event_id"]
    field = context.user_data["edit_field"]
    await db.update_event_field(event_id, field, value)  # فرض بر استفاده از تابع db
    await update.message.reply_text("ویرایش شد!", reply_markup=get_admin_menu())
    return ConversationHandler.END

edit_event_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(ویرایش رویدادها ✏️)$"), edit_event_start)],
    states={
        EditEventState.CHOOSE_EVENT.value: [CallbackQueryHandler(edit_event_choose, pattern="^edit_event_")],
        EditEventState.CHOOSE_FIELD.value: [CallbackQueryHandler(edit_event_value, pattern="^edit_")],
        EditEventState.GET_NEW_VALUE.value: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_edit_value)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=True  # برای حذف هشدار
)

# بقیه کد (toggle_event_conv و ...) بدون تغییر
