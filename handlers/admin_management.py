# handlers/admin_management.py
import re
import logging
from enum import Enum, auto
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler,
    filters, ContextTypes
)

import database as db
from config import OPERATOR_GROUP_ID
from handlers.common import get_admin_menu, cancel, is_user_admin
from handlers.user_events import deactivate_event  # اگر نیاز باشه

logger = logging.getLogger(__name__)

# --- States ---
class AnnounceState(Enum):
    CHOOSE_GROUP = auto()
    GET_MESSAGE = auto()

class AdminManageState(Enum):
    CHOOSE_ACTION = auto()
    GET_ID_TO_ADD = auto()
    CHOOSE_TO_REMOVE = auto()

class ManualRegState(Enum):
    CHOOSE_EVENT = auto()
    GET_STUDENT_ID = auto()
    CONFIRM = auto()

class ReportState(Enum):
    CHOOSE_TYPE = auto()
    CHOOSE_PERIOD_OR_EVENT = auto()

# --- Admin Menu Entry ---
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_user_admin(update.effective_user.id):
        await update.message.reply_text("شما دسترسی ادمین ندارید! 🚫")
        return
    await update.message.reply_text("منوی ادمین:", reply_markup=get_admin_menu())

# --- 1. Announce Conversation ---
async def announce_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await is_user_admin(update.effective_user.id):
        return ConversationHandler.END
        
    events = await db.get_all_events()
    buttons = [[InlineKeyboardButton(f"{event['title']} ({event['type']})", callback_data=f"announce_group_{event['event_id']}")] for event in events]
    buttons.append([InlineKeyboardButton("همه کاربران", callback_data="announce_group_all")])
    
    await update.message.reply_text("گروه هدف اعلان را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
    return AnnounceState.CHOOSE_GROUP.value

async def announce_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    group_data = query.data.split("announce_group_")[1]
    context.user_data["announce_group"] = group_data
    await query.message.edit_text("لطفاً متن اعلان را وارد کنید:")
    return AnnounceState.GET_MESSAGE.value

async def send_announcement(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message.text
    group = context.user_data["announce_group"]
    sent_count = 0
    if group == "all":
        async with db.get_db_connection() as conn:
            cursor = await conn.execute("SELECT user_id FROM users")
            users = await cursor.fetchall()
        for user in users:
            try:
                await context.bot.send_message(user['user_id'], message)
                sent_count += 1
                await asyncio.sleep(0.1)  # جلوگیری از rate limit
            except Exception as e:
                logger.warning(f"Failed to send to {user['user_id']}: {e}")
    else:
        event_id = int(group)
        participants = await db.get_event_participants(event_id)
        for participant in participants:
            try:
                await context.bot.send_message(participant['user_id'], message)
                sent_count += 1
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.warning(f"Failed to send to {participant['user_id']}: {e}")
    await update.message.reply_text(f"اعلان به {sent_count} نفر ارسال شد! ✅", reply_markup=get_admin_menu())
    context.user_data.clear()
    return ConversationHandler.END

announce_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(اعلان عمومی 📢)$"), announce_start)],
    states={
        AnnounceState.CHOOSE_GROUP.value: [CallbackQueryHandler(announce_group, pattern="^announce_group_")],
        AnnounceState.GET_MESSAGE.value: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_announcement)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=False
)

# --- 2. Manage Admins Conversation ---
async def manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await is_user_admin(update.effective_user.id):
        return ConversationHandler.END
    await update.message.reply_text(
        "لطفاً یکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("اضافه کردن ادمین ➕", callback_data="add_admin")],
            [InlineKeyboardButton("حذف ادمین ➖", callback_data="remove_admin")]
        ])
    )
    return AdminManageState.CHOOSE_ACTION.value

async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.message.edit_text("لطفاً آیدی عددی ادمین جدید را وارد کنید:")
    return AdminManageState.GET_ID_TO_ADD.value

