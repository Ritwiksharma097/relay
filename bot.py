# bot.py — StorePing Telegram Bot
# Handles all commands from store owners.
#
# Commands:
#   /start              — link this chat to a store
#   /today              — today's stats
#   /week               — last 7 days
#   /month              — last 30 days
#   /orders             — recent 5 orders
#   /maintenance on|off — toggle maintenance mode
#   /help               — command list

import asyncio
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

import database as db
from notifier import (
    format_today,
    format_week,
    format_month,
    format_recent_orders,
    send_event_notification,
)
from config import BOT_TOKEN, SUMMARY_HOUR, SUMMARY_MINUTE

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("storeping.bot")


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
# COMMAND HANDLERS
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
                "Welcome to StorePing!\n\n"
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
        f"✅ Linked! This chat will now receive notifications for *{client['name']}*\n\n"
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

    # No args — show current status
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
        await update.message.reply_text(
            "Usage: `/maintenance on` or `/maintenance off`",
            parse_mode="Markdown",
        )
        return

    db.set_setting(client["id"], "maintenance", action)

    if action == "on":
        await update.message.reply_text(
            "🔧 *Maintenance mode ON*\n"
            "Store is now showing maintenance page to visitors.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "✅ *Maintenance mode OFF*\n"
            "Store is back online.",
            parse_mode="Markdown",
        )
    log.info(f"Maintenance {action} for {client['name']}")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client     = await get_client_for_chat(update)
    store_name = client["name"] if client else "your store"
    await update.message.reply_text(
        f"*StorePing — {store_name}*\n"
        f"\n"
        f"/today — today's orders and revenue\n"
        f"/week — last 7 days\n"
        f"/month — last 30 days\n"
        f"/orders — 5 most recent orders\n"
        f"/maintenance — check or toggle maintenance mode\n"
        f"/help — this message\n"
        f"\n"
        f"_You get automatic notifications when orders come in._",
        parse_mode="Markdown",
    )


# ======================
# DAILY SUMMARY (runs via JobQueue — correct async pattern)
# ======================

async def daily_summary_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Called every 60 seconds by JobQueue.
    Only fires at SUMMARY_HOUR:SUMMARY_MINUTE — ignores all other ticks.
    Uses bot_data to track which clients already got today's summary.
    """
    now       = datetime.now()
    today_key = str(now.date())

    # Reset tracker on new day
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
    app.add_handler(CommandHandler("help",        cmd_help))

    # JobQueue handles the async scheduling correctly
    app.job_queue.run_repeating(daily_summary_job, interval=60, first=10)

    log.info("✅ StorePing bot starting")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
