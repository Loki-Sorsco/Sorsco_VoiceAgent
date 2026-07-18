"""Human handoff: the AI agent hands a live call to a person, with context.

Flow:
  1. Caller asks for a human (or the agent decides it's stuck) -> the bot calls
     the transfer_to_human tool -> create_handoff() writes a record with the
     transcript-so-far, an instant AI summary, and the customer's details.
  2. Every dashboard user sees the handoff pop up in real time (the handoff is
     also emitted as a `handoff.requested` webhook so it can ring a Slack
     channel / CRM).
  3. Browser calls: staff open the live view, read the context, and either call
     the customer back or join at the desk. Telephony calls: accept can
     LIVE-TRANSFER the phone call — Twilio redirects the customer's leg to the
     staff phone (config: handoff.transfer_number on the client).
  4. accept -> resolve closes the loop; unanswered handoffs age to "missed".

Storage: data/platform/handoffs.json (same JSON-store convention as the rest).
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from loguru import logger

HANDOFFS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "platform" / "handoffs.json"
WAITING_TIMEOUT_S = 15 * 60


def _load() -> list:
    if HANDOFFS_FILE.exists():
        try:
            return json.loads(HANDOFFS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return []


def _save(handoffs: list):
    HANDOFFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    HANDOFFS_FILE.write_text(
        json.dumps(handoffs, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def create_handoff(
    client_cfg: dict,
    reason: str,
    transcript: list[dict],
    customer_name: str = "",
    customer_phone: str = "",
    call_sid: str | None = None,
) -> dict:
    """Open a handoff with full context. Returns the record for the bot/tool."""
    summary = _quick_summary(transcript, reason)
    record = {
        "handoff_id": uuid.uuid4().hex[:8],
        "client_id": client_cfg["client_id"],
        "business_name": client_cfg.get("business_name", ""),
        "reason": reason,
        "summary": summary,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "call_sid": call_sid,
        "transcript": [
            {"who": e.get("type"), "text": e.get("text", "")}
            for e in transcript
            if e.get("type") in ("user", "assistant")
        ][-40:],
        "status": "waiting",
        "accepted_by": None,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    handoffs = _load()
    handoffs.append(record)
    _save(handoffs)

    from src.platform.webhooks_out import emit

    emit("handoff.requested", client_cfg, {
        "handoff_id": record["handoff_id"],
        "reason": reason,
        "summary": summary,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
    })
    logger.info(f"Handoff {record['handoff_id']} opened: {reason}")
    return record


def _quick_summary(transcript: list[dict], reason: str) -> str:
    """Instant LLM summary so staff can pick up mid-conversation. Best-effort."""
    lines = [
        f"{'CALLER' if e.get('type') == 'user' else 'AGENT'}: {e.get('text', '')}"
        for e in transcript
        if e.get("type") in ("user", "assistant")
    ]
    if not lines:
        return reason
    try:
        from src.llm_factory import chat_complete

        reply = chat_complete(
            "Summarize this in-progress call in 2 short sentences for the human "
            "staff member about to take over: who is calling, what they want, and "
            "where the conversation stands. Plain English, no preamble.",
            [{"role": "user", "content": "\n".join(lines[-30:])}],
            max_tokens=120,
        )
        return reply.strip()[:400] or reason
    except Exception as e:
        logger.warning(f"Handoff summary failed: {e}")
        return reason


# ------------------------------------------------------------------ queries


def list_handoffs(client_id: str | None = None, limit: int = 50) -> list[dict]:
    _age_out()
    handoffs = _load()
    if client_id:
        handoffs = [h for h in handoffs if h["client_id"] == client_id]
    return handoffs[-limit:][::-1]


def get_handoff(handoff_id: str) -> dict | None:
    return next((h for h in _load() if h["handoff_id"] == handoff_id), None)


def waiting_count(client_id: str | None = None) -> int:
    return sum(1 for h in list_handoffs(client_id) if h["status"] == "waiting")


def _age_out():
    """Handoffs nobody answered within the window become 'missed'."""
    handoffs = _load()
    changed = False
    now = datetime.now()
    for h in handoffs:
        if h["status"] != "waiting":
            continue
        try:
            created = datetime.strptime(h["created"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if (now - created).total_seconds() > WAITING_TIMEOUT_S:
            h["status"] = "missed"
            changed = True
    if changed:
        _save(handoffs)


# ----------------------------------------------------------------- lifecycle


def update_handoff(handoff_id: str, **fields) -> dict | None:
    handoffs = _load()
    found = None
    for h in handoffs:
        if h["handoff_id"] == handoff_id:
            h.update(fields)
            h["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            found = h
    _save(handoffs)
    return found


async def accept_handoff(handoff_id: str, staff_name: str, client_cfg: dict) -> dict:
    """Staff takes the handoff. Live phone calls get transferred to the staff line."""
    record = get_handoff(handoff_id)
    if not record:
        raise ValueError("No such handoff")
    transferred = False
    transfer_number = (client_cfg.get("handoff") or {}).get("transfer_number", "")
    if record.get("call_sid") and transfer_number:
        try:
            await _twilio_transfer(record["call_sid"], transfer_number)
            transferred = True
        except Exception as e:
            logger.warning(f"Live transfer failed for {handoff_id}: {e}")
    record = update_handoff(
        handoff_id, status="accepted", accepted_by=staff_name, transferred=transferred
    )

    from src.platform.webhooks_out import emit

    emit("handoff.accepted", client_cfg, {
        "handoff_id": handoff_id, "accepted_by": staff_name, "transferred": transferred,
    })
    return record


def resolve_handoff(handoff_id: str, client_cfg: dict, note: str = "") -> dict | None:
    record = update_handoff(handoff_id, status="resolved", note=note)

    from src.platform.webhooks_out import emit

    emit("handoff.resolved", client_cfg, {"handoff_id": handoff_id, "note": note})
    return record


async def _twilio_transfer(call_sid: str, to_number: str):
    """Redirect the live Twilio call away from the bot to the staff phone."""
    import aiohttp

    sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    if not (sid and token):
        raise ValueError("Twilio not configured")
    twiml = f"<Response><Say>Connecting you now.</Say><Dial>{to_number}</Dial></Response>"
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls/{call_sid}.json"
    async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, token)) as session:
        async with session.post(url, data={"Twiml": twiml}) as r:
            if r.status >= 300:
                body = await r.json()
                raise ValueError(body.get("message", f"Twilio HTTP {r.status}"))
    logger.info(f"Call {call_sid} live-transferred to {to_number}")
