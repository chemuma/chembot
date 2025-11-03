# handlers/user_events.py
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db
from config import CHANNEL_ID, CARD_NUMBER, OPERATOR_GROUP_ID
from handlers.common import check_channel_membership, is_user_admin

logger = logging.getLogger(__name__)

async def deactivate_event(event_id: int, reason: str, context: ContextTypes.DEFAULT_TYPE):
    try:
        async with db.get_db_connection() as conn:
            await conn.execute(
                "UPDATE events SET is_active = 0, deactivation_reason = ? WHERE event_id = ?",
                (reason, event_id)
            )
            event = await db.get_event_details(event_id)
            registrations = await db.get_event_participants(event_id)
            await conn.commit()

            users = []
            for reg in registrations:
                user = await db.get_user_info(reg['user_id'])
                if user:
                    users.append(f"- {user['full_name']} ({user['phone']})")

            text = (
                f"#{event['type']} #{event['hashtag'].replace(' ', '_')}\n"
                f"#نهایی\n"
                f"تعداد: {len(users)}\n"
                f"{' '.join(users)}"
            )
            message = await context.bot.send_message(OPERATOR_GROUP_ID, text)
            
            await conn.execute(
                "INSERT INTO operator_messages (message_id, chat_id, user_id, event_id, message_type, sent_at) VALUES (?, ?, ?, ?, ?, ?)",
                (message.message_id, OPERATOR_GROUP_ID, 0, event_id, "final_list", datetime.now().isoformat())
            )
            await conn.commit()
            logger.info(f"Event {event_id} deactivated. Reason: {reason}")
            
    except Exception as e:
        logger.error(f"Error deactivating event {event_id}: {e}")

async def show_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message or (update.callback_query.message if update.callback_query else None)
    if not message:
        return

    if not await check_channel_membership(update, context):
        await message.reply_text(
            f"لطفاً ابتدا کانال رسمی را دنبال کنید: {CHANNEL_ID}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("عضو شدم", callback_data="check_membership")
            ]])
        )
        return
        
    events = await db.get_all_events(active_only=True)
            
    if not events:
        await message.reply_text("در حال حاضر دوره یا بازدید فعالی وجود ندارد.")
        return
        
    buttons = [[InlineKeyboardButton(f"{e['title']} ({e['type']})", callback_data=f"event_{e['event_id']}")] for e in events]
    
    if update.callback_query and update.callback_query.data == "back_to_events":
        await update.callback_query.message.edit_text(
            "رویدادهای فعال:", reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        await message.reply_text("رویدادهای فعال:", reply_markup=InlineKeyboardMarkup(buttons))

async def event_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split("_")[1])
    
    event = await db.get_event_details(event_id)
    if not event:
        await query.message.edit_text("رویداد یافت نشد!")
        return
        
    if not event['is_active']:
        await query.message.edit_text(f"رویداد غیرفعال شده است. دلیل: {event['deactivation_reason']}")
        return
        
    capacity_text = "نامحدود" if event['type'] == "دوره" else f"{event['capacity'] - event['current_capacity']}/{event['capacity']}"
    cost_text = "رایگان" if event['cost'] == 0 else f"{event['cost']:,} تومان"
    
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
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def register_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.split("_")[1])
    user_id = update.effective_user.id

    event = await db.get_event_details(event_id)
    if not event or not event['is_active']:
        await query.message.edit_text("رویداد در دسترس نیست.")
        return

    # چک ثبت‌نام قبلی
    async with db.get_db_connection() as conn:
        cursor = await conn.execute(
            "SELECT 1 FROM registrations WHERE user_id = ? AND event_id = ?",
            (user_id, event_id)
        )
        if await cursor.fetchone():
            await query.message.edit_text("شما قبلاً در این رویداد ثبت‌نام کرده‌اید.")
            return

    if event['cost'] == 0:
        # ثبت‌نام رایگان
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
        await query.message.edit_text("ثبت‌نام شما با موفقیت انجام شد!")
        if event['type'] != "دوره" and event['current_capacity'] + 1 >= event['capacity']:
            await deactivate_event(event_id, "تکمیل ظرفیت", context)
    else:
        # نیاز به پرداخت
        text = (
            f"برای ثبت‌نام در '{event['title']}'، مبلغ {event['cost']:,} تومان را به کارت {CARD_NUMBER} واریز کنید.\n"
            "سپس رسید را آپلود کنید."
        )
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت", callback_data="back_to_events")]]))

