# user_profile.py
from enum import Enum, auto
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from common import (
    validate_national_id,
    validate_phone,
    validate_full_name,
    get_main_menu,
    require_channel_membership,
    show_main_menu,
    remove_keyboard,
)
from database import (
    get_user_info,
    create_user,
    update_user_field,
    is_admin,
)


# ==============================
# حالت‌های مکالمه پروفایل
# ==============================

class ProfileStates(Enum):
    FULL_NAME = auto()
    CONFIRM_FULL_NAME = auto()
    NATIONAL_ID = auto()
    CONFIRM_NATIONAL_ID = auto()
    STUDENT_ID = auto()
    CONFIRM_STUDENT_ID = auto()
    PHONE = auto()
    CONFIRM_PHONE = auto()


class EditProfileStates(Enum):
    SELECT_FIELD = auto()
    INPUT_VALUE = auto()


# ==============================
# ConversationHandler: ثبت‌نام اولیه
# ==============================

profile_conv = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        ProfileStates.FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, full_name)],
        ProfileStates.CONFIRM_FULL_NAME: [CallbackQueryHandler(confirm_full_name)],
        ProfileStates.NATIONAL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, national_id)],
        ProfileStates.CONFIRM_NATIONAL_ID: [CallbackQueryHandler(confirm_national_id)],
        ProfileStates.STUDENT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, student_id)],
        ProfileStates.CONFIRM_STUDENT_ID: [CallbackQueryHandler(confirm_student_id)],
        ProfileStates.PHONE: [
            MessageHandler(filters.CONTACT, phone),
            MessageHandler(filters.TEXT & ~filters.COMMAND, phone)
        ],
        ProfileStates.CONFIRM_PHONE: [CallbackQueryHandler(confirm_phone)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=False,
)


# ==============================
# توابع پروفایل
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """شروع ربات و چک عضویت"""
    if not await require_channel_membership(update, context):
        return ConversationHandler.END

    user_info = await get_user_info(update.effective_user.id)
    if user_info:
        await show_main_menu(update, context)
        return ConversationHandler.END

    await update.message.reply_text(
        "لطفاً نام کامل خود را به فارسی وارد کنید (مثال: علی محمدی):",
        reply_markup=remove_keyboard()
    )
    return ProfileStates.FULL_NAME


async def full_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not validate_full_name(text):
        await update.message.reply_text(
            "نام کامل باید حداقل 6 کاراکتر فارسی و شامل یک فاصله باشد. دوباره وارد کنید:"
        )
        return ProfileStates.FULL_NAME

    context.user_data["full_name"] = text
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("بله", callback_data="confirm_full_name"),
        InlineKeyboardButton("خیر", callback_data="retry_full_name")
    ]])
    await update.message.reply_text(f"آیا نام زیر درست است؟\n\n{text}", reply_markup=keyboard)
    return ProfileStates.CONFIRM_FULL_NAME


async def confirm_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "retry_full_name":
        await query.edit_message_text("لطفاً نام کامل خود را دوباره وارد کنید:")
        return ProfileStates.FULL_NAME

    await query.edit_message_text("لطفاً کد ملی 10 رقمی خود را وارد کنید:")
    return ProfileStates.NATIONAL_ID


async def national_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not validate_national_id(text):
        await update.message.reply_text("کد ملی نامعتبر است. لطفاً 10 رقم معتبر وارد کنید:")
        return ProfileStates.NATIONAL_ID

    context.user_data["national_id"] = text
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("بله", callback_data="confirm_national_id"),
        InlineKeyboardButton("خیر", callback_data="retry_national_id")
    ]])
    await update.message.reply_text(f"آیا کد ملی زیر درست است؟\n\n{text}", reply_markup=keyboard)
    return ProfileStates.CONFIRM_NATIONAL_ID


async def confirm_national_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "retry_national_id":
        await query.edit_message_text("لطفاً کد ملی خود را دوباره وارد کنید:")
        return ProfileStates.NATIONAL_ID

    await query.edit_message_text("لطفاً شماره دانشجویی خود را وارد کنید:")
    return ProfileStates.STUDENT_ID


async def student_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("شماره دانشجویی باید فقط شامل اعداد باشد. دوباره وارد کنید:")
        return ProfileStates.STUDENT_ID

    context.user_data["student_id"] = text
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("بله", callback_data="confirm_student_id"),
        InlineKeyboardButton("خیر", callback_data="retry_student_id")
    ]])
    await update.message.reply_text(f"آیا شماره دانشجویی زیر درست است؟\n\n{text}", reply_markup=keyboard)
    return ProfileStates.CONFIRM_STUDENT_ID


async def confirm_student_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "retry_student_id":
        await query.edit_message_text("لطفاً شماره دانشجویی خود را دوباره وارد کنید:")
        return ProfileStates.STUDENT_ID

    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("ارسال شماره تماس", request_contact=True)]],
        one_time_keyboard=True,
        resize_keyboard=True
    )
    await query.edit_message_text(
        "لطفاً شماره تماس خود را وارد کنید یا دکمه زیر را فشار دهید:",
        reply_markup=keyboard
    )
    return ProfileStates.PHONE


async def phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.contact:
        phone = update.message.contact.phone_number
        phone = phone.replace("+98", "0") if phone.startswith("+98") else phone
    else:
        phone = update.message.text.strip()

    if not validate_phone(phone):
        await update.message.reply_text("شماره تماس باید 11 رقم و با 09 شروع شود. دوباره وارد کنید:")
        return ProfileStates.PHONE

    context.user_data["phone"] = phone
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("بله", callback_data="confirm_phone"),
        InlineKeyboardButton("خیر", callback_data="retry_phone")
    ]])
    await update.message.reply_text(f"آیا شماره تماس زیر درست است؟\n\n{phone}", reply_markup=keyboard)
    return ProfileStates.CONFIRM_PHONE


