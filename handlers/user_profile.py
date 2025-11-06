# handlers/user_profile.py
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ContextTypes, ConversationHandler, filters,
    CommandHandler, MessageHandler, CallbackQueryHandler
)
from .common import (
    get_main_menu, get_user_row, get_admin_row, show_main_menu,
    check_channel_membership, cancel
)
from config import CHANNEL_ID
import re
from datetime import datetime
import aiosqlite

from enum import IntEnum

class ProfileState(IntEnum):
    FULL_NAME = 0
    CONFIRM_FULL_NAME = 1
    NATIONAL_ID = 2
    CONFIRM_NATIONAL_ID = 3
    STUDENT_ID = 4
    CONFIRM_STUDENT_ID = 5
    PHONE = 6
    CONFIRM_PHONE = 7
    EDIT_PROFILE = 8
    EDIT_PROFILE_VALUE = 9

def validate_national_id(nid: str) -> bool:
    if not re.match(r"^\d{10}$", nid): return False
    check = int(nid[9])
    total = sum(int(nid[i]) * (10 - i) for i in range(9)) % 11
    return (total < 2 and check == total) or (total >= 2 and check == 11 - total)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_channel_membership(update, context):
        await update.message.reply_text(
            f"لطفاً ابتدا کانال رسمی را دنبال کنید: {CHANNEL_ID}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("عضو شدم", callback_data="check_membership")
            ]])
        )
        return ConversationHandler.END

    user = await get_user_row(update.effective_user.id)
    if not user:
        await update.message.reply_text("لطفاً نام کامل خود را به فارسی وارد کنید (مثال: علی محمدی):")
        return ProfileState.FULL_NAME

    await show_main_menu(update, context)
    return ConversationHandler.END

async def full_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not re.match(r"^[آ-ی\s]{6,}$", text) or text.count(" ") < 1:
        await update.message.reply_text("نام کامل باید حداقل 6 کاراکتر با حروف فارسی و شامل یک فاصله باشد. دوباره وارد کنید:")
        return ProfileState.FULL_NAME
    context.user_data["full_name"] = text
    await update.message.reply_text(
        f"آیا نام زیر درست است؟\n{text}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("بله", callback_data="confirm_full_name"),
            InlineKeyboardButton("خیر", callback_data="retry_full_name")
        ]])
    )
    return ProfileState.CONFIRM_FULL_NAME

async def confirm_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "retry_full_name":
        await query.message.reply_text("لطفاً نام کامل خود را دوباره وارد کنید:")
        await query.message.delete()
        return ProfileState.FULL_NAME
    await query.message.reply_text("لطفاً کد ملی 10 رقمی خود را وارد کنید:")
    await query.message.delete()
    return ProfileState.NATIONAL_ID

async def national_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if not validate_national_id(text):
        await update.message.reply_text("کد ملی نامعتبر است. لطفاً کد ملی 10 رقمی معتبر وارد کنید:")
        return ProfileState.NATIONAL_ID
    context.user_data["national_id"] = text
    await update.message.reply_text(
        f"آیا کد ملی زیر درست است؟\n{text}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("بله", callback_data="confirm_national_id"),
            InlineKeyboardButton("خیر", callback_data="retry_national_id")
        ]])
    )
    return ProfileState.CONFIRM_NATIONAL_ID

async def confirm_national_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "retry_national_id":
        await query.message.reply_text("لطفاً کد ملی خود را دوباره وارد کنید:")
        await query.message.delete()
        return ProfileState.NATIONAL_ID
    await query.message.reply_text("لطفاً شماره دانشجویی خود را وارد کنید:")
    await query.message.delete()
    return ProfileState.STUDENT_ID

async def student_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if not re.match(r"^\d+$", text):
        await update.message.reply_text("شماره دانشجویی باید فقط شامل اعداد باشد. دوباره وارد کنید:")
        return ProfileState.STUDENT_ID
    context.user_data["student_id"] = text
    await update.message.reply_text(
        f"آیا شماره دانشجویی زیر درست است؟\n{text}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("بله", callback_data="confirm_student_id"),
            InlineKeyboardButton("خیر", callback_data="retry_student_id")
        ]])
    )
    return ProfileState.CONFIRM_STUDENT_ID

