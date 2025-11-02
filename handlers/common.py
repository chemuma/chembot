# handlers/common.py
import re
import logging
from enum import Enum, auto
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.error import Forbidden
from telegram.ext import (
    CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)

import database as db
from config import CHANNEL_ID, ADMIN_IDS

logger = logging.getLogger(__name__)

# --- States ---
class ProfileState(Enum):
    FULL_NAME = auto()
    CONFIRM_FULL_NAME = auto()
    NATIONAL_ID = auto()
    CONFIRM_NATIONAL_ID = auto()
    STUDENT_ID = auto()
    CONFIRM_STUDENT_ID = auto()
    PHONE = auto()
    CONFIRM_PHONE = auto()

# --- Utility Functions ---

def validate_national_id(national_id: str) -> bool:
    if not re.match(r"^\d{10}$", national_id):
        return False
    check = int(national_id[9])
    total = sum(int(national_id[i]) * (10 - i) for i in range(9)) % 11
    return total < 2 and check == total or total >= 2 and check == 11 - total

async def is_user_admin(user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True
    admin = await db.get_admin_info(user_id)
    return admin is not None

async def check_channel_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        user_id = update.effective_user.id
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Forbidden:
        logger.warning(f"Bot blocked or can't check membership for {user_id}")
        return False
    except Exception as e:
        logger.error(f"Error checking membership for {user_id}: {e}")
        return False

# --- Menu Functions ---

def get_main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    buttons = [
        ["دوره‌ها/بازدیدها (calendar)", "ویرایش مشخصات (pencil)"],
        ["ارتباط با پشتیبانی (phone)", "سوالات متداول (question)"],
        ["لغو/شروع دوباره (door)"]
    ]
    if is_admin:
        buttons.insert(-1, ["منوی ادمین (gear)"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([
        ["اضافه کردن رویداد جدید (plus)", "ویرایش رویدادها (pencil)"],
        ["غیرفعال/فعال کردن رویداد (switch)", "مدیریت ادمین‌ها (people)"],
        ["اعلان عمومی (megaphone)", "گزارش‌ها (chart)"],
        ["اضافه کردن دستی به ثبت‌نام (clipboard)", "ارسال نظرسنجی (star)"],
        ["لغو/شروع دوباره (door)", "بازگشت (back)"]
    ], resize_keyboard=True)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, full_name: str = None):
    user_id = update.effective_user.id
    if not full_name:
        user_info = await db.get_user_info(user_id)
        full_name = user_info['full_name'] if user_info else "کاربر"
    
    is_admin = await is_user_admin(user_id)
    text = f"{full_name} عزیز، به ربات انجمن مهندسی شیمی خوش آمدید! (party_popper)"
    await update.message.reply_text(text, reply_markup=get_main_menu(is_admin))

# --- Basic Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not await check_channel_membership(update, context):
        await update.message.reply_text(
            f"لطفاً ابتدا کانال رسمی را دنبال کنید: {CHANNEL_ID} (megaphone)",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("عضو شدم (check)", callback_data="check_membership")
            ]])
        )
        return ConversationHandler.END
        
    user_info = await db.get_user_info(user_id)
    if not user_info:
        await update.message.reply_text("لطفاً نام کامل خود را به فارسی وارد کنید (مثال: علی محمدی):")
        return ProfileState.FULL_NAME.value
    
    await show_main_menu(update, context, user_info['full_name'])
    return ConversationHandler.END

async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if await check_channel_membership(update, context):
        user_id = update.effective_user.id
        user_info = await db.get_user_info(user_id)
        if not user_info:
            await query.message.edit_text("لطفاً نام کامل خود را به فارسی وارد کنید (مثال: علی محمدی):")
            return ProfileState.FULL_NAME.value
        
        await show_main_menu(update, context, user_info['full_name'])
        await query.message.delete()
        return ConversationHandler.END
        
    await query.message.edit_text(
        f"شما هنوز عضو کانال نیستید. لطفاً ابتدا کانال را دنبال کنید: {CHANNEL_ID} (megaphone)",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("عضو شدم (check)", callback_data="check_membership")
        ]])
    )
    return ConversationHandler.END

