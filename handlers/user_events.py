# user_event.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters
from .common import (
    require_channel_membership,
    get_event,
    register_free_event,
    send_payment_request,
    show_main_menu,
)
from database import get_active_events, get_registrations_for_event


async def show_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش لیست رویدادهای فعال"""
    if not await require_channel_membership(update, context):
        return

    events = await get_active_events()
    if not events:
        await update.message.reply_text("در حال حاضر رویداد فعالی وجود ندارد.")
        return

    buttons = [
        [InlineKeyboardButton(f"{e['title']} ({e['type']})", callback_data=f"event_{e['event_id']}")]
        for e in events
    ]
    await update.message.reply_text("رویدادهای فعال:", reply_markup=InlineKeyboardMarkup(buttons))


async def event_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش جزئیات رویداد"""
    query = update.callback_query
    await query.answer()

    event_id = int(query.data.split("_")[1])
    event = await get_event(event_id)

    if not event:
        await query.edit_message_text("رویداد یافت نشد!")
        return

    if not event["is_active"]:
        await query.edit_message_text(f"رویداد غیرفعال است.\nدلیل: {event['deactivation_reason']}")
        return

    capacity_text = "نامحدود" if event["type"] == "دوره" else f"{event['capacity'] - event['current_capacity']}/{event['capacity']}"
    cost_text = "رایگان" if event["cost"] == 0 else f"{event['cost']:,} تومان"

    text = (
        f"**{event['title']}**\n"
        f"نوع: {event['type']}\n"
        f"تاریخ: {event['date']}\n"
        f"محل: {event['location']}\n"
        f"هزینه: {cost_text}\n"
        f"ظرفیت باقی‌مانده: {capacity_text}\n\n"
        f"{event['description'] or 'توضیحات: —'}"
    )

    buttons = [[InlineKeyboardButton("ثبت‌نام", callback_data=f"register_{event_id}")]]
    if event["type"] != "دوره":
        buttons.append([InlineKeyboardButton("بازگشت", callback_data="back_to_events")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def register_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شروع فرآیند ثبت‌نام"""
    query = update.callback_query
    await query.answer()

    if not await require_channel_membership(update, context):
        return

    event_id = int(query.data.split("_")[1])
    event = await get_event(event_id)

    registrations = await get_registrations_for_event(event_id)
    if any(r["user_id"] == update.effective_user.id for r in registrations):
        await query.edit_message_text("شما قبلاً ثبت‌نام کرده‌اید!")
        return

    if event["cost"] == 0:
        await register_free_event(update, context, event_id)
    else:
        await send_payment_request(update, context, event_id)


async def handle_payment_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دریافت تصویر رسید پرداخت"""
    if "pending_event_id" not in context.user_data:
        await update.message.reply_text("لطفاً ابتدا یک رویداد انتخاب کنید.")
        return

    event_id = context.user_data["pending_event_id"]
    event = await get_event(event_id)

    # ارسال رسید به گروه اپراتورها
    photo = update.message.photo[-1]
    caption = (
        f"رسید پرداخت برای رویداد: {event['title']}\n"
        f"کاربر: {update.effective_user.full_name or 'نامشخص'}\n"
        f"آیدی: {update.effective_user.id}"
    )

    sent = await context.bot.send_photo(
        chat_id=context.bot_data.get("operator_group_id", -1002574996302),
        photo=photo.file_id,
        caption=caption
    )

    # دکمه‌های تأیید/رد
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("تأیید", callback_data=f"confirm_payment_{event_id}_{update.effective_user.id}"),
        InlineKeyboardButton("نامشخص", callback_data=f"unclear_payment_{event_id}"),
        InlineKeyboardButton("لغو", callback_data=f"cancel_payment_{event_id}")
    ]])

    await context.bot.send_message(
        chat_id=context.bot_data.get("operator_group_id", -1002574996302),
        text="اقدام:",
        reply_to_message_id=sent.message_id,
        reply_markup=keyboard
    )

    await update.message.reply_text("رسید شما ارسال شد. منتظر تأیید اپراتورها باشید.")
    del context.user_data["pending_event_id"]


async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دکمه چک عضویت"""
    query = update.callback_query
    await query.answer()

    if await require_channel_membership(update, context):
        await query.edit_message_text("عضو شدید! حالا /start بزنید.")
    else:
        await query.edit_message_text("شما هنوز عضو کانال نیستید!")
