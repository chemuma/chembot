# handlers/user_events.py
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, filters, CallbackQueryHandler, MessageHandler
from .common import (
    check_channel_membership, get_user_row, get_admin_row,
    get_main_menu, show_main_menu, cancel
)
from config import OPERATOR_GROUP_ID, CARD_NUMBER
from datetime import datetime
import aiosqlite
import asyncio

# --- Show Events ---
async def show_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_channel_membership(update, context):
        await update.message.reply_text(
            f"لطفاً ابتدا کانال رسمی را دنبال کنید: {CHANNEL_ID}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("عضو شدم", callback_data="check_membership")
            ]])
        )
        return

    async with aiosqlite.connect("chemeng_bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT event_id, title, type FROM events WHERE is_active = 1") as cursor:
            events = await cursor.fetchall()

    if not events:
        await update.message.reply_text("در حال حاضر دوره یا بازدید فعالی وجود ندارد.")
        return

    buttons = [[InlineKeyboardButton(f"{e['title']} ({e['type']})", callback_data=f"event_{e['event_id']}")] for e in events]
    await update.message.reply_text("رویدادهای فعال:", reply_markup=InlineKeyboardMarkup(buttons))

# --- Event Details ---
async def event_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split("_")[1])

    async with aiosqlite.connect("chemeng_bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)) as cursor:
            event = await cursor.fetchone()

    if not event:
        await query.message.reply_text("رویداد یافت نشد!")
        return
    if not event["is_active"]:
        await query.message.reply_text(f"رویداد غیرفعال شده است. دلیل: {event['deactivation_reason']}")
        return

    capacity_text = "نامحدود" if event["type"] == "دوره" else f"{event['capacity'] - event['current_capacity']}/{event['capacity']}"
    cost_text = "رایگان" if event["cost"] == 0 else f"{event['cost']:,} تومان"

    text = (
        f"عنوان: {event['title']}\n"
        f"نوع: {event['type']}\n"
        f"تاریخ: {event['date']}\n"
        f"محل: {event['location']}\n"
        f"هزینه: {cost_text}\n"
        f"ظرفیت باقی‌مانده: {capacity_text}\n"
        f"توضیحات: {event['description']}"
    )
    buttons = [
        [InlineKeyboardButton("ثبت‌نام", callback_data=f"register_{event_id}")],
        [InlineKeyboardButton("بازگشت", callback_data="back_to_events")]
    ]
    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    await query.message.delete()

# --- Register Event ---
async def register_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not await check_channel_membership(update, context):
        await query.message.reply_text(
            f"لطفاً ابتدا کانال رسمی را دنبال کنید: {CHANNEL_ID}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("عضو شدم", callback_data="check_membership")
            ]])
        )
        return

    event_id = int(query.data.split("_")[1])
    user_id = update.effective_user.id

    async with aiosqlite.connect("chemeng_bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)) as cursor:
            event = await cursor.fetchone()
        async with db.execute("SELECT 1 FROM registrations WHERE user_id = ? AND event_id = ?", (user_id, event_id)) as cursor:
            already_reg = await cursor.fetchone()

        if already_reg:
            await query.message.reply_text("شما قبلاً ثبت‌نام کرده‌اید!")
            return
        if not event["is_active"]:
            await query.message.reply_text(f"رویداد غیرفعال شده است. دلیل: {event['deactivation_reason']}")
            return
        if event["type"] != "دوره" and event["current_capacity"] >= event["capacity"]:
            await query.message.reply_text("ظرفیت تکمیل شده است. برای لیست ذخیره با پشتیبانی تماس بگیرید.")
            return

    if event["cost"] == 0:
        # Free event
        await _register_free_event(user_id, event, context)
        await query.message.reply_text("ثبت‌نام شما با موفقیت انجام شد!")
    else:
        # Paid event
        context.user_data["pending_event_id"] = event_id
        await query.message.reply_text(
            f"برای ثبت‌نام در {event['title']}، مبلغ {event['cost']:,} تومان به کارت زیر واریز کنید:\n"
            f"`{CARD_NUMBER}`\n\n"
            "سپس تصویر رسید را ارسال کنید.",
            parse_mode="Markdown"
        )

async def _register_free_event(user_id: int, event: aiosqlite.Row, context: ContextTypes.DEFAULT_TYPE):
    async with aiosqlite.connect("chemeng_bot.db") as db:
        await db.execute(
            "INSERT INTO registrations (user_id, event_id, registered_at) VALUES (?, ?, ?)",
            (user_id, event["event_id"], datetime.now().isoformat())
        )
        await db.execute(
            "UPDATE events SET current_capacity = current_capacity + 1 WHERE event_id = ?",
            (event["event_id"],)
        )
        async with db.execute("SELECT full_name, national_id, student_id, phone FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
        async with db.execute("SELECT COUNT(*) FROM registrations WHERE event_id = ?", (event["event_id"],)) as cursor:
            reg_count = (await cursor.fetchone())[0]
        await db.commit()

    hashtag = f"#{event['type']} #{event['hashtag'].replace(' ', '_')}"
    text = (
        f"{hashtag}\n"
        f"{reg_count}:\n"
        f"نام: {user['full_name']}\n"
        f"کد ملی: {user['national_id']}\n"
        f"شماره دانشجویی: {user['student_id']}\n"
        f"شماره تماس: {user['phone']}"
    )
    message = await context.bot.send_message(OPERATOR_GROUP_ID, text)
    async with aiosqlite.connect("chemeng_bot.db") as db:
        await db.execute(
            "INSERT INTO operator_messages (message_id, chat_id, user_id, event_id, message_type, sent_at) VALUES (?, ?, ?, ?, ?, ?)",
            (message.message_id, OPERATOR_GROUP_ID, user_id, event["event_id"], "registration", datetime.now().isoformat())
        )
        await db.commit()

    if event["type"] != "دوره" and event["current_capacity"] + 1 >= event["capacity"]:
        await _deactivate_event(event["event_id"], "تکمیل ظرفیت", context)

# --- Handle Payment Receipt ---
async def handle_payment_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if "pending_event_id" not in context.user_data:
        await update.message.reply_text("لطفاً ابتدا یک رویداد انتخاب کنید.")
        return

    event_id = context.user_data["pending_event_id"]
    user_id = update.effective_user.id

    async with aiosqlite.connect("chemeng_bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)) as cursor:
            event = await cursor.fetchone()
        async with db.execute("SELECT full_name, national_id, student_id, phone FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()

    text = (
        f"#{event['type']} #{event['hashtag'].replace(' ', '_')}\n"
        f"نام: {user['full_name']}\n"
        f"کد ملی: {user['national_id']}\n"
        f"شماره دانشجویی: {user['student_id']}\n"
        f"شماره تماس: {user['phone']}\n"
        f"مبلغ: {event['cost']:,} تومان"
    )
    buttons = [
        [InlineKeyboardButton("تأیید", callback_data=f"confirm_payment_{user_id}_{event_id}")],
        [
            InlineKeyboardButton("ناخوانا", callback_data=f"unclear_payment_{user_id}_{event_id}"),
            InlineKeyboardButton("ابطال", callback_data=f"cancel_payment_{user_id}_{event_id}")
        ]
    ]
    message = await context.bot.send_photo(
        OPERATOR_GROUP_ID,
        update.message.photo[-1].file_id,
        caption=text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    async with aiosqlite.connect("chemeng_bot.db") as db:
        await db.execute(
            "INSERT INTO operator_messages (message_id, chat_id, user_id, event_id, message_type, sent_at) VALUES (?, ?, ?, ?, ?, ?)",
            (message.message_id, OPERATOR_GROUP_ID, user_id, event_id, "payment", datetime.now().isoformat())
        )
        await db.commit()

    await update.message.reply_text("رسید شما ارسال شد و در انتظار تأیید است.")

# --- Payment Actions ---
async def payment_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS and not await get_admin_row(user_id):
        await query.answer("فقط ادمین‌ها مجازند!", show_alert=True)
        return

    parts = query.data.split("_")
    action = parts[0]

    if action == "done":
        await query.message.delete()
        return

    if len(parts) >= 5 and parts[1] == "confirm":
        sub_action = parts[2]
        target_user_id = int(parts[3])
        event_id = int(parts[4])

        async with aiosqlite.connect("chemeng_bot.db") as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)) as cursor:
                event = await cursor.fetchone()
            async with db.execute("SELECT full_name, national_id, student_id, phone FROM users WHERE user_id = ?", (target_user_id,)) as cursor:
                user = await cursor.fetchone()

        if sub_action == "confirm_payment":
            await _confirm_payment(target_user_id, event, context)
            await context.bot.send_message(target_user_id, "پرداخت تأیید شد و ثبت‌نام شما تکمیل شد!")
        elif sub_action == "unclear_payment":
            context.user_data["pending_event_id"] = event_id
            await context.bot.send_message(target_user_id, "رسید ناخوانا است. لطفاً دوباره ارسال کنید.")
        elif sub_action == "cancel_payment":
            if "pending_event_id" in context.user_data:
                del context.user_data["pending_event_id"]
            await context.bot.send_message(target_user_id, "پرداخت تأیید نشد. دوباره تلاش کنید.")
        await query.message.delete()

    elif len(parts) == 3:
        action = parts[0]
        target_user_id = int(parts[1])
        event_id = int(parts[2])
        label = {"confirm_payment": "تأیید", "unclear_payment": "ناخوانا", "cancel_payment": "ابطال"}[action]
        buttons = [
            [InlineKeyboardButton(label, callback_data=f"confirm_{action}_{target_user_id}_{event_id}")],
            [InlineKeyboardButton("بازگشت", callback_data="done")]
        ]
        await query.message.edit_reply_markup(InlineKeyboardMarkup(buttons))

async def _confirm_payment(user_id: int, event: aiosqlite.Row, context: ContextTypes.DEFAULT_TYPE):
    async with aiosqlite.connect("chemeng_bot.db") as db:
        await db.execute(
            "INSERT INTO registrations (user_id, event_id, registered_at) VALUES (?, ?, ?)",
            (user_id, event["event_id"], datetime.now().isoformat())
        )
        await db.execute(
            "INSERT INTO payments (user_id, event_id, amount, confirmed_at) VALUES (?, ?, ?, ?)",
            (user_id, event["event_id"], event["cost"], datetime.now().isoformat())
        )
        await db.execute(
            "UPDATE events SET current_capacity = current_capacity + 1 WHERE event_id = ?",
            (event["event_id"],)
        )
        async with db.execute("SELECT COUNT(*) FROM registrations WHERE event_id = ?", (event["event_id"],)) as cursor:
            reg_count = (await cursor.fetchone())[0]
        await db.commit()

    hashtag = f"#{event['type']} #{event['hashtag'].replace(' ', '_')}"
    text = f"{hashtag}, {reg_count}:\nنام: {user['full_name']}\nکد ملی: {user['national_id']}\nشماره دانشجویی: {user['student_id']}\nشماره تماس: {user['phone']}"
    message = await context.bot.send_message(OPERATOR_GROUP_ID, text)
    async with aiosqlite.connect("chemeng_bot.db") as db:
        await db.execute(
            "INSERT INTO operator_messages (message_id, chat_id, user_id, event_id, message_type, sent_at) VALUES (?, ?, ?, ?, ?, ?)",
            (message.message_id, OPERATOR_GROUP_ID, user_id, event["event_id"], "registration", datetime.now().isoformat())
        )
        await db.commit()

    if event["type"] != "دوره" and event["current_capacity"] + 1 >= event["capacity"]:
        await _deactivate_event(event["event_id"], "تکمیل ظرفیت", context)

async def _deactivate_event(event_id: int, reason: str, context: ContextTypes.DEFAULT_TYPE):
    async with aiosqlite.connect("chemeng_bot.db") as db:
        await db.execute(
            "UPDATE events SET is_active = 0, deactivation_reason = ? WHERE event_id = ?",
            (reason, event_id)
        )
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)) as cursor:
            event = await cursor.fetchone()
        async with db.execute("SELECT user_id FROM registrations WHERE event_id = ?", (event_id,)) as cursor:
            regs = await cursor.fetchall()
        await db.commit()

    users = []
    for reg in regs:
        async with aiosqlite.connect("chemeng_bot.db") as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT full_name, phone FROM users WHERE user_id = ?", (reg["user_id"],)) as cursor:
                u = await cursor.fetchone()
                users.append(f"- {u['full_name']} ({u['phone']})")

    text = (
        f"#{event['type']} #{event['hashtag'].replace(' ', '_')}\n"
        f"#نهایی\n"
        f"تعداد: {len(users)}\n"
        f"{' '.join(users)}"
    )
    await context.bot.send_message(OPERATOR_GROUP_ID, text)
