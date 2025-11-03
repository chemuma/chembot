# admin_events.py
from enum import Enum, auto
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from common import require_admin, get_admin_menu, remove_keyboard
from database import (
    create_event,
    update_event_field,
    deactivate_event,
    activate_event,
    get_active_events,
    get_all_events,
    get_event,
    get_registrations_for_event,
    increment_event_capacity,
)


# ==============================
# حالت‌های اضافه کردن رویداد
# ==============================

class AddEventStates(Enum):
    TYPE = auto()
    TITLE = auto()
    DESCRIPTION = auto()
    COST = auto()
    DATE = auto()
    LOCATION = auto()
    CAPACITY = auto()
    HASHTAG = auto()
    CONFIRM = auto()


# ==============================
# حالت‌های ویرایش رویداد
# ==============================

class EditEventStates(Enum):
    SELECT_EVENT = auto()
    SELECT_FIELD = auto()
    INPUT_VALUE = auto()


# ==============================
# حالت‌های فعال/غیرفعال
# ==============================

class ToggleEventStates(Enum):
    SELECT_EVENT = auto()
    INPUT_REASON = auto()


# ==============================
# ConversationHandler: اضافه کردن رویداد
# ==============================

add_event_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(اضافه کردن رویداد جدید)$"), add_event_start)],
    states={
        AddEventStates.TYPE: [CallbackQueryHandler(add_event_type)],
        AddEventStates.TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_event_title)],
        AddEventStates.DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_event_description)],
        AddEventStates.COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_event_cost)],
        AddEventStates.DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_event_date)],
        AddEventStates.LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_event_location)],
        AddEventStates.CAPACITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_event_capacity)],
        AddEventStates.HASHTAG: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_event_hashtag)],
        AddEventStates.CONFIRM: [CallbackQueryHandler(add_event_confirm)],
    },
    fallbacks=[MessageHandler(filters.Regex("^(لغو)$"), cancel_add_event)],
    per_message=False,
)


# ==============================
# توابع اضافه کردن رویداد
# ==============================

async def add_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await require_admin(update, context):
        return ConversationHandler.END

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("دوره", callback_data="type_دوره")],
        [InlineKeyboardButton("بازدید", callback_data="type_بازدید")]
    ])
    await update.message.reply_text("نوع رویداد را انتخاب کنید:", reply_markup=keyboard)
    return AddEventStates.TYPE


async def add_event_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["event_type"] = query.data.split("_")[1]
    await query.edit_message_text("عنوان رویداد را وارد کنید:")
    return AddEventStates.TITLE


async def add_event_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["event_title"] = update.message.text.strip()
    await update.message.reply_text("توضیحات رویداد را وارد کنید:")
    return AddEventStates.DESCRIPTION


async def add_event_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["event_description"] = update.message.text.strip()
    await update.message.reply_text("هزینه رویداد (0 = رایگان):")
    return AddEventStates.COST


async def add_event_cost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        cost = int(update.message.text.strip())
        if cost < 0:
            raise ValueError
        context.user_data["event_cost"] = cost
    except ValueError:
        await update.message.reply_text("هزینه باید عدد غیرمنفی باشد. دوباره وارد کنید:")
        return AddEventStates.COST
    await update.message.reply_text("تاریخ برگزاری (مثال: 1404/08/15):")
    return AddEventStates.DATE


async def add_event_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["event_date"] = update.message.text.strip()
    await update.message.reply_text("محل برگزاری:")
    return AddEventStates.LOCATION


async def add_event_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["event_location"] = update.message.text.strip()
    await update.message.reply_text("ظرفیت (عدد یا 'نامحدود'):")
    return AddEventStates.CAPACITY


async def add_event_capacity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()
    if text == "نامحدود":
        context.user_data["event_capacity"] = None
    else:
        try:
            capacity = int(text)
            if capacity <= 0:
                raise ValueError
            context.user_data["event_capacity"] = capacity
        except ValueError:
            await update.message.reply_text("ظرفیت باید عدد مثبت یا 'نامحدود' باشد.")
            return AddEventStates.CAPACITY
    await update.message.reply_text("هشتگ رویداد (مثال: شیمی_پالایش):")
    return AddEventStates.HASHTAG


async def add_event_hashtag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["event_hashtag"] = update.message.text.strip()
    
    event = context.user_data
    cost_text = "رایگان" if event["event_cost"] == 0 else f"{event['event_cost']:,} تومان"
    capacity_text = "نامحدود" if event["event_capacity"] is None else str(event["event_capacity"])

    text = (
        f"**تأیید رویداد**\n\n"
        f"عنوان: {event['event_title']}\n"
        f"نوع: {event['event_type']}\n"
        f"هزینه: {cost_text}\n"
        f"تاریخ: {event['event_date']}\n"
        f"محل: {event['event_location']}\n"
        f"ظرفیت: {capacity_text}\n"
        f"هشتگ: #{event['event_hashtag']}\n"
        f"توضیحات: {event['event_description']}"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("تأیید", callback_data="confirm_event")],
        [InlineKeyboardButton("لغو", callback_data="cancel_event")]
    ])
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    return AddEventStates.CONFIRM


async def add_event_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_event":
        await query.edit_message_text("ایجاد رویداد لغو شد.", reply_markup=get_admin_menu())
        return ConversationHandler.END

    event = context.user_data
    event_id = await create_event(
        title=event["event_title"],
        type_=event["event_type"],
        date=event["event_date"],
        location=event["event_location"],
        capacity=event["event_capacity"],
        description=event["event_description"],
        hashtag=event["event_hashtag"],
        cost=event["event_cost"],
        card_number=None
    )

    await query.edit_message_text(f"رویداد با موفقیت ایجاد شد! ID: {event_id}", reply_markup=get_admin_menu())
    return ConversationHandler.END


