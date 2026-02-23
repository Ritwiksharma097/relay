# bot.py — Relay Telegram Bot
#
# Commands:
#   /start              — link this chat to a store
#   /today              — today's stats
#   /week               — last 7 days
#   /month              — last 30 days
#   /orders             — recent 5 orders
#   /maintenance on|off — toggle maintenance mode
#   /reply <id> <msg>   — reply to a website chat session
#   /close <id>         — close a chat session
#   /chats              — list open chat sessions
#   /help               — command list

import asyncio
import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

import database as db
from notifier import (
    format_today,
    format_week,
    format_month,
    format_recent_orders,
    send_event_notification,
    send_chat_followup_notification,
)
from config import BOT_TOKEN, SUMMARY_HOUR, SUMMARY_MINUTE, TELEGRAM_GROUP_ID

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("relay.bot")


# ======================
# HELPERS
# ======================

async def get_client_for_chat(update: Update) -> dict | None:
    chat_id = update.effective_chat.id
    client  = db.get_client_by_chat_id(chat_id)
    if not client:
        await update.message.reply_text(
            "This chat isn't linked to any store yet.\n"
            "Use /start <store-slug> <api-secret> to link it."
        )
        return None
    return client


# ======================
# EXISTING COMMANDS
# ======================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        client = db.get_client_by_chat_id(update.effective_chat.id)
        if client:
            await update.message.reply_text(
                f"✅ This chat is linked to *{client['name']}*\n"
                f"Type /help to see available commands.",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                "Welcome to Relay!\n\n"
                "To link this chat to your store, run:\n"
                "`/start your-store-slug your-api-secret`",
                parse_mode="Markdown",
            )
        return

    if len(args) < 2:
        await update.message.reply_text(
            "Usage: `/start your-store-slug your-api-secret`",
            parse_mode="Markdown",
        )
        return

    slug   = args[0].lower().strip()
    secret = args[1].strip()

    client = db.get_client_by_slug(slug)
    if not client:
        await update.message.reply_text(f"No store found with slug `{slug}`.", parse_mode="Markdown")
        return

    import hmac
    if not hmac.compare_digest(secret, client["api_secret"]):
        await update.message.reply_text("Wrong secret. Check your credentials.")
        return

    chat = update.effective_chat
    db.set_client_chat(
        client_id = client["id"],
        chat_id   = chat.id,
        chat_type = chat.type,
        label     = chat.title or chat.username or "owner chat",
    )
    await update.message.reply_text(
        f"✅ Linked! This chat will now receive Relay notifications for *{client['name']}*\n\n"
        f"Type /help to see what you can do.",
        parse_mode="Markdown",
    )
    log.info(f"Chat {chat.id} linked to client {client['name']} ({client['id']})")


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client = await get_client_for_chat(update)
    if not client: return
    stats = db.get_today_stats(client["id"])
    await update.message.reply_text(format_today(client, stats), parse_mode="Markdown")


async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client = await get_client_for_chat(update)
    if not client: return
    stats = db.get_week_stats(client["id"])
    await update.message.reply_text(format_week(client, stats), parse_mode="Markdown")


async def cmd_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client = await get_client_for_chat(update)
    if not client: return
    stats = db.get_month_stats(client["id"])
    await update.message.reply_text(format_month(client, stats), parse_mode="Markdown")


async def cmd_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client = await get_client_for_chat(update)
    if not client: return
    orders = db.get_recent_orders(client["id"], limit=5)
    await update.message.reply_text(format_recent_orders(client, orders), parse_mode="Markdown")


async def cmd_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client = await get_client_for_chat(update)
    if not client: return
    args = context.args
    if not args:
        current = db.get_setting(client["id"], "maintenance") or "off"
        icon    = "🔧" if current == "on" else "✅"
        label   = "ON — store is offline" if current == "on" else "OFF — store is live"
        await update.message.reply_text(
            f"{icon} *Maintenance is {label}*\n\n"
            f"To change: `/maintenance on` or `/maintenance off`",
            parse_mode="Markdown",
        )
        return
    action = args[0].lower().strip()
    if action not in ("on", "off"):
        await update.message.reply_text("Usage: `/maintenance on` or `/maintenance off`", parse_mode="Markdown")
        return
    db.set_setting(client["id"], "maintenance", action)
    if action == "on":
        await update.message.reply_text("🔧 *Maintenance mode ON*\nStore is now showing maintenance page.", parse_mode="Markdown")
    else:
        await update.message.reply_text("✅ *Maintenance mode OFF*\nStore is back online.", parse_mode="Markdown")
    log.info(f"Maintenance {action} for {client['name']}")