async def reset_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    user_info = await db.get_user_info(update.effective_user.id)
    if not user_info:
        await update.message.reply_text("اطلاعات شما یافت نشد. لطفاً از ابتدا ثبت نام کنید.\nنام کامل خود را به فارسی وارد کنید:")
        return ProfileState.FULL_NAME.value
    await show_main_menu(update, context, user_info['full_name'])
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels any conversation and returns to main menu."""
    context.user_data.clear()
    user_info = await db.get_user_info(update.effective_user.id)
    if user_info:
        await show_main_menu(update, context, user_info['full_name'])
    else:
        await update.message.reply_text("عملیات لغو شد. برای شروع دوباره /start بزنید.")
    return ConversationHandler.END

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_info = await db.get_user_info(update.effective_user.id)
    if user_info:
        await show_main_menu(update, context, user_info['full_name'])
    else:
        await update.message.reply_text("لطفاً ابتدا ثبت نام کنید. /start")

async def faq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    faq_text = (
        "سوالات متداول:\n\n"
        "1. چطور ثبت نام کنم؟\n"
        "   → با زدن /start و وارد کردن اطلاعات\n\n"
        "2. چرا نمی‌تونم ثبت نام کنم؟\n"
        "   → باید عضو کانال @chemical_eng_uma باشید\n\n"
        "3. چطور پرداخت کنم؟\n"
        "   → بعد از ثبت نام، رسید را بفرستید\n\n"
        "4. چطور ادمین بشم؟\n"
        "   → فقط توسط ادمین اصلی"
    )
    await update.message.reply_text(faq_text, reply_markup=get_main_menu())

async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "متوجه نشدم (confused)\n"
        "لطفاً از منو استفاده کنید یا /start بزنید.",
        reply_markup=get_main_menu()
    )

async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from config import OPERATOR_GROUP_ID
    user = update.effective_user
    text = update.message.text
    try:
        await context.bot.send_message(
            OPERATOR_GROUP_ID,
            f"پیام پشتیبانی از {user.full_name} (@{user.username or 'بدون یوزرنیم'}):\n\n{text}"
        )
        await update.message.reply_text("پیام شما به پشتیبانی ارسال شد. به زودی پاسخ می‌دهیم (smiling_face)")
    except Exception as e:
        logger.error(f"Failed to forward support message: {e}")
        await update.message.reply_text("خطا در ارسال پیام. لطفاً دوباره تلاش کنید.")

# --- Profile Conversation Handlers ---

async def full_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if len(name) < 3 or not re.match(r"^[\u0600-\u06FF\s]+$", name):
        await update.message.reply_text("نام باید حداقل 3 حرف و فقط فارسی باشد. دوباره وارد کنید:")
        return ProfileState.FULL_NAME.value
    context.user_data["full_name"] = name
    await update.message.reply_text(
        f"آیا نام زیر درست است؟\n{name}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("بله (check)", callback_data="confirm_full_name"),
            InlineKeyboardButton("خیر (pencil)", callback_data="retry_full_name")
        ]])
    )
    return ProfileState.CONFIRM_FULL_NAME.value

async def confirm_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "retry_full_name":
        await query.message.reply_text("لطفاً نام کامل خود را دوباره وارد کنید:")
        await query.message.delete()
        return ProfileState.FULL_NAME.value
    await query.message.reply_text("لطفاً کد ملی خود را وارد کنید (10 رقم):")
    await query.message.delete()
    return ProfileState.NATIONAL_ID.value

async def national_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    nid = update.message.text.strip()
    if not validate_national_id(nid):
        await update.message.reply_text("کد ملی نامعتبر است. دوباره وارد کنید:")
        return ProfileState.NATIONAL_ID.value
    context.user_data["national_id"] = nid
    await update.message.reply_text(
        f"آیا کد ملی زیر درست است؟\n{nid}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("بله (check)", callback_data="confirm_national_id"),
            InlineKeyboardButton("خیر (pencil)", callback_data="retry_national_id")
        ]])
    )
    return ProfileState.CONFIRM_NATIONAL_ID.value

async def confirm_national_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "retry_national_id":
        await query.message.reply_text("لطفاً کد ملی خود را دوباره وارد کنید:")
        await query.message.delete()
        return ProfileState.NATIONAL_ID.value
    await query.message.reply_text("لطفاً شماره دانشجویی خود را وارد کنید:")
    await query.message.delete()
    return ProfileState.STUDENT_ID.value

async def student_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not re.match(r"^\d+$", text):
        await update.message.reply_text("شماره دانشجویی باید فقط شامل اعداد باشد. دوباره وارد کنید:")
        return ProfileState.STUDENT_ID.value
    context.user_data["student_id"] = text
    await update.message.reply_text(
        f"آیا شماره دانشجویی زیر درست است؟\n{text}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("بله (check)", callback_data="confirm_student_id"),
            InlineKeyboardButton("خیر (pencil)", callback_data="retry_student_id")
        ]])
    )
    return ProfileState.CONFIRM_STUDENT_ID.value

async def confirm_student_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "retry_student_id":
        await query.message.reply_text("لطفاً شماره دانشجویی خود را دوباره وارد کنید:")
        await query.message.delete()
        return ProfileState.STUDENT_ID.value
    await query.message.reply_text(
        "لطفاً شماره تماس خود را وارد کنید یا دکمه زیر را فشار دهید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("ارسال شماره تماس (phone)", request_contact=True)]],
            one_time_keyboard=True
        )
    )
    await query.message.delete()
    return ProfileState.PHONE.value

async def phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.contact:
        phone_num = update.message.contact.phone_number
        phone_num = phone_num.replace("+98", "0") if phone_num.startswith("+98") else phone_num
    else:
        phone_num = update.message.text.strip()
        if not re.match(r"^09\d{9}$", phone_num):
            await update.message.reply_text("شماره تماس باید 11 رقم و با 09 شروع شود. دوباره وارد کنید:")
            return ProfileState.PHONE.value
    context.user_data["phone"] = phone_num
    await update.message.reply_text(
        f"آیا شماره تماس زیر درست است؟\n{phone_num}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("بله (check)", callback_data="confirm_phone"),
            InlineKeyboardButton("خیر (pencil)", callback_data="retry_phone")
        ]])
    )
    return ProfileState.CONFIRM_PHONE.value

async def confirm_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "retry_phone":
        await query.message.reply_text(
            "لطفاً شماره تماس خود را دوباره وارد کنید...",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("ارسال شماره تماس (phone)", request_contact=True)]],
                one_time_keyboard=True
            )
        )
        await query.message.delete()
        return ProfileState.PHONE.value
        
    user_id = update.effective_user.id
    try:
        async with db.get_db_connection() as conn:  # اصلاح شد
            await conn.execute(
                """
                INSERT INTO users 
                (user_id, full_name, national_id, student_id, phone, created_at) 
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    context.user_data["full_name"],
                    context.user_data["national_id"],
                    context.user_data["student_id"],
                    context.user_data["phone"],
                    datetime.now().isoformat(),
                )
            )
            await conn.commit()
        
        await query.message.reply_text("پروفایل شما با موفقیت ایجاد شد! (check)")
        await show_main_menu(update, context, context.user_data["full_name"])
        await query.message.delete()
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error creating profile for {user_id}: {e}")
        await query.message.reply_text("خطایی در ایجاد پروفایل رخ داد. لطفاً دوباره تلاش کنید.")
        return ConversationHandler.END

