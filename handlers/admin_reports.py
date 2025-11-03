# handlers/admin_reports.py
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, filters, CallbackQueryHandler
from .common import get_admin_row, get_main_menu
import aiosqlite
import re

# --- Reports Menu ---
async def reports_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS and not await get_admin_row(user_id):
        await update.message.reply_text("دسترسی ندارید!")
        return

    buttons = [
        [InlineKeyboardButton("آمار کلی", callback_data="report_general")],
        [InlineKeyboardButton("لیست ثبت‌نام‌ها", callback_data="report_registrations")],
        [InlineKeyboardButton("گزارش مالی", callback_data="report_financial")],
        [InlineKeyboardButton("نظرسنجی‌ها", callback_data="report_feedback")],
        [InlineKeyboardButton("بازگشت", callback_data="back_to_admin")]
    ]
    await update.message.reply_text("گزارش مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))

# --- General Report ---
async def general_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    async with aiosqlite.connect("chemeng_bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            total_users = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM events WHERE is_active = 1") as cursor:
            active_events = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM registrations") as cursor:
            total_regs = (await cursor.fetchone())[0]
        async with db.execute("SELECT SUM(cost) FROM events WHERE cost > 0") as cursor:
            total_revenue = (await cursor.fetchone())[0] or 0

    text = (
        f"آمار کلی ربات:\n\n"
        f"تعداد کاربران: {total_users}\n"
        f"رویدادهای فعال: {active_events}\n"
        f"کل ثبت‌نام‌ها: {total_regs}\n"
        f"درآمد پیش‌بینی شده: {total_revenue:,} تومان"
    )
    await query.message.reply_text(text)

# --- Registrations Report ---
async def registrations_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    async with aiosqlite.connect("chemeng_bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT e.title, e.type, COUNT(r.registration_id) as regs
            FROM events e
            LEFT JOIN registrations r ON e.event_id = r.event_id
            GROUP BY e.event_id
            ORDER BY regs DESC
        """) as cursor:
            events = await cursor.fetchall()

    if not events:
        await query.message.reply_text("هنوز ثبت‌نامی وجود ندارد.")
        return

    text = "لیست ثبت‌نام‌ها:\n\n"
    for e in events:
        text += f"• {e['title']} ({e['type']}): {e['regs']} نفر\n"

    await query.message.reply_text(text)

# --- Financial Report ---
async def financial_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    async with aiosqlite.connect("chemeng_bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT e.title, e.cost, COUNT(p.payment_id) as paid
            FROM events e
            LEFT JOIN payments p ON e.event_id = p.event_id
            WHERE e.cost > 0
            GROUP BY e.event_id
        """) as cursor:
            paid_events = await cursor.fetchall()
        async with db.execute("SELECT SUM(amount) FROM payments") as cursor:
            total_paid = (await cursor.fetchone())[0] or 0

    if not paid_events:
        await query.message.reply_text("هنوز پرداختی ثبت نشده است.")
        return

    text = f"گزارش مالی:\n\nکل درآمد تأیید شده: {total_paid:,} تومان\n\n"
    for e in paid_events:
        revenue = e["cost"] * e["paid"]
        text += f"• {e['title']}: {e['paid']} نفر × {e['cost']:,} = {revenue:,} تومان\n"

    await query.message.reply_text(text)

# --- Feedback Report ---
async def feedback_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    async with aiosqlite.connect("chemeng_bot.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT e.title, e.type, 
                   COUNT(f.feedback_id) as total,
                   AVG(f.rating) as avg_rating
            FROM events e
            LEFT JOIN feedbacks f ON e.event_id = f.event_id
            GROUP BY e.event_id
            HAVING total > 0
        """) as cursor:
            feedbacks = await cursor.fetchall()

    if not feedbacks:
        await query.message.reply_text("هنوز نظری ثبت نشده است.")
        return

    text = "گزارش نظرسنجی‌ها:\n\n"
    for f in feedbacks:
        avg = round(f["avg_rating"], 2)
        text += f"• {f['title']} ({f['type']}): میانگین {avg}/5 از {f['total']} نظر\n"

    await query.message.reply_text(text)

# --- Back to Admin Menu ---
async def back_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("به منوی ادمین بازگشتید.", reply_markup=get_admin_menu())
    await query.message.delete()

# --- Report Handler ---
async def report_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "report_general":
        await general_report(update, context)
    elif action == "report_registrations":
        await registrations_report(update, context)
    elif action == "report_financial":
        await financial_report(update, context)
    elif action == "report_feedback":
        await feedback_report(update, context)
    elif action == "back_to_admin":
        await back_to_admin(update, context)

    # Keep menu
    await query.message.reply_text(
        "گزارش دیگری می‌خواهید؟",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("بله", callback_data="report_menu")],
            [InlineKeyboardButton("خروج", callback_data="back_to_admin")]
        ])
    )
