# api.py — Relay Event Receiver
# FastAPI server running on your VPS.
#
# Endpoints:
#   POST /event/{client_slug}/order   — receive a new order
#   POST /event/{client_slug}/generic — receive any other event
#   GET  /maintenance/{client_slug}   — check maintenance status
#   GET  /health                      — uptime check
#
#   POST /chat/{client_slug}/start    — widget opens, creates a session
#   POST /chat/{client_slug}/message  — visitor sends a message
#   GET  /chat/{session_id}/poll      — widget polls for owner replies
#   POST /chat/{session_id}/close     — widget closes the session

import hmac
import time
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

import database as db
from notifier import send_order_notification, send_event_notification, send_chat_notification, send_chat_followup_notification


# ======================
# STARTUP
# ======================

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("✅ Relay API starting")
    yield
    print("Relay API shutting down")

app = FastAPI(title="Relay API", lifespan=lifespan)

# Allow your website to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://interactxp.in", "https://interactxp.pages.dev"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


# ======================
# REQUEST MODELS
# ======================

class OrderEvent(BaseModel):
    order_number:   str
    customer_name:  Optional[str] = "Unknown"
    total:          float
    item_count:     Optional[int] = 1
    received_at:    Optional[int] = None

class GenericEvent(BaseModel):
    event_type: str
    payload:    Optional[dict] = {}

class ChatStart(BaseModel):
    visitor_name: Optional[str] = "Visitor"
    page:         Optional[str] = "/"
    first_message: str           # first message sent with the session

class ChatMessage(BaseModel):
    session_id: str
    message:    str


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
# EXISTING ENDPOINTS
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


# ======================
# CHAT ENDPOINTS
# ======================

@app.post("/chat/{client_slug}/start")
async def chat_start(
    client_slug:   str = Path(...),
    body:          ChatStart = ...,
    authorization: str = Header(default=""),
):
    """Widget calls this when user sends their first message. Returns session_id."""
    client = db.get_client_by_slug(client_slug)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    verify_secret(client, authorization)

    session_id = db.create_chat_session(
        client_id=client["id"],
        visitor_id=body.visitor_name,
        page=body.page,
    )

    # Save the first message
    db.add_chat_message(session_id, "visitor", body.first_message)

    # Notify owner on Telegram
    asyncio.create_task(send_chat_notification(client, session_id, body.visitor_name, body.page, body.first_message))

    return {"ok": True, "session_id": session_id}


@app.post("/chat/{client_slug}/message")
async def chat_message(
    client_slug:   str = Path(...),
    body:          ChatMessage = ...,
    authorization: str = Header(default=""),
):
    """Widget sends follow-up messages."""
    client = db.get_client_by_slug(client_slug)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    verify_secret(client, authorization)

    session = db.get_chat_session(body.session_id)
    if not session or session["client_id"] != client["id"]:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] == "closed":
        raise HTTPException(status_code=400, detail="Session is closed")

    db.add_chat_message(body.session_id, "visitor", body.message)

    # Also notify owner for follow-up messages
    asyncio.create_task(send_chat_followup(client, session, body.message))

    return {"ok": True}


@app.get("/chat/{session_id}/poll")
async def chat_poll(
    session_id: str = Path(...),
    since:      int = 0,
):
    """Widget polls this every 3 seconds to get owner replies. No auth — session_id is the secret."""
    session = db.get_chat_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = db.get_chat_messages(session_id, since=since)
    return {
        "status": session["status"],
        "messages": messages,
    }


@app.post("/chat/{session_id}/close")
async def chat_close(session_id: str = Path(...)):
    """Widget calls this when user closes the chat."""
    session = db.get_chat_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.close_chat_session(session_id)
    return {"ok": True}


# ======================
# HELPER (follow-up notify)
# ======================

async def send_chat_followup(client: dict, session: dict, message: str):
    visitor = session.get("visitor_id") or "Visitor"
    sid     = session["session_id"]
    await send_chat_followup_notification(client, sid, visitor, message)
