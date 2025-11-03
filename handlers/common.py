# common.py
import re
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from config import CHANNEL_ID, ADMIN_IDS
from database import get_user_info, get_admin_info

def validate_national_id(national_id: str) -> bool:
    if not re.match(r"^\d{10}$", national_id):
        return False
    check = int(national_id[9])
    total = sum(int(national_id[i]) * (10 - i) for i in range(9)) % 11
    return total < 2 and check == total or total >= 2 and check == 11 - total

def get_main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    buttons = [
        ["دوره‌ها/بازدیدها 📅", "ویرایش مشخصات ✏️"],
        ["ارتباط با پشتیبانی 📞", "سوالات متداول ❓"],
        ["لغو/شروع دوباره 🚪"]
    ]
    if is_admin:
        buttons.insert(-1, ["منوی ادمین ⚙️"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([
        ["اضافه کردن رویداد جدید ➕", "تغییر رویداد فعال ✏️"],
        ["غیرفعال/فعال کردن رویداد 🔄", "مدیریت ادمین‌ها 👤"],
        ["اعلان عمومی 📢", "گزارش‌ها 📊"],
        ["اضافه کردن دستی به ثبت‌نام 📋", "ارسال نظرخواهی ⭐"],
        ["لغو/شروع دوباره 🚪"],
        ["بازگشت 🔙"]
    ], resize_keyboard=True)

async def check_channel_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, update.effective_user.id)
        return member.status in ["member", "administrator", "creator"]
    except Forbidden:
        return False

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS and not await get_admin_info(user_id):
        await update.message.reply_text("شما دسترسی ادمین ندارید! 🚫")
        return
    await update.message.reply_text("منوی ادمین:", reply_markup=get_admin_menu())

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_info = await get_user_info(user_id)
    full_name = user_info['full_name'] if user_info else "کاربر"
    is_admin = user_id in ADMIN_IDS or bool(await get_admin_info(user_id))
    await update.message.reply_text(
        f"{full_name} عزیز، به منوی اصلی بازگشتید.",
        reply_markup=get_main_menu(is_admin)
    )

async def payment_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Implementation moved from original code, assuming it's common
    # ... (add the payment_action logic here if it's not admin-specific)
    pass  # Placeholder, implement as per original