async def confirm_student_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "retry_student_id":
        await query.message.reply_text("لطفاً شماره دانشجویی خود را دوباره وارد کنید:")
        await query.message.delete()
        return ProfileState.STUDENT_ID
    await query.message.reply_text(
        "لطفاً شماره تماس خود را وارد کنید یا دکمه زیر را فشار دهید:",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("ارسال شماره تماس", request_contact=True)]],
            one_time_keyboard=True
        )
    )
    await query.message.delete()
    return ProfileState.PHONE

async def phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.contact:
        phone = update.message.contact.phone_number
        phone = phone.replace("+98", "0") if phone.startswith("+98") else phone
    else:
        phone = update.message.text
        if not re.match(r"^09\d{9}$", phone):
            await update.message.reply_text("شماره تماس باید 11 رقم و با 09 شروع شود. دوباره وارد کنید:")
            return ProfileState.PHONE
    context.user_data["phone"] = phone
    await update.message.reply_text(
        f"آیا شماره تماس زیر درست است؟\n{phone}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("بله", callback_data="confirm_phone"),
            InlineKeyboardButton("خیر", callback_data="retry_phone")
        ]])
    )
    return ProfileState.CONFIRM_PHONE

async def confirm_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "retry_phone":
        await query.message.reply_text(
            "لطفاً شماره تماس خود را دوباره وارد کنید یا دکمه زیر را فشار دهید:",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("ارسال شماره تماس", request_contact=True)]],
                one_time_keyboard=True
            )
        )
        await query.message.delete()
        return ProfileState.PHONE

    user_id = update.effective_user.id
    async with aiosqlite.connect("chemeng_bot.db") as db:
        await db.execute(
            "INSERT INTO users (user_id, full_name, national_id, student_id, phone, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                user_id,
                context.user_data["full_name"],
                context.user_data["national_id"],
                context.user_data["student_id"],
                context.user_data["phone"],
                datetime.now().isoformat(),
            )
        )
        await db.commit()

    is_admin = user_id in ADMIN_IDS or bool(await get_admin_row(user_id))
    await query.message.reply_text(
        "پروفایل شما با موفقیت ایجاد شد!",
        reply_markup=get_main_menu(is_admin)
    )
    await query.message.delete()
    return ConversationHandler.END

# --- Edit Profile ---
async def edit_profile_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_channel_membership(update, context):
        await update.message.reply_text(
            f"لطفاً ابتدا کانال رسمی را دنبال کنید: {CHANNEL_ID}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("عضو شدم", callback_data="check_membership")
            ]])
        )
        return ConversationHandler.END

    user = await get_user_row(update.effective_user.id)
    if not user:
        await update.message.reply_text("ابتدا پروفایل خود را تکمیل کنید!", reply_markup=get_main_menu())
        return ConversationHandler.END

    text = (
        f"اطلاعات فعلی شما:\n"
        f"نام کامل: {user['full_name']}\n"
        f"کد ملی: {user['national_id']}\n"
        f"شماره دانشجویی: {user['student_id']}\n"
        f"شماره تماس: {user['phone']}"
    )
    buttons = [
        [InlineKeyboardButton("ویرایش نام", callback_data="edit_full_name")],
        [InlineKeyboardButton("ویرایش کد ملی", callback_data="edit_national_id")],
        [InlineKeyboardButton("ویرایش شماره دانشجویی", callback_data="edit_student_id")],
        [InlineKeyboardButton("ویرایش شماره تماس", callback_data="edit_phone")],
        [InlineKeyboardButton("لغو", callback_data="cancel_edit")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    return ProfileState.EDIT_PROFILE

async def edit_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if query.data == "cancel_edit":
        is_admin = user_id in ADMIN_IDS or bool(await get_admin_row(user_id))
        await query.message.reply_text("ویرایش لغو شد.", reply_markup=get_main_menu(is_admin))
        await query.message.delete()
        return ConversationHandler.END

    context.user_data["edit_field"] = query.data
    field_name = {
        "edit_full_name": "نام کامل",
        "edit_national_id": "کد ملی",
        "edit_student_id": "شماره دانشجویی",
        "edit_phone": "شماره تماس"
    }[query.data]

    if query.data == "edit_phone":
        await query.message.reply_text(
            f"لطفاً {field_name} جدید را وارد کنید یا دکمه زیر را فشار دهید:",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("ارسال شماره تماس", request_contact=True)]],
                one_time_keyboard=True
            )
        )
    else:
        await query.message.reply_text(f"لطفاً {field_name} جدید را وارد کنید:")

    await query.message.delete()
    return ProfileState.EDIT_PROFILE_VALUE

