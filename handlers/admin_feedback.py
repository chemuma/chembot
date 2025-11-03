# admin_feedback.py
from enum import Enum, auto
from telegram.ext import ConversationHandler, CallbackQueryHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import timedelta
from common import get_admin_menu
from config import OPERATOR_GROUP_ID
from database import get_event, get_registrations  # etc.

class FeedbackStates(Enum):
    SELECT_EVENT = auto()
    SEND_POLL = auto()

feedback_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(ارسال نظرخواهی ⭐)$"), start_feedback)],
    states={
        FeedbackStates.SELECT_EVENT: [CallbackQueryHandler(select_feedback_event)],
        FeedbackStates.SEND_POLL: [CallbackQueryHandler(send_feedback_poll)],
    },
    fallbacks=[],
    per_message=False
)

scheduler = AsyncIOScheduler()

async def start_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> FeedbackStates:
    # Check if there are recent events, show list of events that need feedback (is_active=0, feedback_sent=0, recent date)
    pass

async def select_feedback_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> FeedbackStates:
    # Select event, check if feedback already sent
    pass

async def send_feedback_poll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Send inline buttons 1-5 stars to participants
    # Schedule job to calculate average after 2 days and send to operator group
    # Update event feedback_sent = 1
    # For users clicking after 2 days, say expired
    pass

async def handle_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Callback for star buttons, check if within 2 days, save rating
    pass

async def calculate_average(job_context):
    # Calculate avg rating, send to group with #نمره and event hashtags
    pass

# Add handler for rating callbacks in Bot.py: CallbackQueryHandler(handle_rating, pattern="^rate_")
