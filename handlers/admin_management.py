# admin_managment.py
from enum import Enum, auto
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from .common import require_admin, get_admin_menu
from .database import (
    get_all_events,
    get_event,
    get_registrations_for_event,
    get_user_info,
    add_admin,
    remove_admin,
    get_admin_info,
    register_user_to_event,
    get_active_events,
)
from config import OPERATOR_GROUP_ID


# ==============================
# حالت‌های اعلان عمومی
# ==============================

class AnnounceStates(Enum):
    INPUT_MESSAGE = auto()
    CONFIRM_SEND = auto()


# ==============================
# حالت‌های مدیریت ادمین
# ==============================

class ManageAdminsStates(Enum):
    SELECT_ACTION = auto()
    INPUT_USER_ID = auto()
    CONFIRM_REMOVE = auto()


# ==============================
# حالت‌های ثبت‌نام دستی
# ==============================

class ManualRegStates(Enum):
    SELECT_EVENT = auto()
    INPUT_NATIONAL_ID = auto()
    CONFIRM_USER = auto()


# ==============================
# ConversationHandler: اعلان عمومی
# ==============================

announce_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(اعلان عمومی)$"), announce_start)],
    states={
        AnnounceStates.INPUT_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, announce_input)],
        AnnounceStates.CONFIRM_SEND: [CallbackQueryHandler(announce_send)],
    },
    fallbacks=[MessageHandler(filters.Regex("^(لغو)$"), cancel_announce)],
    per_message=False,
)


async def announce_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await require_admin(update, context):
        return ConversationHandler.END

    await update.message.reply_text("متن اعلان عمومی را وارد کنید:")
    return AnnounceStates.INPUT_MESSAGE


async def announce_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["announce_text"] = update.message.text.strip()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("ارسال به همه", callback_data="announce_all")],
        [InlineKeyboardButton("ارسال به گروه اپراتور", callback_data="announce_ops")],
        [InlineKeyboardButton("لغو", callback_data="announce_cancel")]
    ])
    await update.message.reply_text(
        f"اعلان:\n\n{context.user_data['announce_text']}\n\nکجا ارسال شود؟",
        reply_markup=keyboard
    )
    return AnnounceStates.CONFIRM_SEND


async def announce_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "announce_cancel":
        await query.edit_message_text("اعلان لغو شد.", reply_markup=get_admin_menu())
        return ConversationHandler.END

    text = context.user_data["announce_text"]
    sent_count = 0

    if query.data == "announce_all":
        # ارسال به همه کاربران ثبت‌نام‌کرده
        from database import fetch_all
        users = await fetch_all("SELECT DISTINCT user_id FROM registrations")
        for user in users:
            try:
                await context.bot.send_message(user["user_id"], text)
                sent_count += 1
                await asyncio.sleep(0.05)
            except Exception:
                pass
        target = "همه کاربران"
    else:
        # ارسال به گروه اپراتورها
        await context.bot.send_message(OPERATOR_GROUP_ID, text)
        sent_count = 1
        target = "گروه اپراتورها"

    await query.edit_message_text(
        f"اعلان با موفقیت برای {sent_count} نفر در {target} ارسال شد!",
        reply_markup=get_admin_menu()
    )
    return ConversationHandler.END


# ==============================
# ConversationHandler: مدیریت ادمین
# ==============================

manage_admins_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(مدیریت ادمین‌ها)$"), manage_admins_start)],
    states={
        ManageAdminsStates.SELECT_ACTION: [CallbackQueryHandler(manage_admins_action)],
        ManageAdminsStates.INPUT_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, manage_admins_input_id)],
        ManageAdminsStates.CONFIRM_REMOVE: [CallbackQueryHandler(manage_admins_confirm_remove)],
    },
    fallbacks=[MessageHandler(filters.Regex("^(لغو)$"), cancel_manage_admins)],
    per_message=False,
)


async def manage_admins_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await require_admin(update, context):
        return ConversationHandler.END

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("اضافه کردن ادمین", callback_data="admin_add")],
        [InlineKeyboardButton("حذف ادمین", callback_data="admin_remove")],
        [InlineKeyboardButton("لغو", callback_data="admin_cancel")]
    ])
    await update.message.reply_text("عملیات مدیریت ادمین:", reply_markup=keyboard)
    return ManageAdminsStates.SELECT_ACTION


