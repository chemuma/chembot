# handlers/admin_feedback.py
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, filters, CallbackQueryHandler, MessageHandler
from .common import get_admin_row, get_main_menu, cancel
from datetime import datetime, timedelta
import aiosqlite
from enum import IntEnum

class FeedbackState(IntEnum):
    SELECT_EVENT = 0
    SET_DEADLINE = 1
    CONFIRM_SEND = 2

# --- Send Feedback Request ---
async def send_feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS and not await get_admin_row(user_id):
        await update.message.reply_text("دسترسی ندارید!")
        return ConversationHandler.END

    async with aiosqlite.connect("chemeng_bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT e.event_id, e.title, e.type, fr.request_id IS NOT NULL AS has_request
            FROM events e
            LEFT JOIN feedback_requests fr ON e.event_id = fr.event_id
            WHERE e.is_active = 0
        """) as cursor:
            events = await cursor.fetchall()

    if not events:
        await update.message.reply_text("رویداد غیرفعالی برای نظرخواهی وجود ندارد.")
        return ConversationHandler.END

    buttons = []
    for e in events:
        status = "ارسال شده" if e["has_request"] else "ارسال نشده"
        buttons.append([InlineKeyboardButton(f"{e['title']} ({e['type']}) - {status}", callback_data=f"fb_event_{e['event_id']}")])
    await update.message.reply_text("رویداد برای نظرخواهی انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
    return FeedbackState.SELECT_EVENT

async def feedback_event_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split("_")[2])
    context.user_data["fb_event_id"] = event_id

    await query.message.reply_text("مهلت پاسخ (به روز، مثلاً 3):")
    await query.message.delete()
    return FeedbackState.SET_DEADLINE

async def feedback_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.text.isdigit() or int(update.message.text) <= 0:
        await update.message.reply_text("مهلت باید عدد مثبت باشد.")
        return FeedbackState.SET_DEADLINE

    deadline_days = int(update.message.text)
    deadline = (datetime.now() + timedelta(days=deadline_days)).isoformat()
    context.user_data["fb_deadline"] = deadline

    async with aiosqlite.connect("chemeng_bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT title, type FROM events WHERE event_id = ?", (context.user_data["fb_event_id"],)) as cursor:
            event = await cursor.fetchone()

    text = f"آیا نظرخواهی برای #{event['type']} {event['title']} ارسال شود؟\nمهلت: {deadline_days} روز"
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("بله", callback_data="confirm_send_fb"),
            InlineKeyboardButton("خیر", callback_data="cancel_send_fb")
        ]])
    )
    return FeedbackState.CONFIRM_SEND

async def confirm_send_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_send_fb":
        await query.message.reply_text("لغو شد.", reply_markup=get_admin_menu())
        await query.message.delete()
        return ConversationHandler.END

    event_id = context.user_data["fb_event_id"]
    deadline = context.user_data["fb_deadline"]

    async with aiosqlite.connect("chemeng_bot.db") as db:
        await db.execute(
            "INSERT INTO feedback_requests (event_id, sent_at, deadline) VALUES (?, ?, ?)",
            (event_id, datetime.now().isoformat(), deadline)
        )
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT title, type FROM events WHERE event_id = ?", (event_id,)) as cursor:
            event = await cursor.fetchone()
        async with db.execute("SELECT user_id FROM registrations WHERE event_id = ?", (event_id,)) as cursor:
            users = await cursor.fetchall()
        await db.commit()

    rating_buttons = [
        [InlineKeyboardButton(str(i), callback_data=f"rate_{event_id}_{i}")] for i in range(1, 6)
    ]
    for user in users:
        await context.bot.send_message(
            user["user_id"],
            f"نظرسنجی #{event['type']} {event['title']}\n"
            f"لطفاً امتیاز ۱ تا ۵ بدهید:\n"
            f"مهلت: تا {datetime.fromisoformat(deadline).strftime('%Y-%m-%d')}",
            reply_markup=InlineKeyboardMarkup(rating_buttons)
        )

    await query.message.reply_text("نظرسنجی ارسال شد!", reply_markup=get_admin_menu())
    await query.message.delete()
    return ConversationHandler.END

# --- Handle Rating ---
async def handle_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    event_id = int(parts[1])
    rating = int(parts[2])
    user_id = update.effective_user.id

    try:
        async with aiosqlite.connect("chemeng_bot.db") as db:
            await db.execute(
                "INSERT INTO feedbacks (user_id, event_id, rating, submitted_at) VALUES (?, ?, ?, ?)",
                (user_id, event_id, rating, datetime.now().isoformat())
            )
            await db.commit()
        await query.message.reply_text("ممنون از نظر شما!")
    except aiosqlite.IntegrityError:
        await query.message.reply_text("شما قبلاً نظر داده‌اید.")

# Conversation Handler
feedback_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(ارسال نظرخواهی)$"), send_feedback_start)],
    states={
        FeedbackState.SELECT_EVENT: [CallbackQueryHandler(feedback_event_select)],
        FeedbackState.SET_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_deadline)],
        FeedbackState.CONFIRM_SEND: [CallbackQueryHandler(confirm_send_feedback)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=False
)
