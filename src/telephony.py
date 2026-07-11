"""Real outbound phone calls via Twilio (works with the free trial).

place_call() asks Twilio to dial the customer; when they answer, Twilio opens
a media stream to our /ws endpoint carrying the task_id, and the same pipeline
that runs browser calls runs the phone call.

Env (set in Dokploy / .env):
  TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN — from console.twilio.com (trial is fine)
  TWILIO_FROM_NUMBER — your Twilio number, e.g. +15005550006
  PUBLIC_HOST — this server's public hostname (no scheme), for the media stream

Trial notes: Twilio trials can only call numbers verified in the console
(Verified Caller IDs) and play a short trial notice before connecting.
"""

import os
from xml.sax.saxutils import quoteattr

from loguru import logger


def telephony_status() -> dict:
    sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_no = os.environ.get("TWILIO_FROM_NUMBER", "")
    host = os.environ.get("PUBLIC_HOST", "")
    missing = [
        name
        for name, val in [
            ("TWILIO_ACCOUNT_SID", sid),
            ("TWILIO_AUTH_TOKEN", token),
            ("TWILIO_FROM_NUMBER", from_no),
            ("PUBLIC_HOST", host),
        ]
        if not val
    ]
    return {
        "configured": not missing,
        "missing": missing,
        "from_number": from_no if from_no else None,
        "provider": "twilio",
    }


async def place_call(task: dict) -> dict:
    """Dial the task's customer. Returns {"call_sid": ...} or raises ValueError."""
    status = telephony_status()
    if not status["configured"]:
        raise ValueError(
            "Telephony not configured — missing: " + ", ".join(status["missing"])
        )
    phone = (task.get("customer_phone") or "").strip().replace(" ", "")
    if not phone.startswith("+"):
        raise ValueError(
            f"Customer phone '{phone or 'empty'}' must be in international format (+91...)"
        )

    import aiohttp

    sid = os.environ["TWILIO_ACCOUNT_SID"]
    token = os.environ["TWILIO_AUTH_TOKEN"]
    host = os.environ["PUBLIC_HOST"]
    twiml = (
        "<Response><Connect>"
        f'<Stream url="wss://{host}/ws">'
        f"<Parameter name=\"task_id\" value={quoteattr(task['task_id'])}/>"
        "</Stream></Connect></Response>"
    )
    data = {
        "To": phone,
        "From": os.environ["TWILIO_FROM_NUMBER"],
        "Twiml": twiml,
    }
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"
    async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, token)) as session:
        async with session.post(url, data=data) as r:
            body = await r.json()
            if r.status >= 300:
                msg = body.get("message", f"Twilio HTTP {r.status}")
                logger.warning(f"Twilio call failed for task {task['task_id']}: {msg}")
                # Trial accounts: most common failure is an unverified number.
                if "unverified" in msg.lower() or body.get("code") == 21219:
                    msg += " (Trial accounts can only call numbers verified in the Twilio console)"
                raise ValueError(msg)
            call_sid = body.get("sid")
            logger.info(f"Dialing {phone} for task {task['task_id']} (CallSid {call_sid})")
            return {"call_sid": call_sid}