async def save_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    admin_id = update.message.text.strip()
    if not re.match(r"^\d+$", admin_id):
        await update.message.reply_text("آیدی باید عددی باشد. دوباره وارد کنید:")
        return AdminManageState.GET_ID_TO_ADD.value
    admin_id = int(admin_id)
    try:
        async with db.get_db_connection() as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?, ?)",
                (admin_id, datetime.now().isoformat())
            )
            await conn.commit()
        await update.message.reply_text("ادمین با موفقیت اضافه شد! ✅", reply_markup=get_admin_menu())
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error adding admin: {e}")
        await update.message.reply_text("خطا در اضافه کردن ادمین.", reply_markup=get_admin_menu())
        return ConversationHandler.END

async def remove_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    async with db.get_db_connection() as conn:
        cursor = await conn.execute("SELECT user_id FROM admins")
        admins = await cursor.fetchall()
    if not admins:
        await query.message.edit_text("هیچ ادمینی وجود ندارد!", reply_markup=get_admin_menu())
        return ConversationHandler.END
    buttons = [[InlineKeyboardButton(str(admin['user_id']), callback_data=f"remove_{admin['user_id']}")] for admin in admins]
    await query.message.edit_text("ادمین را برای حذف انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
    return AdminManageState.CHOOSE_TO_REMOVE.value

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    admin_id = int(query.data.split("_")[1])
    try:
        async with db.get_db_connection() as conn:
            await conn.execute("DELETE FROM admins WHERE user_id = ?", (admin_id,))
            await conn.commit()
        await query.message.edit_text("ادمین با موفقیت حذف شد! ✅", reply_markup=get_admin_menu())
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error removing admin: {e}")
        await query.message.edit_text("خطا در حذف ادمین.", reply_markup=get_admin_menu())
        return ConversationHandler.END

manage_admins_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(مدیریت ادمین‌ها 👤)$"), manage_admins)],
    states={
        AdminManageState.CHOOSE_ACTION.value: [
            CallbackQueryHandler(add_admin_start, pattern="^add_admin$"),
            CallbackQueryHandler(remove_admin_start, pattern="^remove_admin$"),
        ],
        AdminManageState.GET_ID_TO_ADD.value: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_admin)],
        AdminManageState.CHOOSE_TO_REMOVE.value: [CallbackQueryHandler(remove_admin, pattern="^remove_")],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=False
)

# --- 3. Manual Registration Conversation ---
async def manual_registration_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await is_user_admin(update.effective_user.id):
        return ConversationHandler.END
    events = await db.get_all_events(active_only=True)
    if not events:
        await update.message.reply_text("هیچ رویداد فعالی وجود ندارد!", reply_markup=get_admin_menu())
        return ConversationHandler.END
    buttons = [[InlineKeyboardButton(event['title'], callback_data=f"manual_reg_{event['event_id']}")] for event in events]
    await update.message.reply_text("رویداد را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
    return ManualRegState.CHOOSE_EVENT.value

async def manual_registration_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split("_")[2])
    context.user_data["manual_event_id"] = event_id
    await query.message.edit_text("لطفاً شماره دانشجویی کاربر را وارد کنید:")
    return ManualRegState.GET_STUDENT_ID.value