# ======================
# CHAT COMMANDS
# ======================

async def cmd_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/reply <session_id> <message...>"""
    client = await get_client_for_chat(update)
    if not client: return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: `/reply <session_id> your message here`",
            parse_mode="Markdown",
        )
        return

    session_id = args[0].upper()
    message    = " ".join(args[1:])

    session = db.get_chat_session(session_id)
    if not session:
        await update.message.reply_text(f"Session `{session_id}` not found.", parse_mode="Markdown")
        return
    if session["client_id"] != client["id"]:
        await update.message.reply_text("That session doesn't belong to your store.")
        return
    if session["status"] == "closed":
        await update.message.reply_text(f"Session `{session_id}` is already closed.", parse_mode="Markdown")
        return

    db.add_chat_message(session_id, "owner", message)

    visitor = session.get("visitor_id") or "Visitor"
    await update.message.reply_text(
        f"✅ Replied to *{visitor}* (`{session_id}`)",
        parse_mode="Markdown",
    )
    log.info(f"Owner replied to session {session_id}")


async def cmd_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/close <session_id>"""
    client = await get_client_for_chat(update)
    if not client: return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: `/close <session_id>`", parse_mode="Markdown")
        return

    session_id = args[0].upper()
    session    = db.get_chat_session(session_id)
    if not session:
        await update.message.reply_text(f"Session `{session_id}` not found.", parse_mode="Markdown")
        return
    if session["client_id"] != client["id"]:
        await update.message.reply_text("That session doesn't belong to your store.")
        return

    db.close_chat_session(session_id)
    visitor = session.get("visitor_id") or "Visitor"
    await update.message.reply_text(
        f"🔒 Session `{session_id}` with *{visitor}* closed.",
        parse_mode="Markdown",
    )
    log.info(f"Session {session_id} closed by owner")


async def cmd_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/chats — list open chat sessions"""
    client = await get_client_for_chat(update)
    if not client: return

    sessions = db.get_open_sessions_for_client(client["id"])
    if not sessions:
        await update.message.reply_text("No open chat sessions right now.")
        return

    lines = ["💬 *Open Chat Sessions*\n"]
    for s in sessions:
        visitor = s.get("visitor_id") or "Visitor"
        page    = s.get("page") or "/"
        lines.append(f"• `{s['session_id']}` — {visitor} on `{page}`")

    lines.append("\n_Reply with: `/reply <id> message`_")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ======================
# INLINE BUTTON HANDLERS
# ======================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles taps on the inline Reply / Close buttons.
    - "reply:SESSION_ID:VISITOR_NAME" → asks owner to type their reply
    - "close:SESSION_ID"              → closes the session immediately
    """
    query  = update.callback_query
    await query.answer()

    data = query.data or ""

    if data.startswith("close:"):
        session_id = data.split(":")[1]
        session    = db.get_chat_session(session_id)
        if not session:
            await query.message.reply_text("Session not found.")
            return
        db.close_chat_session(session_id)
        visitor = session.get("visitor_id") or "Visitor"
        # Update the original message to show it's closed
        try:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(f"🔒 Chat with *{visitor}* (`{session_id}`) closed.", parse_mode="Markdown")
        except Exception:
            pass
        log.info(f"Session {session_id} closed via button")

    elif data.startswith("reply:"):
        parts      = data.split(":", 2)
        session_id = parts[1]
        visitor    = parts[2] if len(parts) > 2 else "Visitor"

        session = db.get_chat_session(session_id)
        if not session:
            await query.message.reply_text("Session not found.")
            return
        if session["status"] == "closed":
            await query.message.reply_text(f"Session `{session_id}` is already closed.", parse_mode="Markdown")
            return

        # Store pending reply state in context
        context.user_data["awaiting_reply"] = {
            "session_id": session_id,
            "visitor":    visitor,
        }

        await query.message.reply_text(
            f"✏️ Replying to *{visitor}* (`{session_id}`)\n\nType your message now:",
            parse_mode="Markdown",
        )


