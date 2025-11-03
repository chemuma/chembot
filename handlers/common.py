# common.py
import re
import asyncio
from datetime import datetime
from typing import List, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from telegram.ext import ContextTypes
from telegram.constants import ChatMemberStatus
from telegram.error import Forbidden

from .config import CHANNEL_ID, ADMIN_IDS, OPERATOR_GROUP_ID, CARD_NUMBER
from .database import (
    get_user_info,
    get_admin_info,
    get_event,
    get_registrations_for_event,
    get_user_registration_count,
    register_user_to_event,
    execute,
)


# ==============================
# اعتبارسنجی‌ها
# ==============================

def validate_national_id(national_id: str) -> bool:
    """اعتبارسنجی کد ملی 10 رقمی"""
    if not re.match(r"^\d{10}$", national_id):
        return False
    digits = [int(d) for d in national_id]
    check = digits[9]
    total = sum(digits[i] * (10 - i) for i in range(9)) % 11
    return (total < 2 and check == total) or (total >= 2 and check == 11 - total)


def validate_phone(phone: str) -> bool:
    """اعتبارسنجی شماره موبایل ایرانی (09xxxxxxxxx)"""
    return bool(re.match(r"^09\d{9}$", phone))


def validate_full_name(name: str) -> bool:
    """نام کامل باید حداقل 6 حرف فارسی و شامل فاصله باشد"""
    return bool(re.match(r"^[آ-ی\s]{6,}$", name) and " " in name.strip())


# ==============================
# منوهای کیبورد
# ==============================

def get_main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """منوی اصلی کاربر"""
    buttons = [
        ["دوره‌ها/بازدیدها", "ویرایش مشخصات"],
        ["ارتباط با پشتیبانی", "سوالات متداول"],
        ["لغو/شروع دوباره"]
    ]
    if is_admin:
        buttons.insert(-1, ["منوی ادمین"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def get_admin_menu() -> ReplyKeyboardMarkup:
    """منوی ادمین"""
    return ReplyKeyboardMarkup([
        ["اضافه کردن رویداد جدید", "تغییر رویداد فعال"],
        ["غیرفعال/فعال کردن رویداد", "مدیریت ادمین‌ها"],
        ["اعلان عمومی", "گزارش‌ها"],
        ["اضافه کردن دستی به ثبت‌نام", "ارسال نظرخواهی"],
        ["لغو/شروع دوباره"],
        ["بازگشت"]
    ], resize_keyboard=True)


def remove_keyboard() -> ReplyKeyboardRemove:
    """حذف کیبورد"""
    return ReplyKeyboardRemove()


# ==============================
# چک عضویت در کانال
# ==============================

async def check_channel_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """بررسی عضویت کاربر در کانال رسمی"""
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, update.effective_user.id)
        return member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        ]
    except Forbidden:
        return False
    except Exception as e:
        print(f"خطا در چک عضویت: {e}")
        return False


async def require_channel_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """اگر عضو کانال نیست، پیام بده و True برگردان اگر عضو هست"""
    if await check_channel_membership(update, context):
        return True

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("عضو شدم", callback_data="check_membership")
    ]])
    await update.message.reply_text(
        f"لطفاً ابتدا در کانال رسمی عضو شوید:\n{CHANNEL_ID}",
        reply_markup=keyboard
    )
    return False


# ==============================
# چک ادمین بودن
# ==============================

async def is_admin(user_id: int) -> bool:
    """بررسی ادمین اصلی یا ادمین اضافه‌شده"""
    if user_id in ADMIN_IDS:
        return True
    admin = await get_admin_info(user_id)
    return bool(admin)


async def require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """اگر ادمین نیست، پیام بده و False برگردان"""
    if await is_admin(update.effective_user.id):
        return True
    await update.message.reply_text("شما دسترسی ادمین ندارید!")
    return False


# ==============================
# توابع کمکی نمایش
# ==============================

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None) -> None:
    """نمایش منوی اصلی با نام کاربر"""
    user_info = await get_user_info(update.effective_user.id)
    full_name = user_info["full_name"] if user_info else "کاربر"
    is_admin_user = await is_admin(update.effective_user.id)

    message_text = text or f"{full_name} عزیز، به ربات انجمن مهندسی شیمی خوش آمدید!"
    await update.message.reply_text(
        message_text,
        reply_markup=get_main_menu(is_admin_user)
    )