async def manual_registration_student_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    student_id = update.message.text.strip()
    async with db.get_db_connection() as conn:
        cursor = await conn.execute("SELECT user_id FROM users WHERE student_id = ?", (student_id,))
        user = await cursor.fetchone()
    if not user:
        await update.message.reply_text("کاربر با این شماره دانشجویی یافت نشد. دوباره وارد کنید:")
        return ManualRegState.GET_STUDENT_ID.value
    context.user_data["manual_user_id"] = user['user_id']
    text = f"ثبت‌نام کاربر {student_id} در رویداد را تأیید می‌کنید؟"
    buttons = [
        [InlineKeyboardButton("تأیید ✅", callback_data="confirm_manual_reg")],
        [InlineKeyboardButton("لغو 🚫", callback_data="cancel_manual_reg")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    return ManualRegState.CONFIRM.value

async def confirm_manual_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel_manual_reg":
        await query.message.edit_text("ثبت‌نام دستی لغو شد.", reply_markup=get_admin_menu())
        return ConversationHandler.END
    user_id = context.user_data["manual_user_id"]
    event_id = context.user_data["manual_event_id"]
    try:
        async with db.get_db_connection() as conn:
            await conn.execute(
                "INSERT INTO registrations (user_id, event_id, registered_at) VALUES (?, ?, ?)",
                (user_id, event_id, datetime.now().isoformat())
            )
            await conn.execute(
                "UPDATE events SET current_capacity = current_capacity + 1 WHERE event_id = ?",
                (event_id,)
            )
            await conn.commit()
        # چک ظرفیت و deactivate اگر پر شد
        event = await db.get_event_details(event_id)
        if event['capacity'] > 0 and event['current_capacity'] >= event['capacity']:
            await deactivate_event(event_id, "ظرفیت پر شد")  # اگر تابع وجود داشته باشه
        await query.message.edit_text("ثبت‌نام دستی با موفقیت انجام شد! ✅", reply_markup=get_admin_menu())
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error manual reg: {e}")
        await query.message.edit_text("خطا در ثبت.", reply_markup=get_admin_menu())
        return ConversationHandler.END

manual_reg_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(اضافه کردن دستی به ثبت‌نام 📋)$"), manual_registration_start)],
    states={
        ManualRegState.CHOOSE_EVENT.value: [CallbackQueryHandler(manual_registration_event, pattern="^manual_reg_")],
        ManualRegState.GET_STUDENT_ID.value: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_registration_student_id)],
        ManualRegState.CONFIRM.value: [CallbackQueryHandler(confirm_manual_registration, pattern="^(confirm_manual_reg|cancel_manual_reg)$")],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=False
)

# --- 4. Reports Conversation ---
async def report_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await is_user_admin(update.effective_user.id):
        return ConversationHandler.END
    buttons = [
        [InlineKeyboardButton("گزارش ثبت‌نام‌ها", callback_data="report_registrations")],
        [InlineKeyboardButton("گزارش پرداخت‌ها", callback_data="report_payments")],
        [InlineKeyboardButton("لیست نهایی شرکت‌کنندگان", callback_data="report_final_list")]
    ]
    await update.message.reply_text("نوع گزارش را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
    return ReportState.CHOOSE_TYPE.value

async def report_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["report_type"] = query.data.split("_")[1]
    events = await db.get_all_events()
    buttons = [[InlineKeyboardButton(event['title'], callback_data=f"report_event_{event['event_id']}")] for event in events]
    buttons.append([InlineKeyboardButton("یک هفته اخیر", callback_data="period_week")])
    buttons.append([InlineKeyboardButton("یک ماه اخیر", callback_data="period_month")])
    await query.message.edit_text("رویداد یا بازه زمانی را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
    return ReportState.CHOOSE_PERIOD_OR_EVENT.value

async def generate_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    report_type = context.user_data["report_type"]
    data = query.data
    if "period_" in data:
        period = data.split("_")[1]
        start_date = datetime.now() - timedelta(days=7 if period == "week" else 30)
        # منطق گزارش بر اساس بازه
        text = f"گزارش {report_type} برای {period}: ..."  # پر کن بر اساس db
    else:
        event_id = int(data.split("_")[2])
        # منطق گزارش برای رویداد
        text = f"گزارش {report_type} برای رویداد {event_id}: ..."  # پر کن
    await query.message.edit_text(text, reply_markup=get_admin_menu())
    context.user_data.clear()
    return ConversationHandler.END

report_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(گزارش‌ها 📊)$"), report_start)],
    states={
        ReportState.CHOOSE_TYPE.value: [CallbackQueryHandler(report_type, pattern="^report_")],
        ReportState.CHOOSE_PERIOD_OR_EVENT.value: [CallbackQueryHandler(generate_report, pattern="^(report_event_|period_)")],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=False
)
