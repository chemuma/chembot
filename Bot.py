# Bot.py
import logging
from telegram.ext import Application
from config import BOT_TOKEN
from user_profile import (
    profile_conv,
    edit_profile_conv,
    edit_profile_start,
    edit_profile,
    edit_profile_value,
    cancel,
    show_main_menu,
    reset_bot,
    faq,
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
    add_event,
    event_type,
    event_title,
    event_description,
    event_cost,
    event_date,
    event_location,
    event_capacity,
    save_event,
    edit_event_start,
    edit_event_select_field,
    edit_event_value,
    save_edited_event,
    toggle_event_status_start,
    toggle_event_status,
)
from admin_managment import (
    announce_conv,
    manage_admins_conv,
    manual_reg_conv,
    report_conv,
    announce_start,
    announce_group,
    send_announcement,
    manage_admins,
    add_admin,
    save_admin,
    remove_admin,
    manual_registration_start,
    manual_registration_event,
    manual_registration_student_id,
    confirm_manual_registration,
    report_start,
    report_type,
    generate_report,
)
from admin_feedback import (
    feedback_conv,
    start_feedback,
    select_feedback_event,
    send_feedback_poll,
)
from common import admin_menu, back_to_main, payment_action
from database import init_db

# تنظیم لاگر اصلی
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.WARNING
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

def main() -> None:
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # ثبت هندلرها
    app.add_handler(profile_conv)
    app.add_handler(edit_profile_conv)
    app.add_handler(add_event_conv)
    app.add_handler(edit_event_conv)
    app.add_handler(toggle_event_conv)
    app.add_handler(announce_conv)
    app.add_handler(manage_admins_conv)
    app.add_handler(manual_reg_conv)
    app.add_handler(report_conv)
    app.add_handler(feedback_conv)
    app.add_handler(MessageHandler(filters.Regex("^(دوره‌ها/بازدیدها 📅)$"), show_events))
    app.add_handler(MessageHandler(filters.Regex("^(ارتباط با پشتیبانی 📞)$"), handle_support_message))
    app.add_handler(MessageHandler(filters.Regex("^(سوالات متداول ❓)$"), faq))
    app.add_handler(MessageHandler(filters.Regex("^(لغو/شروع دوباره 🚪)$"), reset_bot))
    app.add_handler(MessageHandler(filters.Regex("^(منوی ادمین ⚙️)$"), admin_menu))
    app.add_handler(MessageHandler(filters.Regex("^(بازگشت 🔙)$"), back_to_main))
    app.add_handler(CallbackQueryHandler(event_details, pattern="^event_"))
    app.add_handler(CallbackQueryHandler(register_event, pattern="^register_"))
    app.add_handler(CallbackQueryHandler(payment_action, pattern="^(confirm_payment_|unclear_payment_|cancel_payment_|confirm_|done)"))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_payment_receipt))
    app.add_handler(CallbackQueryHandler(check_membership, pattern="^check_membership$"))
    app.add_handler(CallbackQueryHandler(show_events, pattern="^back_to_events$"))

    logger.info("Bot is starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