# ==============================
# مدیریت پرداخت (مشترک)
# ==============================

async def send_payment_request(update: Update, context: ContextTypes.DEFAULT_TYPE, event_id: int) -> None:
    """ارسال درخواست پرداخت به کاربر"""
    event = await get_event(event_id)
    context.user_data["pending_event_id"] = event_id

    await update.callback_query.message.reply_text(
        f"برای ثبت‌نام در **{event['title']}**، لطفاً مبلغ **{event['cost']:,} تومان** را به شماره کارت زیر واریز کنید:\n\n"
        f"`{CARD_NUMBER}`\n\n"
        "سپس **تصویر رسید** را ارسال کنید.",
        parse_mode="Markdown"
    )


# ==============================
# ثبت‌نام رایگان
# ==============================

async def register_free_event(update: Update, context: ContextTypes.DEFAULT_TYPE, event_id: int) -> None:
    """ثبت‌نام در رویداد رایگان"""
    user_id = update.effective_user.id
    event = await get_event(event_id)

    if not event["is_active"]:
        await update.callback_query.message.reply_text(
            f"رویداد غیرفعال است.\nدلیل: {event['deactivation_reason'] or 'نامشخص'}"
        )
        return

    if event["type"] != "دوره" and event["current_capacity"] >= event["capacity"]:
        await update.callback_query.message.reply_text(
            "ظرفیت رویداد تکمیل شده است.\nبرای لیست انتظار با پشتیبانی تماس بگیرید."
        )
        return

    success = await register_user_to_event(user_id, event_id)
    if not success:
        await update.callback_query.message.reply_text("شما قبلاً ثبت‌نام کرده‌اید!")
        return

    # ارسال اطلاعات به گروه اپراتورها
    user = await get_user_info(user_id)
    reg_count = await get_user_registration_count(event_id)
    hashtag = f"#{event['type']} #{event['hashtag'].replace(' ', '_')}"

    text = (
        f"{hashtag}\n"
        f"ثبت‌نام #{reg_count}:\n"
        f"نام: {user['full_name']}\n"
        f"کد ملی: {user['national_id']}\n"
        f"شماره دانشجویی: {user['student_id']}\n"
        f"شماره تماس: {user['phone']}"
    )

    try:
        message = await context.bot.send_message(OPERATOR_GROUP_ID, text)
        await execute(
            "INSERT INTO operator_messages (message_id, chat_id, user_id, event_id, message_type, sent_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (message.message_id, OPERATOR_GROUP_ID, user_id, event_id, "registration", datetime.now().isoformat())
        )
    except Exception as e:
        print(f"خطا در ارسال به گروه: {e}")

    await update.callback_query.message.reply_text("ثبت‌نام با موفقیت انجام شد!")
    
    # چک تکمیل ظرفیت
    if event["type"] != "دوره" and event["current_capacity"] + 1 >= event["capacity"]:
        from admin_events import deactivate_event
        await deactivate_event(event_id, "تکمیل ظرفیت", context)


# ==============================
# تأیید پرداخت (دکمه‌های شیشه‌ای)
# ==============================

async def payment_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """مدیریت دکمه‌های تأیید/رد پرداخت توسط ادمین"""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = update.effective_user.id

    if not await is_admin(user_id):
        await query.edit_message_text("شما دسترسی ندارید!")
        return

    if data.startswith("confirm_payment_"):
        payment_id = int(data.split("_")[2])
        # تأیید پرداخت
        await execute("UPDATE payments SET confirmed_at = ? WHERE payment_id = ?", 
                      (datetime.now().isoformat(), payment_id))
        await query.edit_message_text("پرداخت تأیید شد!")

    elif data.startswith("unclear_payment_"):
        await query.edit_message_text("رسید نامشخص است. لطفاً رسید واضح‌تری ارسال کنید.")

    elif data.startswith("cancel_payment_"):
        await query.edit_message_text("پرداخت لغو شد.")