# ==============================
# ویرایش رویداد (جزئی)
# ==============================

edit_event_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(تغییر رویداد فعال)$"), edit_event_start)],
    states={
        EditEventStates.SELECT_EVENT: [CallbackQueryHandler(edit_event_select)],
        EditEventStates.SELECT_FIELD: [CallbackQueryHandler(edit_event_field)],
        EditEventStates.INPUT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_event_value)],
    },
    fallbacks=[MessageHandler(filters.Regex("^(لغو)$"), cancel_edit_event)],
    per_message=False,
)


async def edit_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await require_admin(update, context):
        return ConversationHandler.END

    events = await get_active_events()
    if not events:
        await update.message.reply_text("رویداد فعالی وجود ندارد.", reply_markup=get_admin_menu())
        return ConversationHandler.END

    buttons = [
        [InlineKeyboardButton(f"{e['title']} ({e['type']})", callback_data=f"edit_event_{e['event_id']}")]
        for e in events
    ]
    await update.message.reply_text("رویداد را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
    return EditEventStates.SELECT_EVENT


async def edit_event_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["edit_event_id"] = int(query.data.split("_")[2])
    event = await get_event(context.user_data["edit_event_id"])

    buttons = [
        [InlineKeyboardButton("عنوان", callback_data="field_title")],
        [InlineKeyboardButton("توضیحات", callback_data="field_description")],
        [InlineKeyboardButton("هزینه", callback_data="field_cost")],
        [InlineKeyboardButton("تاریخ", callback_data="field_date")],
        [InlineKeyboardButton("محل", callback_data="field_location")],
        [InlineKeyboardButton("ظرفیت", callback_data="field_capacity")],
        [InlineKeyboardButton("هشتگ", callback_data="field_hashtag")],
        [InlineKeyboardButton("لغو", callback_data="cancel_edit")]
    ]
    await query.edit_message_text(f"ویرایش: {event['title']}\nکدام بخش؟", reply_markup=InlineKeyboardMarkup(buttons))
    return EditEventStates.SELECT_FIELD


async def edit_event_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_edit":
        await query.edit_message_text("ویرایش لغو شد.", reply_markup=get_admin_menu())
        return ConversationHandler.END

    context.user_data["edit_field"] = query.data.split("_")[1]
    field_names = {
        "title": "عنوان",
        "description": "توضیحات",
        "cost": "هزینه",
        "date": "تاریخ",
        "location": "محل",
        "capacity": "ظرفیت",
        "hashtag": "هشتگ"
    }
    await query.edit_message_text(f"مقدار جدید برای {field_names[context.user_data['edit_field']]}:")
    return EditEventStates.INPUT_VALUE


async def edit_event_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    field = context.user_data["edit_field"]
    value = update.message.text.strip()
    event_id = context.user_data["edit_event_id"]

    if field == "cost":
        try:
            value = int(value)
            if value < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("هزینه باید عدد غیرمنفی باشد.")
            return EditEventStates.INPUT_VALUE
    elif field == "capacity":
        if value.lower() == "نامحدود":
            value = None
        else:
            try:
                value = int(value)
                if value <= 0:
                    raise ValueError
            except ValueError:
                await update.message.reply_text("ظرفیت باید عدد مثبت یا 'نامحدود' باشد.")
                return EditEventStates.INPUT_VALUE

    await update_event_field(event_id, field, value)
    await update.message.reply_text("رویداد با موفقیت ویرایش شد!", reply_markup=get_admin_menu())
    return ConversationHandler.END


# ==============================
# فعال/غیرفعال کردن
# ==============================

toggle_event_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(غیرفعال/فعال کردن رویداد)$"), toggle_event_start)],
    states={
        ToggleEventStates.SELECT_EVENT: [CallbackQueryHandler(toggle_event_select)],
        ToggleEventStates.INPUT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, toggle_event_reason)],
    },
    fallbacks=[MessageHandler(filters.Regex("^(لغو)$"), cancel_toggle_event)],
    per_message=False,
)


async def toggle_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await require_admin(update, context):
        return ConversationHandler.END

    events = await get_all_events()
    if not events:
        await update.message.reply_text("رویدادی وجود ندارد.")
        return ConversationHandler.END

    buttons = []
    for e in events:
        status = "غیرفعال" if not e["is_active"] else "فعال"
        buttons.append([InlineKeyboardButton(f"{e['title']} ({status})", callback_data=f"toggle_{e['event_id']}")])
    await update.message.reply_text("رویداد را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
    return ToggleEventStates.SELECT_EVENT


async def toggle_event_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split("_")[1])
    event = await get_event(event_id)
    context.user_data["toggle_event_id"] = event_id

    if event["is_active"]:
        await query.edit_message_text("دلیل غیرفعال‌سازی را وارد کنید:")
        return ToggleEventStates.INPUT_REASON
    else:
        await activate_event(event_id)
        await query.edit_message_text("رویداد فعال شد!", reply_markup=get_admin_menu())
        return ConversationHandler.END


async def toggle_event_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reason = update.message.text.strip()
    event_id = context.user_data["toggle_event_id"]
    await deactivate_event(event_id, reason)
    await update.message.reply_text("رویداد غیرفعال شد.", reply_markup=get_admin_menu())
    return ConversationHandler.END


# ==============================
# توابع لغو
# ==============================

async def cancel_add_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("ایجاد رویداد لغو شد.", reply_markup=get_admin_menu())
    return ConversationHandler.END

async def cancel_edit_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("ویرایش لغو شد.", reply_markup=get_admin_menu())
    return ConversationHandler.END

async def cancel_toggle_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("عملیات لغو شد.", reply_markup=get_admin_menu())
    return ConversationHandler.END
