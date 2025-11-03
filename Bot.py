# Bot.py
import logging
from telegram.ext import Application
from config import BOT_TOKEN
from database import init_db

# --- هندلرها از پوشه handlers ---
from handlers.user_profile import (
    profile_conv,
    edit_profile_conv,
    reset_bot,
    handle_support_message,
)
from handlers.user_events import (
    show_events,
    event_details,
    register_event,
    handle_payment_receipt,
    check_membership,
)
from handlers.admin_events import (
    add_event_conv,
    edit_event_conv,
    toggle_event_conv,
)
from handlers.admin_management import (
    announce_conv,
    manage_admins_conv,
    manual_reg_conv,
    report_conv,
)
from handlers.admin_feedback import feedback_conv
from handlers.common import (
    admin_menu,
    back_to_main,
    payment_action,
)

# --- باقی کد بدون تغییر ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

def main() -> None:
    import asyncio
    asyncio.run(init_db())

    app = Application.builder().token(BOT_TOKEN).build()

    # --- ثبت هندلرها ---
    app.add_handler(profile_conv)
    app.add_handler(edit_profile_conv)
    app.add_handler(show_events)
    app.add_handler(event_details)
    app.add_handler(register_event)
    app.add_handler(handle_payment_receipt)
    app.add_handler(add_event_conv)
    app.add_handler(edit_event_conv)
    app.add_handler(toggle_event_conv)
    app.add_handler(announce_conv)
    app.add_handler(manage_admins_conv)
    app.add_handler(manual_reg_conv)
    app.add_handler(report_conv)
    app.add_handler(feedback_conv)
    app.add_handler(admin_menu)
    app.add_handler(back_to_main)
    app.add_handler(reset_bot)
    app.add_handler(handle_support_message)
    app.add_handler(payment_action)
    app.add_handler(check_membership)

    # --- هندلر امتیازدهی ---
    from handlers.admin_feedback import handle_rating
    app.add_handler(CallbackQueryHandler(handle_rating, pattern="^rate_"))

    logger.info("ربات در حال راه‌اندازی است...")
    app.run_polling(allowed_updates=[
        "message", "edited_message", "callback_query", "chat_member", "my_chat_member"
    ])

if __name__ == "__main__":
    main()