async def handle_payment_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    photo = update.message.photo[-1]
    file_id = photo.file_id

    # پیدا کردن رویداد پرداختی اخیر
    async with db.get_db_connection() as conn:
        cursor = await conn.execute(
            """
            SELECT e.event_id, e.title, e.cost 
            FROM events e
            JOIN registrations r ON e.event_id = r.event_id
            WHERE r.user_id = ? AND e.cost > 0
            ORDER BY r.registered_at DESC LIMIT 1
            """, (user_id,)
        )
        event = await cursor.fetchone()

    if not event:
        await update.message.reply_text("رویدادی برای پرداخت یافت نشد.")
        return

    caption = (
        f"رسید برای {event['title']}\n"
        f"مبلغ: {event['cost']:,} تومان\n"
        f"کاربر: {update.effective_user.full_name} (@{update.effective_user.username or 'none'})"
    )
    buttons = [
        [InlineKeyboardButton("تأیید", callback_data=f"confirm_payment_{user_id}_{event['event_id']}")],
        [InlineKeyboardButton("ناخوانا", callback_data=f"unclear_payment_{user_id}_{event['event_id']}")],
        [InlineKeyboardButton("ابطال", callback_data=f"cancel_payment_{user_id}_{event['event_id']}")]
    ]
    message = await context.bot.send_photo(
        OPERATOR_GROUP_ID, file_id, caption=caption, reply_markup=InlineKeyboardMarkup(buttons)
    )

    # ثبت پیام
    async with db.get_db_connection() as conn:
        await conn.execute(
            "INSERT INTO operator_messages (message_id, chat_id, user_id, event_id, message_type, sent_at) VALUES (?, ?, ?, ?, ?, ?)",
            (message.message_id, OPERATOR_GROUP_ID, user_id, event['event_id'], "payment_receipt", datetime.now().isoformat())
        )
        await conn.commit()

    await update.message.reply_text("رسید ارسال شد. منتظر تأیید باشید.")

async def payment_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    callback_parts = callback_data.split("_")
    action = callback_parts[0]
    
    if not await is_user_admin(update.effective_user.id):
        await query.answer("فقط ادمین‌ها می‌تونن این کار رو انجام بدن.", show_alert=True)
        return
    
    try:
        if action == "confirm":
            sub_action = callback_parts[1]
            user_id = int(callback_parts[2])
            event_id = int(callback_parts[3])
            
            event = await db.get_event_details(event_id)
            
            if sub_action == "confirm_payment":
                async with db.get_db_connection() as conn:
                    await conn.execute(
                        "INSERT INTO payments (user_id, event_id, amount, confirmed_at) VALUES (?, ?, ?, ?)",
                        (user_id, event_id, event['cost'], datetime.now().isoformat())
                    )
                    await conn.execute(
                        "UPDATE events SET current_capacity = current_capacity + 1 WHERE event_id = ?",
                        (event_id,)
                    )
                    await conn.commit()
                
                # ثبت پیام در گروه اپراتورها
                message_log = await context.bot.send_message(
                    OPERATOR_GROUP_ID,
                    f"پرداخت کاربر {user_id} برای رویداد {event['title']} تأیید شد."
                )
                await conn.execute(
                    "INSERT INTO operator_messages (message_id, chat_id, user_id, event_id, message_type, sent_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (message_log.message_id, OPERATOR_GROUP_ID, user_id, event_id, "registration", datetime.now().isoformat())
                )
                await conn.commit()

                await context.bot.send_message(user_id, f"پرداخت شما برای {event['title']} تأیید شد!")
                
                if event['type'] != "دوره" and event['current_capacity'] + 1 >= event['capacity']:
                    await deactivate_event(event_id, "تکمیل ظرفیت", context)
                
                await query.message.edit_caption(caption=f"{query.message.caption}\n\n✅ تأیید توسط {update.effective_user.full_name}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("حذف", callback_data="done")]]))
            
            elif sub_action == "unclear_payment":
                await context.bot.send_message(user_id, f"رسید برای {event['title']} ناخوانا بود. دوباره ارسال کنید.")
                await query.message.edit_caption(caption=f"{query.message.caption}\n\n📸 ناخوانا توسط {update.effective_user.full_name}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("حذف", callback_data="done")]]))
            
            elif sub_action == "cancel_payment":
                await context.bot.send_message(user_id, f"پرداخت برای {event['title']} تأیید نشد. دوباره ثبت‌نام کنید.")
                await query.message.edit_caption(caption=f"{query.message.caption}\n\n🚫 ابطال توسط {update.effective_user.full_name}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("حذف", callback_data="done")]]))
        
        elif action in ["confirm_payment", "unclear_payment", "cancel_payment"]:
            user_id = int(callback_parts[1])
            event_id = int(callback_parts[2])
            action_label = {"confirm_payment": "تأیید", "unclear_payment": "ناخوانا", "cancel_payment": "ابطال"}[action]
            
            caption = query.message.caption
            if "تأیید نهایی" in caption or "ابطال" in caption:
                await query.answer("این رسید پردازش شده.", show_alert=True)
                return

            buttons = [
                [InlineKeyboardButton(f"تأیید نهایی {action_label}", callback_data=f"confirm_{action}_{user_id}_{event_id}")],
                [InlineKeyboardButton("بازگشت", callback_data="done")]
            ]
            await query.message.edit_reply_markup(InlineKeyboardMarkup(buttons))
    
    except Exception as e:
        logger.error(f"Error in payment_action: {e}")
        await query.message.reply_text("خطایی رخ داد.")
