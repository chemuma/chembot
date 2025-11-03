# admin_feedback.py
from enum import Enum, auto
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .common import require_admin, get_admin_menu, get_event, get_registrations_for_event
from .database import (
    submit_rating,
    get_average_rating,
    is_feedback_sent,
    mark_feedback_sent,
    has_user_rated,
)
from .config import OPERATOR_GROUP_ID, FEEDBACK_DURATION_HOURS

# راه‌اندازی APScheduler
scheduler = AsyncIOScheduler()
scheduler.start()


class FeedbackStates(Enum):
    SELECT_EVENT = auto()
    CONFIRM_SEND = auto()


feedback_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(ارسال نظرخواهی)$"), feedback_start)],
    states={
        FeedbackStates.SELECT_EVENT: [CallbackQueryHandler(feedback_select_event)],
        FeedbackStates.CONFIRM_SEND: [CallbackQueryHandler(feedback_send)],
    },
    fallbacks=[MessageHandler(filters.Regex("^(لغو)$"), cancel_feedback)],
    per_message=False,
)


async def feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await require_admin(update, context):
        return ConversationHandler.END

    from database import fetch_all
    events = await fetch_all("""
        SELECT event_id, title, type, hashtag FROM events 
        WHERE is_active = 0 AND feedback_sent = 0
        ORDER BY event_id DESC
    """)
    if not events:
        await update.message.reply_text("رویداد اخیر برگزار شده‌ای برای نظرخواهی وجود ندارد.", reply_markup=get_admin_menu())
        return ConversationHandler.END

    buttons = [
        [InlineKeyboardButton(f"{e['title']} ({e['type']})", callback_data=f"fb_event_{e['event_id']}")]
        for e in events
    ]
    await update.message.reply_text("رویداد برای نظرخواهی انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
    return FeedbackStates.SELECT_EVENT


async def feedback_select_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split("_")[2])
    context.user_data["fb_event_id"] = event_id
    event = await get_event(event_id)

    if await is_feedback_sent(event_id):
        await query.edit_message_text("نظرسنجی قبلاً ارسال شده است.", reply_markup=get_admin_menu())
        return ConversationHandler.END

    await query.edit_message_text(
        f"آیا نظرسنجی برای **{event['title']}** ارسال شود؟\n"
        f"مهلت: {FEEDBACK_DURATION_HOURS} ساعت",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("بله، ارسال کن", callback_data="fb_send")],
            [InlineKeyboardButton("لغو", callback_data="fb_cancel")]
        ]),
        parse_mode="Markdown"
    )
    return FeedbackStates.CONFIRM_SEND


async def feedback_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "fb_cancel":
        await query.edit_message_text("ارسال لغو شد.", reply_markup=get_admin_menu())
        return ConversationHandler.END

    event_id = context.user_data["fb_event_id"]
    event = await get_event(event_id)
    registrations = await get_registrations_for_event(event_id)

    if not registrations:
        await query.edit_message_text("هیچ ثبت‌نامی وجود ندارد!", reply_markup=get_admin_menu())
        return ConversationHandler.END

    # برنامه‌ریزی برای محاسبه میانگین
    deadline = datetime.now() + timedelta(hours=FEEDBACK_DURATION_HOURS)
    job_id = f"feedback_{event_id}"
    scheduler.add_job(
        calculate_average_and_send,
        "date",
        run_date=deadline,
        args=(context.bot, event_id, event),
        id=job_id,
        replace_existing=True
    )

    # ارسال نظرسنجی
    buttons = [
        [InlineKeyboardButton(f"{i} ستاره", callback_data=f"rate_{event_id}_{i}")]
        for i in range(1, 6)
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    text = f"نظرت درباره **{event['title']}** چیه؟\nمهلت: {FEEDBACK_DURATION_HOURS} ساعت"

    sent_count = 0
    for reg in registrations:
        try:
            await context.bot.send_message(
                chat_id=reg["user_id"],
                text=text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            sent_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await mark_feedback_sent(event_id)
    await query.edit_message_text(
        f"نظرسنجی برای {sent_count} نفر ارسال شد!\n"
        f"نتیجه در {FEEDBACK_DURATION_HOURS} ساعت به گروه ارسال می‌شود.",
        reply_markup=get_admin_menu()
    )
    return ConversationHandler.END


async def handle_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دکمه‌های امتیازدهی"""
    query = update.callback_query
    await query.answer()

    data = query.data.split("_")
    if len(data) != 3 or data[0] != "rate":
        return

    event_id = int(data[1])
    rating = int(data[2])

    if not (1 <= rating <= 5):
        return

    event = await get_event(event_id)
    if not event or event["is_active"] or await is_feedback_sent(event_id):
        await query.edit_message_text("مهلت امتیازدهی تمام شده است.")
        return

    job = scheduler.get_job(f"feedback_{event_id}")
    if not job or datetime.now() > job.next_run_time:
        await query.edit_message_text("مهلت امتیازدهی تمام شده است.")
        return

    if await has_user_rated(update.effective_user.id, event_id):
        await query.edit_message_text("شما قبلاً امتیاز داده‌اید!")
        return

    await submit_rating(update.effective_user.id, event_id, rating)
    await query.edit_message_text(f"{rating} ستاره ثبت شد!")


async def calculate_average_and_send(bot, event_id: int, event: dict) -> None:
    """محاسبه میانگین و ارسال به گروه"""
    avg = await get_average_rating(event_id)
    avg_text = f"{avg:.1f} ستاره" if avg else "بدون امتیاز"
    hashtag = f"#{event['type']} #{event['hashtag'].replace(' ', '_')} #نمره"
    text = f"{hashtag}\nمیانگین امتیاز: {avg_text}"

    try:
        await bot.send_message(OPERATOR_GROUP_ID, text)
    except Exception as e:
        print(f"خطا در ارسال نتیجه: {e}")


async def cancel_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("عملیات لغو شد.", reply_markup=get_admin_menu())
    return ConversationHandler.END
