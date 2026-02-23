# config.py — Relay Configuration
# Single place for all settings.
# Set these as environment variables on your VPS, or create a .env file.
# NEVER commit this file with real values to git.
#
# Quick setup on your VPS:
#   export BOT_TOKEN="your_token_from_botfather"
#   export TELEGRAM_GROUP_ID="-5289768910"
#   export DB_PASS="your_postgres_password"
#   export API_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

import os

# ======================
# DATABASE
# ======================

DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = int(os.getenv("DB_PORT", "5432"))
DB_NAME     = os.getenv("DB_NAME", "relay")
DB_USER     = os.getenv("DB_USER", "relay_user")
DB_PASS     = os.getenv("DB_PASS", "changeme")

# ======================
# API SERVER
# ======================

API_HOST    = os.getenv("API_HOST", "0.0.0.0")
API_PORT    = int(os.getenv("API_PORT", "8000"))

# Client API secret — PHP/webhook sites send this in Authorization header.
# Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
API_SECRET  = os.getenv("API_SECRET", "change-this-before-deploying")

# ======================
# TELEGRAM
# ======================

# Get this from @BotFather — /newbot or /mybots
BOT_TOKEN           = os.getenv("BOT_TOKEN", "")

# Your Telegram group ID where Relay sends notifications
# Your group ID: -5289768910
TELEGRAM_GROUP_ID   = int(os.getenv("TELEGRAM_GROUP_ID", "-5289768910"))

# ======================
# DAILY SUMMARY
# ======================

SUMMARY_HOUR    = int(os.getenv("SUMMARY_HOUR", "21"))    # 9pm
SUMMARY_MINUTE  = int(os.getenv("SUMMARY_MINUTE", "0"))
TIMEZONE        = os.getenv("TIMEZONE", "Asia/Kolkata")
