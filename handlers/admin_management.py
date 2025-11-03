# handlers/admin_management.py
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, filters, CallbackQueryHandler, MessageHandler
from .common import get_admin_row, get_main_menu, cancel, show_main_menu
from config import ADMIN_IDS
from datetime import datetime
import aiosqlite
from enum import IntEnum

class AdminState(IntEnum):
    ADD_ADMIN = 0
    REMOVE_ADMIN = 1
    CONFIRM_ADD = 2
    CONFIRM_REMOVE = 3

# --- Add Admin ---
async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("فقط ادمین اصلی می‌تواند این کار را انجام دهد!")
        return ConversationHandler.END

    await update.message.reply_text("آیدی عددی کاربر را وارد کنید:")
    return AdminState.ADD_ADMIN

async def add_admin_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        target_id = int(update.message.text)
    except ValueError:
        await update.message.reply_text("آیدی باید عدد باشد.")
        return AdminState.ADD_ADMIN

    if target_id in ADMIN_IDS:
        await update.message.reply_text("این کاربر ادمین اصلی است و نیازی به اضافه کردن نیست.")
        return ConversationHandler.END

    admin_row = await get_admin_row(target_id)
    if admin_row:
        await update.message.reply_text("این کاربر قبلاً ادمین است.")
        return ConversationHandler.END

    context.user_data["new_admin_id"] = target_id
    await update.message.reply_text(
        f"آیا کاربر با آیدی `{target_id}` را به عنوان ادمین اضافه کنیم؟",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("بله", callback_data="confirm_add_admin"),
            InlineKeyboardButton("خیر", callback_data="cancel_add_admin")
        ]])
    )
    return AdminState.CONFIRM_ADD

async def confirm_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_add_admin":
        await query.message.reply_text("لغو شد.", reply_markup=get_admin_menu())
        await query.message.delete()
        return ConversationHandler.END

    target_id = context.user_data["new_admin_id"]
    async with aiosqlite.connect("chemeng_bot.db") as db:
        await db.execute(
            "INSERT INTO admins (user_id, added_at) VALUES (?, ?)",
            (target_id, datetime.now().isoformat())
        )
        await db.commit()

    await query.message.reply_text("ادمین جدید با موفقیت اضافه شد!", reply_markup=get_admin_menu())
    await query.message.delete()
    return ConversationHandler.END

# --- Remove Admin ---
async def remove_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("فقط ادمین اصلی می‌تواند این کار را انجام دهد!")
        return ConversationHandler.END

    async with aiosqlite.connect("chemeng_bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id FROM admins") as cursor:
            admins = await cursor.fetchall()

    if not admins:
        await update.message.reply_text("ادمین فعالی وجود ندارد.")
        return ConversationHandler.END

    buttons = [[InlineKeyboardButton(f"آیدی: {a['user_id']}", callback_data=f"remove_admin_{a['user_id']}")] for a in admins]
    await update.message.reply_text("ادمین برای حذف انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
    return AdminState.REMOVE_ADMIN

async def remove_admin_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    target_id = int(query.data.split("_")[2])

    context.user_data["remove_admin_id"] = target_id
    await query.message.reply_text(
        f"آیا ادمین با آیدی `{target_id}` را حذف کنیم؟",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("بله", callback_data="confirm_remove_admin"),
            InlineKeyboardButton("خیر", callback_data="cancel_remove_admin")
        ]])
    )
    await query.message.delete()
    return AdminState.CONFIRM_REMOVE

async def confirm_remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_remove_admin":
        await query.message.reply_text("لغو شد.", reply_markup=get_admin_menu())
        await query.message.delete()
        return ConversationHandler.END

    target_id = context.user_data["remove_admin_id"]
    async with aiosqlite.connect("chemeng_bot.db") as db:
        await db.execute("DELETE FROM admins WHERE user_id = ?", (target_id,))
        await db.commit()

    await query.message.reply_text("ادمین با موفقیت حذف شد!", reply_markup=get_admin_menu())
    await query.message.delete()
    return ConversationHandler.END

# --- Toggle Event Active ---
async def toggle_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS and not await get_admin_row(user_id):
        await update.message.reply_text("دسترسی ندارید!")
        return ConversationHandler.END

    async with aiosqlite.connect("chemeng_bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT event_id, title, type, is_active FROM events") as cursor:
            events = await cursor.fetchall()

    if not events:
        await update.message.reply_text("رویدادی وجود ندارد!")
        return ConversationHandler.END

    buttons = []
    for e in events:
        status = "فعال" if e["is_active"] else "غیرفعال"
        buttons.append([InlineKeyboardButton(f"{e['title']} ({e['type']}) - {status}", callback_data=f"toggle_{e['event_id']}")])
    await update.message.reply_text("رویداد را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))
    return AdminState.TOGGLE_SELECT

async def toggle_event_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split("_")[1])
    context.user_data["toggle_event_id"] = event_id

    async with aiosqlite.connect("chemeng_bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT is_active FROM events WHERE event_id = ?", (event_id,)) as cursor:
            event = await cursor.fetchone()

    action = "غیرفعال" if event["is_active"] else "فعال"
    await query.message.reply_text(f"آیا رویداد را {action} کنیم؟ در صورت غیرفعال‌سازی، دلیل را وارد کنید:")
    await query.message.delete()
    return AdminState.TOGGLE_REASON

async def toggle_event_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reason = update.message.text.strip()
    event_id = context.user_data["toggle_event_id"]

    async with aiosqlite.connect("chemeng_bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT is_active FROM events WHERE event_id = ?", (event_id,)) as cursor:
            event = await cursor.fetchone()
        new_status = 0 if event["is_active"] else 1
        await db.execute(
            "UPDATE events SET is_active = ?, deactivation_reason = ? WHERE event_id = ?",
            (new_status, reason if new_status == 0 else None, event_id)
        )
        await db.commit()

    status_text = "غیرفعال" if new_status == 0 else "فعال"
    await update.message.reply_text(f"رویداد با موفقیت {status_text} شد!", reply_markup=get_admin_menu())
    return ConversationHandler.END

# Conversation Handler
admin_management_conv = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex("^(مدیریت ادمین‌ها)$"), lambda u, c: add_admin_start(u, c) if u.effective_user.id in ADMIN_IDS else remove_admin_start(u, c)),
        MessageHandler(filters.Regex("^(غیرفعال/فعال کردن رویداد)$"), toggle_event_start)
    ],
    states={
        AdminState.ADD_ADMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_id)],
        AdminState.CONFIRM_ADD: [CallbackQueryHandler(confirm_add_admin)],
        AdminState.REMOVE_ADMIN: [CallbackQueryHandler(remove_admin_select)],
        AdminState.CONFIRM_REMOVE: [CallbackQueryHandler(confirm_remove_admin)],
        AdminState.TOGGLE_SELECT: [CallbackQueryHandler(toggle_event_select)],
        AdminState.TOGGLE_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, toggle_event_reason)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=False
)
