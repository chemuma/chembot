# handlers/admin_feedback.py
import logging
from enum import Enum, auto
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler,
    filters, ContextTypes
)

import database as db
from config import OPERATOR_GROUP_ID, FEEDBACK_WINDOW_DAYS
from handlers.common import get_admin_menu, cancel, is_user_admin

logger = logging.getLogger(__name__)

class FeedbackState(Enum):
    CHOOSE_EVENT = auto()
    CONFIRM_SEND = auto()

async def feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the process for sending feedback forms."""
    if not await is_user_admin(update.effective_user.id):
        await update.message.reply_text("شما دسترسی ادمین ندارید! 🚫")
        return ConversationHandler.END

    # رویدادهایی که تمام شده و نظرسنجی ارسال نشده را بگیر
    events = await db.get_recently_finished_events()
    
    if not events:
        await update.message.reply_text(
            "در حال حاضر هیچ رویداد برگزار شده‌ای (که نظرسنجی برایش ارسال نشده باشد) وجود ندارد.",
            reply_markup=get_admin_menu()
        )
        return ConversationHandler.END

    buttons = [[InlineKeyboardButton(
        f"{event['title']} ({event['type']}) - {event['date']}", 
        callback_data=f"send_feedback_{event['event_id']}"
    )] for event in events]
    
    buttons.append([InlineKeyboardButton("لغو 🚫", callback_data="cancel_feedback")])
    
    await update.message.reply_text(
        "برای کدام رویداد می‌خواهید فرم نظرسنجی ارسال کنید؟",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return FeedbackState.CHOOSE_EVENT

async def feedback_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asks admin to confirm sending feedback forms."""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_feedback":
        await query.message.edit_text("عملیات لغو شد.", reply_markup=get_admin_menu())
        return ConversationHandler.END
        
    event_id = int(query.data.split("_")[2])
    context.user_data["feedback_event_id"] = event_id
    
    event = await db.get_event_details(event_id)
    participants = await db.get_event_participants(event_id)
    
    if not event:
        await query.message.edit_text("خطا: رویداد یافت نشد.", reply_markup=get_admin_menu())
        return ConversationHandler.END
        
    if not participants:
        await query.message.edit_text(f"رویداد '{event['title']}' هیچ شرکت‌کننده‌ای ندارد!", reply_markup=get_admin_menu())
        return ConversationHandler.END

    text = (
        f"رویداد: {event['title']}\n"
        f"تعداد شرکت‌کنندگان: {len(participants)} نفر\n\n"
        f"آیا فرم نظرسنجی برای این افراد ارسال شود؟"
    )
    buttons = [
        [InlineKeyboardButton("بله، ارسال کن ✅", callback_data="confirm_send_feedback")],
        [InlineKeyboardButton("خیر، لغو کن 🚫", callback_data="cancel_feedback")]
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    return FeedbackState.CONFIRM_SEND

async def feedback_send_forms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Sends feedback forms to all participants and schedules the result job."""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_feedback":
        await query.message.edit_text("عملیات لغو شد.", reply_markup=get_admin_menu())
        return ConversationHandler.END

    event_id = context.user_data.get("feedback_event_id")
    if not event_id:
        await query.message.edit_text("خطا: رویداد یافت نشد.", reply_markup=get_admin_menu())
        return ConversationHandler.END

    event = await db.get_event_details(event_id)
    participants = await db.get_event_participants(event_id)
    
    await query.message.edit_text(f"در حال ارسال {len(participants)} فرم نظرسنجی...")

    # Build rating keyboard
    buttons = [
        InlineKeyboardButton("⭐ 1", callback_data=f"rate_{event_id}_1"),
        InlineKeyboardButton("⭐ 2", callback_data=f"rate_{event_id}_2"),
        InlineKeyboardButton("⭐ 3", callback_data=f"rate_{event_id}_3"),
        InlineKeyboardButton("⭐ 4", callback_data=f"rate_{event_id}_4"),
        InlineKeyboardButton("⭐ 5", callback_data=f"rate_{event_id}_5"),
    ]
    rating_markup = InlineKeyboardMarkup([buttons])
    
    message_text = (
        f"سلام! متشکریم که در رویداد '{event['title']}' شرکت کردید.\n"
        f"لطفاً با انتخاب یک گزینه، به این رویداد امتیاز دهید (از 1 تا 5 ستاره).\n"
        f"شما {FEEDBACK_WINDOW_DAYS} روز فرصت دارید."
    )
    
    sent_count = 0
    for participant in participants:
        try:
            await context.bot.send_message(
                chat_id=participant['user_id'],
                text=message_text,
                reply_markup=rating_markup
            )
            sent_count += 1
        except Exception as e:
            logger.warning(f"Failed to send feedback form to user {participant['user_id']}: {e}")
    
    # Mark as sent in DB
    await db.set_feedback_sent(event_id)
    
    # Schedule the job to calculate results
    context.job_queue.run_once(
        calculate_average_job,
        timedelta(days=FEEDBACK_WINDOW_DAYS),
        data={'event_id': event_id, 'event_title': event['title'], 'event_hashtag': event['hashtag'], 'event_type': event['type']},
        name=f"feedback_result_{event_id}"
    )
    
    await query.message.edit_text(
        f"نظرسنجی با موفقیت به {sent_count} نفر ارسال شد.\n"
        f"نتایج {FEEDBACK_WINDOW_DAYS} روز دیگر به گروه اپراتورها ارسال خواهد شد.",
        reply_markup=get_admin_menu()
    )
    return ConversationHandler.END

async def calculate_average_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job callback to calculate and send average rating."""
    job_data = context.job.data
    event_id = job_data['event_id']
    
    try:
        ratings_data = await db.get_event_ratings(event_id)
        if not ratings_data or ratings_data['num_ratings'] == 0:
            avg_rating_text = "هیچ رایی ثبت نشد"
            num_ratings = 0
        else:
            avg_rating = ratings_data['avg_rating']
            num_ratings = ratings_data['num_ratings']
            avg_rating_text = f"{avg_rating:.1f} ستاره"
            
        hashtag = f"#{job_data['event_type']} #{job_data['event_hashtag'].replace(' ', '_')} #نمره"
        
        text = (
            f"📊 **نتایج نظرسنجی رویداد** 📊\n"
            f"{hashtag}\n\n"
            f"**رویداد:** {job_data['event_title']}\n"
            f"**میانگین امتیاز:** {avg_rating_text}\n"
            f"**تعداد کل آرا:** {num_ratings} نفر"
        )
        
        await context.bot.send_message(OPERATOR_GROUP_ID, text)
        logger.info(f"Feedback results sent for event {event_id}.")
        
    except Exception as e:
        logger.error(f"Error in calculate_average_job for event {event_id}: {e}")

feedback_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(ارسال نظرسنجی 📊⭐)$"), feedback_start)],
    states={
        FeedbackState.CHOOSE_EVENT: [CallbackQueryHandler(feedback_confirm, pattern="^(send_feedback_|cancel_feedback)"), ],
        FeedbackState.CONFIRM_SEND: [CallbackQueryHandler(feedback_send_forms, pattern="^(confirm_send_feedback|cancel_feedback)$")],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=False
)

# --- User-side Rating Handler (Not part of admin conversation) ---

async def handle_user_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    try:
        _, event_id_str, rating_str = query.data.split("_")
        event_id = int(event_id_str)
        rating = int(rating_str)
        user_id = query.from_user.id  # اصلاح

        # Check if deadline has passed
        event_status = await db.get_event_feedback_status(event_id)
        if not event_status or not event_status['feedback_sent_at']:
            await query.message.edit_text("خطایی رخ داد. این نظرسنجی معتبر نیست.")
            return

        sent_at = datetime.fromisoformat(event_status['feedback_sent_at'])
        deadline = sent_at + timedelta(days=FEEDBACK_WINDOW_DAYS)
        
        if datetime.now() > deadline:
            await query.message.edit_text(
                f"متأسفانه مهلت {FEEDBACK_WINDOW_DAYS} روزه برای امتیازدهی به این رویداد تمام شده است."
            )
            return

        # Store the rating
        await db.store_rating(user_id, event_id, rating)
        
        await query.message.edit_text(
            f"از بازخورد شما متشکریم! ✨\n"
            f"امتیاز شما: {'⭐' * rating} ({rating} ستاره) ثبت شد."
        )
        
    except Exception as e:
        logger.error(f"Error handling user rating: {e}")
        await query.message.edit_text("خطایی در ثبت امتیاز شما رخ داد.")