async def handle_reply_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Catches the owner's plain text message when they're in 'awaiting_reply' state.
    Saves it to the DB so the widget polls it up.
    """
    pending = context.user_data.get("awaiting_reply")
    if not pending:
        return  # not in reply mode — ignore

    session_id = pending["session_id"]
    visitor    = pending["visitor"]
    message    = update.message.text.strip()

    if not message:
        return

    session = db.get_chat_session(session_id)
    if not session or session["status"] == "closed":
        await update.message.reply_text(f"Session `{session_id}` is closed.", parse_mode="Markdown")
        context.user_data.pop("awaiting_reply", None)
        return

    db.add_chat_message(session_id, "owner", message)
    context.user_data.pop("awaiting_reply", None)

    # Confirm + show Reply button again for convenience
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💬 Reply again", callback_data=f"reply:{session_id}:{visitor}"),
            InlineKeyboardButton("🔒 Close", callback_data=f"close:{session_id}"),
        ]
    ])
    await update.message.reply_text(
        f"✅ Sent to *{visitor}*: _{message}_",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    log.info(f"Owner replied to session {session_id}: {message[:40]}")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client     = await get_client_for_chat(update)
    store_name = client["name"] if client else "your store"
    await update.message.reply_text(
        f"*Relay — {store_name}*\n"
        f"\n"
        f"*Orders & Stats*\n"
        f"/today — today's orders and revenue\n"
        f"/week — last 7 days\n"
        f"/month — last 30 days\n"
        f"/orders — 5 most recent orders\n"
        f"\n"
        f"*Store Control*\n"
        f"/maintenance — check or toggle maintenance mode\n"
        f"\n"
        f"*Website Chat*\n"
        f"/chats — list open chat sessions\n"
        f"/reply <id> <msg> — reply to a visitor\n"
        f"/close <id> — close a chat session\n"
        f"\n"
        f"/help — this message\n"
        f"\n"
        f"_You get automatic notifications when orders and chats come in._",
        parse_mode="Markdown",
    )


# ======================
# DAILY SUMMARY
# ======================

async def daily_summary_job(context: ContextTypes.DEFAULT_TYPE):
    now       = datetime.now()
    today_key = str(now.date())

    if context.bot_data.get("summary_last_day") != today_key:
        context.bot_data["summary_sent"]     = set()
        context.bot_data["summary_last_day"] = today_key

    if now.hour != SUMMARY_HOUR or now.minute != SUMMARY_MINUTE:
        return

    sent_today: set = context.bot_data["summary_sent"]
    clients         = db.get_all_active_clients()

    for client in clients:
        key = f"{client['id']}-{today_key}"
        if key in sent_today:
            continue
        stats = db.get_today_stats(client["id"])
        try:
            await send_event_notification(client, "daily_summary", {
                "order_count": stats["order_count"],
                "revenue":     float(stats["revenue"]),
                "avg_order":   float(stats["avg_order"]),
                "date":        today_key,
            })
            sent_today.add(key)
            log.info(f"Daily summary sent to {client['name']}")
        except Exception as e:
            log.error(f"Daily summary failed for {client['name']}: {e}")


# ======================
# MAIN
# ======================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("today",       cmd_today))
    app.add_handler(CommandHandler("week",        cmd_week))
    app.add_handler(CommandHandler("month",       cmd_month))
    app.add_handler(CommandHandler("orders",      cmd_orders))
    app.add_handler(CommandHandler("maintenance", cmd_maintenance))
    app.add_handler(CommandHandler("reply",       cmd_reply))
    app.add_handler(CommandHandler("close",       cmd_close))
    app.add_handler(CommandHandler("chats",       cmd_chats))
    app.add_handler(CommandHandler("help",        cmd_help))

    # Inline button handlers
    app.add_handler(CallbackQueryHandler(handle_callback))
    # Catches owner's reply text when in awaiting_reply state
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reply_message))

    app.job_queue.run_repeating(daily_summary_job, interval=60, first=10)

    log.info(f"✅ Relay bot starting — group ID: {TELEGRAM_GROUP_ID}")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