async def edit_profile_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    field = context.user_data["edit_field"]
    value = None

    if field == "edit_phone" and update.message.contact:
        value = update.message.contact.phone_number
        value = value.replace("+98", "0") if value.startswith("+98") else value
    else:
        value = update.message.text

    # Validation
    if field == "edit_full_name":
        if not re.match(r"^[آ-ی\s]{6,}$", value) or value.count(" ") < 1:
            await update.message.reply_text("نام کامل نامعتبر است. دوباره وارد کنید:")
            return ProfileState.EDIT_PROFILE_VALUE
    elif field == "edit_national_id":
        if not validate_national_id(value):
            await update.message.reply_text("کد ملی نامعتبر است.")
            return ProfileState.EDIT_PROFILE_VALUE
    elif field == "edit_student_id":
        if not re.match(r"^\d+$", value):
            await update.message.reply_text("شماره دانشجویی باید عددی باشد.")
            return ProfileState.EDIT_PROFILE_VALUE
    elif field == "edit_phone":
        if not re.match(r"^09\d{9}$", value):
            await update.message.reply_text("شماره تماس باید 11 رقم و با 09 شروع شود.")
            return ProfileState.EDIT_PROFILE_VALUE

    async with aiosqlite.connect("chemeng_bot.db") as db:
        column = field.replace("edit_", "")
        await db.execute(f"UPDATE users SET {column} = ? WHERE user_id = ?", (value, user_id))
        await db.commit()

    is_admin = user_id in ADMIN_IDS or bool(await get_admin_row(user_id))
    await update.message.reply_text("پروفایل شما با موفقیت ویرایش شد!", reply_markup=get_main_menu(is_admin))
    return ConversationHandler.END

# Conversation Handler
profile_conv = ConversationHandler(
    entry_points=[
        CommandHandler("start", start),
        MessageHandler(filters.Regex("^(ویرایش مشخصات)$"), edit_profile_start)
    ],
    states={
        ProfileState.FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, full_name)],
        ProfileState.CONFIRM_FULL_NAME: [CallbackQueryHandler(confirm_full_name)],
        ProfileState.NATIONAL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, national_id)],
        ProfileState.CONFIRM_NATIONAL_ID: [CallbackQueryHandler(confirm_national_id)],
        ProfileState.STUDENT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, student_id)],
        ProfileState.CONFIRM_STUDENT_ID: [CallbackQueryHandler(confirm_student_id)],
        ProfileState.PHONE: [
            MessageHandler(filters.CONTACT, phone),
            MessageHandler(filters.TEXT & ~filters.COMMAND, phone)
        ],
        ProfileState.CONFIRM_PHONE: [CallbackQueryHandler(confirm_phone)],
        ProfileState.EDIT_PROFILE: [CallbackQueryHandler(edit_profile)],
        ProfileState.EDIT_PROFILE_VALUE: [
            MessageHandler(filters.CONTACT | filters.TEXT & ~filters.COMMAND, edit_profile_value)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True
    per_message=False
)
