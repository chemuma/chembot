# Bot.py
import logging
from telegram.ext import Application
from config import BOT_TOKEN
from database import init_db
from user_profile import (
    profile_conv,
    edit_profile_conv,
    reset_bot,
    handle_support_message,
)
from user_event import (
    show_events,
    event_details,
    register_event,
    handle_payment_receipt,
    check_membership,
)
from admin_events import (
    add_event_conv,
    edit_event_conv,
    toggle_event_conv,
)
from admin_managment import (
    announce_conv,
    manage_admins_conv,
    manual_reg_conv,
    report_conv,
)
from admin_feedback import feedback_conv
from common import (
    admin_menu,
    back_to_main,
    payment_action,
)

# تنظیم لاگر
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def main() -> None:
    """راه‌اندازی ربات"""
    # ایجاد دیتابیس
    import asyncio
    asyncio.run(init_db())

    # ساخت اپلیکیشن
    app = Application.builder().token(BOT_TOKEN).build()

    # --- ثبت هندلرها ---

    # پروفایل کاربر
    app.add_handler(profile_conv)
    app.add_handler(edit_profile_conv)

    # رویدادهای کاربر
    app.add_handler(show_events)
    app.add_handler(event_details)
    app.add_handler(register_event)
    app.add_handler(handle_payment_receipt)

    # مدیریت ادمین
    app.add_handler(add_event_conv)
    app.add_handler(edit_event_conv)
    app.add_handler(toggle_event_conv)
    app.add_handler(announce_conv)
    app.add_handler(manage_admins_conv)
    app.add_handler(manual_reg_conv)
    app.add_handler(report_conv)
    app.add_handler(feedback_conv)

    # منوها و دستورات عمومی
    app.add_handler(admin_menu)
    app.add_handler(back_to_main)
    app.add_handler(reset_bot)
    app.add_handler(faq)
    app.add_handler(handle_support_message)

    # دکمه‌های شیشه‌ای
    app.add_handler(payment_action)
    app.add_handler(check_membership)

    # --- شروع ربات ---
    logger.info("ربات در حال راه‌اندازی است...")
    app.run_polling(
        allowed_updates=[
            "message",
            "edited_message",
            "callback_query",
            "chat_member",
            "my_chat_member",
        ]
    )


if __name__ == "__main__":
    main()
