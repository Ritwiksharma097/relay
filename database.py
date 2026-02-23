# database.py — Relay Storage Layer
# Single access point. Nothing else touches PostgreSQL directly.
# Multi-tenant: every table references client_id.

import time
import json
import psycopg2
import psycopg2.extras
from typing import Optional, Dict, List
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS


# ======================
# CONNECTION
# ======================

def get_connection():
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT,
        dbname=DB_NAME, user=DB_USER, password=DB_PASS,
    )
    conn.autocommit = False
    return conn


# ======================
# SCHEMA SETUP
# ======================

def init_db():
    """Create all tables. Safe to call on every startup."""
    conn = get_connection()
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id               SERIAL PRIMARY KEY,
            slug             TEXT NOT NULL UNIQUE,
            name             TEXT NOT NULL,
            api_secret       TEXT NOT NULL,
            telegram_chat_id BIGINT,
            currency_symbol  TEXT DEFAULT '$',
            timezone         TEXT DEFAULT 'Asia/Kolkata',
            active           BOOLEAN DEFAULT TRUE,
            created_at       BIGINT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id            SERIAL PRIMARY KEY,
            client_id     INTEGER NOT NULL REFERENCES clients(id),
            order_number  TEXT NOT NULL,
            customer_name TEXT,
            total         NUMERIC(10, 2) NOT NULL,
            item_count    INTEGER DEFAULT 1,
            status        TEXT DEFAULT 'pending',
            received_at   BIGINT NOT NULL,
            created_at    BIGINT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id          SERIAL PRIMARY KEY,
            client_id   INTEGER NOT NULL REFERENCES clients(id),
            event_type  TEXT NOT NULL,
            payload     JSONB,
            created_at  BIGINT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS telegram_chats (
            id         SERIAL PRIMARY KEY,
            client_id  INTEGER NOT NULL REFERENCES clients(id),
            chat_id    BIGINT NOT NULL,
            chat_type  TEXT DEFAULT 'private',
            label      TEXT,
            active     BOOLEAN DEFAULT TRUE,
            added_at   BIGINT NOT NULL,
            UNIQUE(client_id, chat_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            client_id   INTEGER NOT NULL REFERENCES clients(id),
            key         TEXT NOT NULL,
            value       TEXT NOT NULL,
            updated_at  BIGINT NOT NULL,
            PRIMARY KEY (client_id, key)
        )
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Relay database initialized")


# ======================
# CLIENT MANAGEMENT
# ======================

def get_client_by_slug(slug: str) -> Optional[Dict]:
    conn = get_connection()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM clients WHERE slug = %s AND active = TRUE", (slug,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return dict(row) if row else None


def get_client_by_id(client_id: int) -> Optional[Dict]:
    conn = get_connection()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM clients WHERE id = %s", (client_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return dict(row) if row else None


def get_client_by_chat_id(chat_id: int) -> Optional[Dict]:
    conn = get_connection()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT c.* FROM clients c
        JOIN telegram_chats tc ON tc.client_id = c.id
        WHERE tc.chat_id = %s AND tc.active = TRUE AND c.active = TRUE
        LIMIT 1
    """, (chat_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return dict(row) if row else None


def create_client(slug: str, name: str, api_secret: str,
                  timezone: str = "Asia/Kolkata", currency_symbol: str = "$") -> int:
    now  = int(time.time())
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO clients (slug, name, api_secret, timezone, currency_symbol, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (slug, name, api_secret, timezone, currency_symbol, now))
    client_id = cur.fetchone()[0]
    conn.commit()
    cur.close(); conn.close()
    return client_id


def set_client_chat(client_id: int, chat_id: int, chat_type: str = "private", label: str = None):
    now  = int(time.time())
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO telegram_chats (client_id, chat_id, chat_type, label, added_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (client_id, chat_id) DO UPDATE SET
            active = TRUE,
            label  = EXCLUDED.label
    """, (client_id, chat_id, chat_type, label, now))
    cur.execute("UPDATE clients SET telegram_chat_id = %s WHERE id = %s", (chat_id, client_id))
    conn.commit()
    cur.close(); conn.close()


def get_all_active_clients() -> List[Dict]:
    conn = get_connection()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM clients WHERE active = TRUE AND telegram_chat_id IS NOT NULL")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in rows]


# ======================
# SETTINGS
# ======================

def get_setting(client_id: int, key: str) -> Optional[str]:
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute(
        "SELECT value FROM settings WHERE client_id = %s AND key = %s",
        (client_id, key)
    )
    row = cur.fetchone()
    cur.close(); conn.close()
    return row[0] if row else None


def set_setting(client_id: int, key: str, value: str):
    now  = int(time.time())
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO settings (client_id, key, value, updated_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (client_id, key) DO UPDATE SET
            value      = EXCLUDED.value,
            updated_at = EXCLUDED.updated_at
    """, (client_id, key, value, now))
    conn.commit()
    cur.close(); conn.close()


# ======================
# ORDER TRACKING
# ======================

def record_order(client_id: int, order_number: str, customer_name: str,
                 total: float, item_count: int = 1, received_at: int = None) -> int:
    now  = int(time.time())
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO orders (client_id, order_number, customer_name, total, item_count, received_at, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (client_id, order_number, customer_name, total, item_count, received_at or now, now))
    order_id = cur.fetchone()[0]
    conn.commit()
    cur.close(); conn.close()
    return order_id


def get_today_stats(client_id: int) -> Dict:
    today_start = int(time.time()) // 86400 * 86400
    conn = get_connection()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            COUNT(*)                AS order_count,
            COALESCE(SUM(total), 0) AS revenue,
            COALESCE(AVG(total), 0) AS avg_order
        FROM orders
        WHERE client_id = %s AND received_at >= %s AND status != 'cancelled'
    """, (client_id, today_start))
    row = cur.fetchone()
    cur.close(); conn.close()
    return dict(row)


def get_week_stats(client_id: int) -> Dict:
    week_start = int(time.time()) - (7 * 86400)
    conn = get_connection()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            COUNT(*)                AS order_count,
            COALESCE(SUM(total), 0) AS revenue,
            COALESCE(AVG(total), 0) AS avg_order
        FROM orders
        WHERE client_id = %s AND received_at >= %s AND status != 'cancelled'
    """, (client_id, week_start))
    row = cur.fetchone()
    cur.close(); conn.close()
    return dict(row)


def get_month_stats(client_id: int) -> Dict:
    month_start = int(time.time()) - (30 * 86400)
    conn = get_connection()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            COUNT(*)                AS order_count,
            COALESCE(SUM(total), 0) AS revenue,
            COALESCE(AVG(total), 0) AS avg_order
        FROM orders
        WHERE client_id = %s AND received_at >= %s AND status != 'cancelled'
    """, (client_id, month_start))
    row = cur.fetchone()
    cur.close(); conn.close()
    return dict(row)


def get_recent_orders(client_id: int, limit: int = 5) -> List[Dict]:
    conn = get_connection()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT order_number, customer_name, total, item_count, status, received_at
        FROM orders
        WHERE client_id = %s
        ORDER BY received_at DESC
        LIMIT %s
    """, (client_id, limit))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in rows]


# ======================
# EVENT LOGGING
# ======================

def log_event(client_id: int, event_type: str, payload: dict = None):
    now  = int(time.time())
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO events (client_id, event_type, payload, created_at)
        VALUES (%s, %s, %s, %s)
    """, (client_id, event_type, json.dumps(payload or {}), now))
    conn.commit()
    cur.close(); conn.close()


# ======================
# INIT ON IMPORT
# ======================

init_db()
