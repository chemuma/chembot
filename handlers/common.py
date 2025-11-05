# handlers/common.py
from telegram import (
    Update, ReplyKeyboardMarkup, InlineKeyboardMarkup,
    InlineKeyboardButton, KeyboardButton
)
from telegram.ext import ContextTypes, ConversationHandler, filters
from config import CHANNEL_ID, OPERATOR_GROUP_ID, ADMIN_IDS
from database import init_db
import aiosqlite
from datetime import datetime
import re
import logging 
logger = logging.getLogger(__name__)
# --- Utility Functions ---
async def check_channel_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = update.callback_query

    # فقط اگر از دکمه اومده بود
    if query:
        await query.answer()

    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        if member.status in ["member", "administrator", "creator"]:
            if query:
                await query.edit_message_text("عضو هستید! در حال ورود...")
            await show_main_menu(update, context)
            return
    except Exception as e:
        logger.error(f"خطا در چک عضویت: {e}")

    # اگر عضو نیست
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("عضویت در کانال", url=f"https://t.me/{CHANNEL_ID.lstrip('@')}")
    ], [
        InlineKeyboardButton("عضو شدم", callback_data="check_membership")
    ]])

    if query:
        await query.edit_message_text("برای استفاده، ابتدا عضو کانال شوید:", reply_markup=keyboard)
    else:
        await update.message.reply_text("برای استفاده، ابتدا عضو کانال شوید:", reply_markup=keyboard)
async def get_user_row(user_id: int) -> aiosqlite.Row | None:
    async with aiosqlite.connect("chemeng_bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def get_admin_row(user_id: int) -> aiosqlite.Row | None:
    async with aiosqlite.connect("chemeng_bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM admins WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

def get_main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    buttons = [
        ["دوره‌ها/بازدیدها", "ویرایش مشخصات"],
        ["ارتباط با پشتیبانی", "سوالات متداول"],
        ["لغو/شروع دوباره"]
    ]
    if is_admin:
        buttons.insert(-1, ["منوی ادمین"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([
        ["اضافه کردن رویداد جدید", "تغییر رویداد فعال"],
        ["غیرفعال/فعال کردن رویداد", "مدیریت ادمین‌ها"],
        ["اعلان عمومی", "گزارش‌ها"],
        ["اضافه کردن دستی به ثبت‌نام", "ارسال نظرخواهی"],
        ["لغو/شروع دوباره", "بازگشت"]
    ], resize_keyboard=True)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, custom_text: str = None):
    user_id = update.effective_user.id
    user = await get_user_row(user_id)
    full_name = user["full_name"] if user else "کاربر"
    is_admin = user_id in ADMIN_IDS or bool(await get_admin_row(user_id))
    text = custom_text or f"{full_name} عزیز، به ربات انجمن مهندسی شیمی خوش آمدید!"
    await update.message.reply_text(text, reply_markup=get_main_menu(is_admin))

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user = await get_user_row(user_id)
    full_name = user["full_name"] if user else "کاربر"
    is_admin = user_id in ADMIN_IDS or bool(await get_admin_row(user_id))
    await update.message.reply_text(
        f"{full_name} عزیز، عملیات لغو شد.",
        reply_markup=get_main_menu(is_admin)
    )
    return ConversationHandler.END

async def reset_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await show_main_menu(update, context, "شروع دوباره!")

async def faq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    is_admin = user_id in ADMIN_IDS or bool(await get_admin_row(user_id))
    text = (
        "**سوالات متداول**\n\n"
        "1️⃣ **چطور ثبت‌نام کنم؟**\n"
        "از منو » دوره‌ها/بازدیدها » رویداد » ثبت‌نام\n\n"
        "2️⃣ **پرداخت چطوره؟**\n"
        "برای رویدادهای پولی، رسید به کارت واریز کنید.\n\n"
        "3️⃣ **ویرایش پروفایل؟**\n"
        "از منو » ویرایش مشخصات\n\n"
        "4️⃣ **پشتیبانی؟**\n"
        "از منو » ارتباط با پشتیبانی\n\n"
        "5️⃣ **وضعیت ثبت‌نام؟**\n"
        "تأییدیه دریافت می‌کنید. در غیر این صورت با پشتیبانی تماس بگیرید."
    )
    await update.message.reply_text(text, reply_markup=get_main_menu(is_admin))

async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_row = await get_user_row(user.id)
    identifier = f"@{user.username}" if user.username else f"شماره: {user_row['phone'] if user_row else 'نامشخص'}"
    text = f"درخواست پشتیبانی از {identifier}:\n{update.message.text}"
    message = await context.bot.send_message(OPERATOR_GROUP_ID, text)
    async with aiosqlite.connect("chemeng_bot.db") as db:
        await db.execute(
            "INSERT INTO operator_messages (message_id, chat_id, user_id, event_id, message_type, sent_at) VALUES (?, ?, ?, ?, ?, ?)",
            (message.message_id, OPERATOR_GROUP_ID, user.id, 0, "support", datetime.now().isoformat())
        )
        await db.commit()
    is_admin = user.id in ADMIN_IDS or bool(await get_admin_row(user.id))
    await update.message.reply_text(
        "پیام شما به تیم پشتیبانی ارسال شد. در اسرع وقت پاسخ خواهیم داد.",
        reply_markup=get_main_menu(is_admin)
    )
async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_main_menu(update, context, "به منوی اصلی بازگشتید.")
