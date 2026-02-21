#!/usr/bin/env python3
# setup_client.py — Register a new client in StorePing
#
# Run this once per client to create their record.
# Then give them their slug + secret to put in storeping.php.
#
# Usage:
#   python setup_client.py

import secrets
import database as db

def main():
    print("\n=== StorePing — New Client Setup ===\n")

    name     = input("Store name (e.g. Turtle Island Jewelry): ").strip()
    slug     = input("Store slug (e.g. turtle-island, no spaces): ").strip().lower()
    timezone = input("Timezone (e.g. America/Toronto) [America/Toronto]: ").strip() or "America/Toronto"
    currency = input("Currency symbol (e.g. $, ₹, €) [$]: ").strip() or "$"

    # Generate a strong secret
    api_secret = secrets.token_hex(32)

    client_id = db.create_client(
        slug=slug,
        name=name,
        api_secret=api_secret,
        timezone=timezone,
        currency_symbol=currency,
    )

    print(f"\n✅ Client created! ID: {client_id}")
    print(f"\n--- Put these in storeping.php on the client site ---")
    print(f"STOREPING_SLUG   = '{slug}'")
    print(f"STOREPING_SECRET = '{api_secret}'")
    print(f"\n--- Send this to the store owner (for Telegram /start) ---")
    print(f"/start {slug} {api_secret}")
    print(f"\n--- Done. They just send that command in Telegram and they're connected. ---\n")


if __name__ == "__main__":
    main()
