# notifier.py — StorePing Telegram Message Sender
# All Telegram message formatting lives here.
# Bot and API both import from here — one format, always consistent.

import time
from telegram import Bot
from config import BOT_TOKEN

# One bot instance shared across the app
_bot: Bot = None

def get_bot() -> Bot:
    global _bot
    if _bot is None:
        _bot = Bot(token=BOT_TOKEN)
    return _bot


# ======================
# FORMATTERS
# ======================

def _fmt_currency(amount: float, symbol: str = "$") -> str:
    return f"{symbol}{amount:,.2f}"

def _fmt_time(ts: int) -> str:
    """Format unix timestamp to readable time."""
    return time.strftime("%I:%M %p", time.localtime(ts))

def _fmt_date(ts: int) -> str:
    return time.strftime("%b %d, %Y", time.localtime(ts))


# ======================
# NOTIFICATION SENDERS
# ======================

async def send_order_notification(client: dict, order: dict):
    """
    Fire when a new order comes in.
    This is the primary notification — keep it clean and readable.
    """
    if not client.get("telegram_chat_id"):
        return

    symbol = client.get("currency_symbol", "$")
    name = order.get("customer_name") or "Unknown customer"
    total = _fmt_currency(order["total"], symbol)
    order_num = order["order_number"]
    items = order.get("item_count", 1)
    item_label = f"{items} item" if items == 1 else f"{items} items"

    text = (
        f"🛒 *New Order*\n"
        f"\n"
        f"#{order_num}\n"
        f"{name}\n"
        f"{item_label} · *{total}*\n"
        f"\n"
        f"_{_fmt_time(int(time.time()))}_"
    )

    await get_bot().send_message(
        chat_id=client["telegram_chat_id"],
        text=text,
        parse_mode="Markdown",
    )


async def send_event_notification(client: dict, event_type: str, payload: dict):
    """
    Fire for non-order events.
    Each event type gets its own format.
    """
    if not client.get("telegram_chat_id"):
        return

    symbol = client.get("currency_symbol", "$")
    text = _format_event(event_type, payload, symbol)

    if not text:
        return  # Unknown event type — silently ignore

    await get_bot().send_message(
        chat_id=client["telegram_chat_id"],
        text=text,
        parse_mode="Markdown",
    )


def _format_event(event_type: str, payload: dict, symbol: str) -> str | None:
    """Return formatted message for a given event type. Returns None to skip."""

    if event_type == "low_stock":
        product = payload.get("product_name", "Unknown product")
        qty = payload.get("quantity", "?")
        return (
            f"⚠️ *Low Stock Alert*\n"
            f"\n"
            f"{product}\n"
            f"Only *{qty}* left"
        )

    elif event_type == "contact_form":
        from_name = payload.get("name", "Someone")
        subject = payload.get("subject", "no subject")
        return (
            f"📩 *Contact Form*\n"
            f"\n"
            f"From: {from_name}\n"
            f"Re: {subject}\n"
            f"\n"
            f"_Check your email for the full message_"
        )

    elif event_type == "maintenance_on":
        return "🔧 *Maintenance Mode ON*\nStore is now offline for visitors."

    elif event_type == "maintenance_off":
        return "✅ *Maintenance Mode OFF*\nStore is back online."

    elif event_type == "daily_summary":
        # payload contains pre-formatted stats
        orders = payload.get("order_count", 0)
        revenue = _fmt_currency(payload.get("revenue", 0), symbol)
        avg = _fmt_currency(payload.get("avg_order", 0), symbol)
        date = payload.get("date", "Today")
        return (
            f"📊 *Daily Summary — {date}*\n"
            f"\n"
            f"Orders: *{orders}*\n"
            f"Revenue: *{revenue}*\n"
            f"Avg order: *{avg}*"
        )

    return None


# ======================
# COMMAND REPLY FORMATTERS
# ======================
# These are used by bot.py to format responses to /commands.

def format_today(client: dict, stats: dict) -> str:
    symbol = client.get("currency_symbol", "$")
    return (
        f"📊 *Today*\n"
        f"\n"
        f"Orders: *{stats['order_count']}*\n"
        f"Revenue: *{_fmt_currency(stats['revenue'], symbol)}*\n"
        f"Avg order: *{_fmt_currency(stats['avg_order'], symbol)}*"
    )


def format_week(client: dict, stats: dict) -> str:
    symbol = client.get("currency_symbol", "$")
    return (
        f"📊 *Last 7 Days*\n"
        f"\n"
        f"Orders: *{stats['order_count']}*\n"
        f"Revenue: *{_fmt_currency(stats['revenue'], symbol)}*\n"
        f"Avg order: *{_fmt_currency(stats['avg_order'], symbol)}*"
    )


def format_month(client: dict, stats: dict) -> str:
    symbol = client.get("currency_symbol", "$")
    return (
        f"📊 *Last 30 Days*\n"
        f"\n"
        f"Orders: *{stats['order_count']}*\n"
        f"Revenue: *{_fmt_currency(stats['revenue'], symbol)}*\n"
        f"Avg order: *{_fmt_currency(stats['avg_order'], symbol)}*"
    )


def format_recent_orders(client: dict, orders: list) -> str:
    symbol = client.get("currency_symbol", "$")
    if not orders:
        return "No orders yet."

    lines = ["🛒 *Recent Orders*\n"]
    for o in orders:
        name = o.get("customer_name") or "Unknown"
        total = _fmt_currency(o["total"], symbol)
        num = o["order_number"]
        status_icon = {"pending": "⏳", "fulfilled": "✅", "cancelled": "❌"}.get(o["status"], "•")
        lines.append(f"{status_icon} #{num} · {name} · *{total}*")

    return "\n".join(lines)