async def manage_admins_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "admin_cancel":
        await query.edit_message_text("عملیات لغو شد.", reply_markup=get_admin_menu())
        return ConversationHandler.END

    context.user_data["admin_action"] = query.data
    action_text = "اضافه" if query.data == "admin_add" else "حذف"
    await query.edit_message_text(f"آیدی عددی کاربر برای {action_text} کردن ادمین را وارد کنید:")
    return ManageAdminsStates.INPUT_USER_ID


async def manage_admins_input_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        user_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("آیدی باید عدد باشد. دوباره وارد کنید:")
        return ManageAdminsStates.INPUT_USER_ID

    context.user_data["target_admin_id"] = user_id

    if context.user_data["admin_action"] == "admin_add":
        if await get_admin_info(user_id):
            await update.message.reply_text("این کاربر قبلاً ادمین است!", reply_markup=get_admin_menu())
            return ConversationHandler.END
        await update.message.reply_text(f"آیا کاربر `{user_id}` ادمین شود؟", parse_mode="Markdown",
                                       reply_markup=InlineKeyboardMarkup([
                                           [InlineKeyboardButton("بله", callback_data="confirm_add_admin")],
                                           [InlineKeyboardButton("خیر", callback_data="cancel_admin")]
                                       ]))
    else:
        if not await get_admin_info(user_id):
            await update.message.reply_text("این کاربر ادمین نیست!", reply_markup=get_admin_menu())
            return ConversationHandler.END
        await update.message.reply_text(f"آیا کاربر `{user_id}` از ادمین‌ها حذف شود؟", parse_mode="Markdown",
                                       reply_markup=InlineKeyboardMarkup([
                                           [InlineKeyboardButton("بله", callback_data="confirm_remove_admin")],
                                           [InlineKeyboardButton("خیر", callback_data="cancel_admin")]
                                       ]))
    return ManageAdminsStates.CONFIRM_REMOVE


async def manage_admins_confirm_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_admin":
        await query.edit_message_text("عملیات لغو شد.", reply_markup=get_admin_menu())
        return ConversationHandler.END

    user_id = context.user_data["target_admin_id"]

    if query.data == "confirm_add_admin":
        await add_admin(user_id)
        action = "اضافه"
    else:
        await remove_admin(user_id)
        action = "حذف"

    await query.edit_message_text(f"کاربر `{user_id}` با موفقیت {action} شد!", parse_mode="Markdown",
                                 reply_markup=get_admin_menu())
    return ConversationHandler.END


# ==============================
# ConversationHandler: ثبت‌نام دستی
# ==============================

manual_reg_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(اضافه کردن دستی به ثبت‌نام)$"), manual_reg_start)],
    states={
        ManualRegStates.SELECT_EVENT: [CallbackQueryHandler(manual_reg_select_event)],
        ManualRegStates.INPUT_NATIONAL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_reg_input_nid)],
        ManualRegStates.CONFIRM_USER: [CallbackQueryHandler(manual_reg_confirm)],
    },
    fallbacks=[MessageHandler(filters.Regex("^(لغو)$"), cancel_manual_reg)],
    per_message=False,
)