async def confirm_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "retry_phone":
        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("ارسال شماره تماس", request_contact=True)]],
            one_time_keyboard=True
        )
        await query.edit_message_text(
            "لطفاً شماره تماس خود را دوباره وارد کنید:",
            reply_markup=keyboard
        )
        return ProfileStates.PHONE

    user_id = update.effective_user.id
    await create_user(
        user_id=user_id,
        full_name=context.user_data["full_name"],
        national_id=context.user_data["national_id"],
        student_id=context.user_data["student_id"],
        phone=context.user_data["phone"]
    )

    is_admin_user = await is_admin(user_id)
    await query.edit_message_text(
        "پروفایل شما با موفقیت ایجاد شد!",
        reply_markup=get_main_menu(is_admin_user)
    )
    return ConversationHandler.END


# ==============================
# ویرایش پروفایل
# ==============================

edit_profile_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(ویرایش مشخصات)$"), edit_profile_start)],
    states={
        EditProfileStates.SELECT_FIELD: [CallbackQueryHandler(edit_profile_field)],
        EditProfileStates.INPUT_VALUE: [
            MessageHandler(filters.CONTACT, edit_profile_value),
            MessageHandler(filters.TEXT & ~filters.COMMAND, edit_profile_value),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=False,
)


async def edit_profile_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await require_channel_membership(update, context):
        return ConversationHandler.END

    user_info = await get_user_info(update.effective_user.id)
    if not user_info:
        await update.message.reply_text("ابتدا پروفایل خود را تکمیل کنید!")
        return ConversationHandler.END

    text = (
        f"اطلاعات فعلی شما:\n"
        f"نام کامل: {user_info['full_name']}\n"
        f"کد ملی: {user_info['national_id']}\n"
        f"شماره دانشجویی: {user_info['student_id']}\n"
        f"شماره تماس: {user_info['phone']}"
    )
    buttons = [
        [InlineKeyboardButton("ویرایش نام", callback_data="edit_full_name")],
        [InlineKeyboardButton("ویرایش کد ملی", callback_data="edit_national_id")],
        [InlineKeyboardButton("ویرایش شماره دانشجویی", callback_data="edit_student_id")],
        [InlineKeyboardButton("ویرایش شماره تماس", callback_data="edit_phone")],
        [InlineKeyboardButton("لغو", callback_data="cancel_edit")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    return EditProfileStates.SELECT_FIELD


async def edit_profile_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_edit":
        is_admin_user = await is_admin(update.effective_user.id)
        await query.edit_message_text("ویرایش لغو شد.", reply_markup=get_main_menu(is_admin_user))
        return ConversationHandler.END

    context.user_data["edit_field"] = query.data
    field_name = {
        "edit_full_name": "نام کامل",
        "edit_national_id": "کد ملی",
        "edit_student_id": "شماره دانشجویی",
        "edit_phone": "شماره تماس"
    }[query.data]

    if query.data == "edit_phone":
        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("ارسال شماره تماس", request_contact=True)]],
            one_time_keyboard=True
        )
        await query.edit_message_text(f"لطفاً {field_name} جدید را وارد کنید:", reply_markup=keyboard)
    else:
        await query.edit_message_text(f"لطفاً {field_name} جدید را وارد کنید:")

    return EditProfileStates.INPUT_VALUE


async def edit_profile_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    field = context.user_data["edit_field"]

    if field == "edit_full_name":
        text = update.message.text.strip()
        if not validate_full_name(text):
            await update.message.reply_text("نام کامل نامعتبر است. دوباره وارد کنید:")
            return EditProfileStates.INPUT_VALUE
        await update_user_field(user_id, "full_name", text)

    elif field == "edit_national_id":
        text = update.message.text.strip()
        if not validate_national_id(text):
            await update.message.reply_text("کد ملی نامعتبر است.")
            return EditProfileStates.INPUT_VALUE
        await update_user_field(user_id, "national_id", text)

    elif field == "edit_student_id":
        text = update.message.text.strip()
        if not text.isdigit():
            await update.message.reply_text("شماره دانشجویی باید عددی باشد.")
            return EditProfileStates.INPUT_VALUE
        await update_user_field(user_id, "student_id", text)

    elif field == "edit_phone":
        if update.message.contact:
            phone = update.message.contact.phone_number.replace("+98", "0") if update.message.contact.phone_number.startswith("+98") else update.message.contact.phone_number
        else:
            phone = update.message.text.strip()
        if not validate_phone(phone):
            await update.message.reply_text("شماره تماس نامعتبر است.")
            return EditProfileStates.INPUT_VALUE
        await update_user_field(user_id, "phone", phone)

    is_admin_user = await is_admin(user_id)
    await update.message.reply_text("پروفایل شما با موفقیت ویرایش شد!", reply_markup=get_main_menu(is_admin_user))
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_info = await get_user_info(update.effective_user.id)
    full_name = user_info["full_name"] if user_info else "کاربر"
    is_admin_user = await is_admin(update.effective_user.id)
    await update.message.reply_text(f"{full_name} عزیز، عملیات لغو شد.", reply_markup=get_main_menu(is_admin_user))
    return ConversationHandler.END