# --- Conversation Handler ---
profile_conv = ConversationHandler(
    entry_points=[
        CommandHandler("start", start),
        MessageHandler(filters.Regex("^(لغو/شروع دوباره (door))$"), reset_bot)
    ],
    states={
        ProfileState.FULL_NAME.value: [MessageHandler(filters.TEXT & ~filters.COMMAND, full_name)],
        ProfileState.CONFIRM_FULL_NAME.value: [CallbackQueryHandler(confirm_full_name, pattern="^(confirm_full_name|retry_full_name)$")],
        ProfileState.NATIONAL_ID.value: [MessageHandler(filters.TEXT & ~filters.COMMAND, national_id)],
        ProfileState.CONFIRM_NATIONAL_ID.value: [CallbackQueryHandler(confirm_national_id, pattern="^(confirm_national_id|retry_national_id)$")],
        ProfileState.STUDENT_ID.value: [MessageHandler(filters.TEXT & ~filters.COMMAND, student_id)],
        ProfileState.CONFIRM_STUDENT_ID.value: [CallbackQueryHandler(confirm_student_id, pattern="^(confirm_student_id|retry_student_id)$")],
        ProfileState.PHONE.value: [
            MessageHandler(filters.CONTACT, phone),
            MessageHandler(filters.TEXT & ~filters.COMMAND, phone)
        ],
        ProfileState.CONFIRM_PHONE.value: [CallbackQueryHandler(confirm_phone, pattern="^(confirm_phone|retry_phone)$")],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=False
)
