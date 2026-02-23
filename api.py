# api.py — Relay Event Receiver
# FastAPI server running on your VPS.
# Client PHP sites POST events here. Bot reads from the same DB.
#
# Endpoints:
#   POST /event/{client_slug}/order   — receive a new order from a client site
#   POST /event/{client_slug}/generic — receive any other event (low stock, contact, etc.)
#   GET  /maintenance/{client_slug}   — check maintenance status
#   GET  /health                      — uptime check

import hmac
import time
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Path
from pydantic import BaseModel
from typing import Optional

import database as db
from notifier import send_order_notification, send_event_notification


# ======================
# STARTUP
# ======================

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("✅ Relay API starting")
    yield
    print("Relay API shutting down")

app = FastAPI(title="Relay API", lifespan=lifespan)


# ======================
# REQUEST MODELS
# ======================

class OrderEvent(BaseModel):
    order_number:   str
    customer_name:  Optional[str] = "Unknown"
    total:          float
    item_count:     Optional[int] = 1
    received_at:    Optional[int] = None    # unix timestamp, defaults to now


class GenericEvent(BaseModel):
    event_type: str                         # "low_stock", "contact_form", "maintenance_on", etc.
    payload:    Optional[dict] = {}


# ======================
# AUTH
# ======================

def verify_secret(client: dict, authorization: str):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    incoming = authorization.removeprefix("Bearer ").strip()

    if not hmac.compare_digest(incoming, client["api_secret"]):
        raise HTTPException(status_code=401, detail="Invalid secret")


# ======================
# ENDPOINTS
# ======================

@app.get("/health")
async def health():
    return {"status": "ok", "service": "relay", "time": int(time.time())}


@app.post("/event/{client_slug}/order")
async def receive_order(
    client_slug:    str = Path(...),
    body:           OrderEvent = ...,
    authorization:  str = Header(default=""),
):
    client = db.get_client_by_slug(client_slug)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    verify_secret(client, authorization)

    db.record_order(
        client_id=client["id"],
        order_number=body.order_number,
        customer_name=body.customer_name,
        total=body.total,
        item_count=body.item_count,
        received_at=body.received_at,
    )

    asyncio.create_task(send_order_notification(client, body.dict()))

    return {"ok": True}


@app.post("/event/{client_slug}/generic")
async def receive_generic_event(
    client_slug:    str = Path(...),
    body:           GenericEvent = ...,
    authorization:  str = Header(default=""),
):
    client = db.get_client_by_slug(client_slug)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    verify_secret(client, authorization)

    db.log_event(client["id"], body.event_type, body.payload)

    asyncio.create_task(send_event_notification(client, body.event_type, body.payload))

    return {"ok": True}


@app.get("/maintenance/{client_slug}")
async def get_maintenance(
    client_slug:   str = Path(...),
    authorization: str = Header(default=""),
):
    client = db.get_client_by_slug(client_slug)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    verify_secret(client, authorization)

    status = db.get_setting(client["id"], "maintenance") or "off"
    return {"maintenance": status}
