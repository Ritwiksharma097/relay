# config.py — StorePing Configuration
# Single place for all settings.
# Copy config.example.py → config.py and fill in your values.
# Never commit config.py to git.

import os
from pathlib import Path

# ======================
# DATABASE
# ======================

DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = int(os.getenv("DB_PORT", "5432"))
DB_NAME     = os.getenv("DB_NAME", "storeping")
DB_USER     = os.getenv("DB_USER", "storeping_user")
DB_PASS     = os.getenv("DB_PASS", "changeme")

# ======================
# API SERVER
# ======================

API_HOST    = os.getenv("API_HOST", "0.0.0.0")
API_PORT    = int(os.getenv("API_PORT", "8000"))

# Shared secret between PHP sites and this API.
# PHP site sends this in Authorization header.
# Generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
API_SECRET  = os.getenv("API_SECRET", "change-this-before-deploying")

# ======================
# TELEGRAM
# ======================

BOT_TOKEN   = os.getenv("BOT_TOKEN", "")   # From @BotFather

# ======================
# DAILY SUMMARY
# ======================

SUMMARY_HOUR    = int(os.getenv("SUMMARY_HOUR", "21"))   # 9pm
SUMMARY_MINUTE  = int(os.getenv("SUMMARY_MINUTE", "0"))
TIMEZONE        = os.getenv("TIMEZONE", "America/Toronto")
