"""Outbound webhooks: push platform events into the client's own systems.

Per-client config (editable in the dashboard, "webhooks" key in the client JSON):

  "webhooks": [
    {"url": "https://example.com/hooks/voice", "secret": "whsec_x",
     "events": ["call.ended", "handoff.requested"]}          # [] = all events
  ]

Deliveries are POSTs with an HMAC-SHA256 signature so receivers can verify us:

  X-Voice-Event:      call.ended
  X-Voice-Signature:  sha256=<hmac of the raw body with the endpoint secret>

Sent from a daemon thread — a slow or dead endpoint never blocks a live call.
"""

import hashlib
import hmac
import json
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from loguru import logger

EVENT_TYPES = [
    "call.started",
    "call.ended",
    "handoff.requested",
    "handoff.accepted",
    "handoff.resolved",
    "lead.captured",
    "appointment.booked",
    "task.queued",
    "payment_link.sent",
]


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(timespec="seconds")


def _deliver(url: str, secret: str, event_type: str, body: bytes, attempt: int = 1):
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "SorscoVoice-Webhooks/1.0",
            "X-Voice-Event": event_type,
            "X-Voice-Signature": signature,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            logger.info(f"Webhook {event_type} -> {url} HTTP {r.status}")
    except Exception as e:
        if attempt < 3:
            time.sleep(2 ** attempt)
            _deliver(url, secret, event_type, body, attempt + 1)
        else:
            logger.warning(f"Webhook {event_type} -> {url} failed after 3 tries: {e}")


def emit(event_type: str, client_cfg: dict, data: dict):
    """Fire event_type at every subscribed endpoint of this client. Non-blocking."""
    endpoints = client_cfg.get("webhooks") or []
    if not endpoints:
        return
    payload = {
        "event": event_type,
        "client_id": client_cfg.get("client_id", ""),
        "timestamp": _now_iso(),
        "data": data,
    }
    body = json.dumps(payload, ensure_ascii=False).encode()
    for ep in endpoints:
        url = (ep.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        wanted = ep.get("events") or []
        if wanted and event_type not in wanted:
            continue
        threading.Thread(
            target=_deliver,
            args=(url, ep.get("secret", ""), event_type, body),
            daemon=True,
        ).start()
