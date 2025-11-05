# main.py
import asyncio
import logging
from telegram import Update, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)
from config import BOT_TOKEN, CHANNEL_ID, OPERATOR_GROUP_ID, ADMIN_IDS
from database import init_db
from handlers.common import (
    show_main_menu, cancel, reset_bot, faq, handle_support_message,
    get_main_menu, get_admin_row, back_to_main_menu
)
from handlers.user_profile import profile_conv
from handlers.user_events import (
    show_events, event_details, register_event, handle_payment_receipt,
    payment_action
)
from handlers.admin_events import admin_events_conv
from handlers.admin_management import admin_management_conv
from handlers.admin_feedback import feedback_conv, handle_rating
from handlers.admin_reports import reports_menu, report_handler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Admin Menu ---
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS and not await get_admin_row(user_id):
        await update.message.reply_text("دسترسی ندارید!")
        return
    await update.message.reply_text(
        "منوی ادمین:",
        reply_markup=get_admin_menu()
    )

# --- Manual Registration ---
async def manual_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS and not await get_admin_row(user_id):
        await update.message.reply_text("دسترسی ندارید!")
        return

    if len(context.args) < 2:
        await update.message.reply_text("استفاده: /manual_reg <event_id> <user_id>")
        return

    try:
        event_id = int(context.args[0])
        target_user_id = int(context.args[1])
    except ValueError:
        await update.message.reply_text("آیدی‌ها باید عدد باشند.")
        return

    async with aiosqlite.connect("chemeng_bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)) as cursor:
            event = await cursor.fetchone()
        if not event or not event["is_active"]:
            await update.message.reply_text("رویداد معتبر یا فعال نیست.")
            return

    # Simulate free registration
    from handlers.user_events import _register_free_event
    await _register_free_event(target_user_id, event, context)
    await update.message.reply_text("ثبت‌نام دستی انجام شد.")

# --- Start Command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    return await profile_conv(update, context) 
    
# --- Main ---
async def main() -> None:
    await init_db()

    application = Application.builder().token(BOT_TOKEN).build()

    # User Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex("^دوره‌ها/بازدیدها$"), show_events))
    application.add_handler(MessageHandler(filters.Regex("^سوالات متداول$"), faq))
    application.add_handler(MessageHandler(filters.Regex("^ارتباط با پشتیبانی$"), lambda u, c: u.message.reply_text("پیام خود را بنویسید:")))
    application.add_handler(MessageHandler(filters.Regex("^لغو/شروع دوباره$"), reset_bot))

    # Profile
    application.add_handler(profile_conv)

    # Events
    application.add_handler(CallbackQueryHandler(event_details, pattern=r"^event_\d+$"))
    application.add_handler(CallbackQueryHandler(register_event, pattern=r"^register_\d+$"))
    application.add_handler(MessageHandler(filters.PHOTO & filters.Chat(OPERATOR_GROUP_ID), payment_action))
    application.add_handler(CallbackQueryHandler(payment_action, pattern=r"^(confirm|unclear|cancel|done)_"))

    # Admin
    application.add_handler(MessageHandler(filters.Regex("^منوی ادمین$"), admin_menu))
    application.add_handler(admin_events_conv)
    application.add_handler(admin_management_conv)
    application.add_handler(feedback_conv)
    application.add_handler(MessageHandler(filters.Regex("^گزارش‌ها$"), reports_menu))
    application.add_handler(CallbackQueryHandler(report_handler, pattern=r"^report_"))
    application.add_handler(CallbackQueryHandler(handle_rating, pattern=r"^rate_\d+_\d+$"))
    application.add_handler(CommandHandler("manual_reg", manual_registration))

    # Support & Back
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_support_message))
    application.add_handler(MessageHandler(filters.Regex("^بازگشت$"), back_to_main_menu))

    # Set Commands
    await application.bot.set_my_commands([
        BotCommand("start", "شروع ربات"),
    ])

    logger.info("ربات شروع شد...")
    await application.run_polling()

# main.py - انتهای فایل
if __name__ == '__main__':
    print("ربات در حال اجراست...")
    import asyncio
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())  # این باید باشه!