async def manual_reg_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await require_admin(update, context):
        return ConversationHandler.END

    events = await get_active_events()
    if not events:
        await update.message.reply_text("رویداد فعالی وجود ندارد.", reply_markup=get_admin_menu())
        return ConversationHandler.END

    buttons = [
        [InlineKeyboardButton(f"{e['title']} ({e['type']})", callback_data=f"manreg_event_{e['event_id']}")]
        for e in events
    ]
    await update.message.reply_text("رویداد را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
    return ManualRegStates.SELECT_EVENT


async def manual_reg_select_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["manreg_event_id"] = int(query.data.split("_")[2])
    await query.edit_message_text("کد ملی کاربر را وارد کنید:")
    return ManualRegStates.INPUT_NATIONAL_ID


async def manual_reg_input_nid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from common import validate_national_id
    nid = update.message.text.strip()

    if not validate_national_id(nid):
        await update.message.reply_text("کد ملی نامعتبر است. دوباره وارد کنید:")
        return ManualRegStates.INPUT_NATIONAL_ID

    user = await get_user_info_by_national_id(nid)
    if not user:
        await update.message.reply_text("کاربری با این کد ملی یافت نشد!", reply_markup=get_admin_menu())
        return ConversationHandler.END

    context.user_data["manreg_user"] = user
    event = await get_event(context.user_data["manreg_event_id"])

    text = (
        f"کاربر: {user['full_name']}\n"
        f"کد ملی: {user['national_id']}\n"
        f"رویداد: {event['title']}\n\n"
        f"آیا ثبت‌نام دستی انجام شود؟"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("بله", callback_data="confirm_manreg")],
        [InlineKeyboardButton("خیر", callback_data="cancel_manreg")]
    ])
    await update.message.reply_text(text, reply_markup=keyboard)
    return ManualRegStates.CONFIRM_USER


async def manual_reg_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_manreg":
        await query.edit_message_text("ثبت‌نام دستی لغو شد.", reply_markup=get_admin_menu())
        return ConversationHandler.END

    user = context.user_data["manreg_user"]
    event_id = context.user_data["manreg_event_id"]

    success = await register_user_to_event(user["user_id"], event_id)
    if not success:
        await query.edit_message_text("کاربر قبلاً ثبت‌نام کرده است!", reply_markup=get_admin_menu())
        return ConversationHandler.END

    # ارسال به گروه
    event = await get_event(event_id)
    reg_count = len(await get_registrations_for_event(event_id))
    hashtag = f"#{event['type']} #{event['hashtag'].replace(' ', '_')} #دستی"

    text = (
        f"{hashtag}\n"
        f"ثبت‌نام دستی #{reg_count}:\n"
        f"نام: {user['full_name']}\n"
        f"کد ملی: {user['national_id']}\n"
        f"شماره دانشجویی: {user['student_id']}\n"
        f"شماره تماس: {user['phone']}"
    )

    try:
        await context.bot.send_message(OPERATOR_GROUP_ID, text)
    except Exception as e:
        print(f"خطا در ارسال به گروه: {e}")

    await query.edit_message_text("ثبت‌نام دستی با موفقیت انجام شد!", reply_markup=get_admin_menu())
    return ConversationHandler.END


# ==============================
# گزارش‌ها
# ==============================

report_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^(گزارش‌ها)$"), report_start)],
    states={},
    fallbacks=[],
)


async def report_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_admin(update, context):
        return

    events = await get_all_events()
    if not events:
        await update.message.reply_text("رویدادی وجود ندارد.", reply_markup=get_admin_menu())
        return

    report_text = "گزارش کلی رویدادها:\n\n"
    for e in events:
        regs = await get_registrations_for_event(e["event_id"])
        status = "غیرفعال" if not e["is_active"] else "فعال"
        cost_total = e["cost"] * len(regs) if e["cost"] > 0 else 0
        report_text += (
            f"**{e['title']}**\n"
            f"نوع: {e['type']} | وضعیت: {status}\n"
            f"تعداد ثبت‌نام: {len(regs)}\n"
            f"درآمد: {cost_total:,} تومان\n"
            f"هشتگ: #{e['hashtag']}\n\n"
        )

    await update.message.reply_text(report_text, parse_mode="Markdown", reply_markup=get_admin_menu())


# ==============================
# تابع کمکی: جستجوی کاربر با کد ملی
# ==============================

async def get_user_info_by_national_id(national_id: str):
    from database import fetch_one
    return await fetch_one("SELECT * FROM users WHERE national_id = ?", (national_id,))


# ==============================
# توابع لغو
# ==============================

async def cancel_announce(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("اعلان لغو شد.", reply_markup=get_admin_menu())
    return ConversationHandler.END

async def cancel_manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("مدیریت ادمین لغو شد.", reply_markup=get_admin_menu())
    return ConversationHandler.END

async def cancel_manual_reg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("ثبت‌نام دستی لغو شد.", reply_markup=get_admin_menu())
    return ConversationHandler.END
