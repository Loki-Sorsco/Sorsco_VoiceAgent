"""Pre-built connectors: how a client's agent talks to their existing stack.

Config lives per client under "connectors" (edited in the dashboard):

  "connectors": {
    "stripe":      {"api_key": "sk_live_..."},
    "razorpay":    {"key_id": "rzp_...", "key_secret": "..."},
    "twilio_sms":  {"from_number": "+1..."},            # creds fall back to env
    "calendly":    {"token": "...", "event_type": "https://api.calendly.com/event_types/..."},
    "google_sheets": {"webhook_url": "https://script.google.com/macros/s/..."},
    "generic_rest": {"base_url": "https://api.clinic.example", "headers": {"X-Api-Key": "..."},
                     "lookup_path": "/patients?phone={query}", "save_path": "/appointments"}
  }

(Shopify predates this registry and keeps its own top-level "shopify" key; the
registry reads it from there so nothing breaks.)

Each connector = a spec (fields the dashboard renders + a test call) and action
functions the agent tools layer invokes mid-call. generic_rest is the escape
hatch for anything without a named connector: hospital EMRs, hotel PMSs, CRMs.
"""

import json

import aiohttp
from loguru import logger

TIMEOUT = aiohttp.ClientTimeout(total=15)


def connector_cfg(client_cfg: dict, connector_id: str) -> dict:
    if connector_id == "shopify":
        return client_cfg.get("shopify") or {}
    return (client_cfg.get("connectors") or {}).get(connector_id) or {}


def is_configured(client_cfg: dict, connector_id: str) -> bool:
    cfg = connector_cfg(client_cfg, connector_id)
    spec = CONNECTORS.get(connector_id, {})
    required = [f["key"] for f in spec.get("fields", []) if f.get("required")]
    return bool(cfg) and all(cfg.get(k) for k in required)


# ------------------------------------------------------------------- stripe


async def stripe_payment_link(client_cfg: dict, amount: float, currency: str,
                              description: str) -> dict:
    """Create a Stripe Payment Link for an ad-hoc amount (price made inline)."""
    key = connector_cfg(client_cfg, "stripe").get("api_key", "")
    if not key:
        return {"error": "Stripe is not connected"}
    auth = aiohttp.BasicAuth(key, "")
    async with aiohttp.ClientSession(auth=auth, timeout=TIMEOUT) as session:
        async with session.post(
            "https://api.stripe.com/v1/prices",
            data={
                "unit_amount": int(round(amount * 100)),
                "currency": currency.lower(),
                "product_data[name]": description[:120] or "Payment",
            },
        ) as r:
            price = await r.json()
            if r.status >= 300:
                return {"error": price.get("error", {}).get("message", f"Stripe HTTP {r.status}")}
        async with session.post(
            "https://api.stripe.com/v1/payment_links",
            data={"line_items[0][price]": price["id"], "line_items[0][quantity]": 1},
        ) as r:
            link = await r.json()
            if r.status >= 300:
                return {"error": link.get("error", {}).get("message", f"Stripe HTTP {r.status}")}
    return {"url": link["url"], "amount": amount, "currency": currency.upper()}


async def _stripe_test(cfg: dict) -> tuple[bool, str]:
    auth = aiohttp.BasicAuth(cfg.get("api_key", ""), "")
    async with aiohttp.ClientSession(auth=auth, timeout=TIMEOUT) as session:
        async with session.get("https://api.stripe.com/v1/balance") as r:
            if r.status == 200:
                return True, "Stripe key works"
            return False, f"Stripe answered HTTP {r.status} — check the API key"


# ----------------------------------------------------------------- razorpay


async def razorpay_payment_link(client_cfg: dict, amount: float, currency: str,
                                description: str, customer_name: str = "",
                                customer_phone: str = "") -> dict:
    """Razorpay Payment Link — the India-first payment option (UPI, cards)."""
    cfg = connector_cfg(client_cfg, "razorpay")
    if not (cfg.get("key_id") and cfg.get("key_secret")):
        return {"error": "Razorpay is not connected"}
    body = {
        "amount": int(round(amount * 100)),
        "currency": (currency or "INR").upper(),
        "description": description[:255] or "Payment",
    }
    if customer_phone:
        body["customer"] = {"name": customer_name or "Customer", "contact": customer_phone}
        body["notify"] = {"sms": True}
    auth = aiohttp.BasicAuth(cfg["key_id"], cfg["key_secret"])
    async with aiohttp.ClientSession(auth=auth, timeout=TIMEOUT) as session:
        async with session.post("https://api.razorpay.com/v1/payment_links", json=body) as r:
            data = await r.json()
            if r.status >= 300:
                return {"error": (data.get("error") or {}).get("description", f"Razorpay HTTP {r.status}")}
    return {"url": data.get("short_url"), "amount": amount,
            "currency": body["currency"], "sms_sent": bool(customer_phone)}


async def _razorpay_test(cfg: dict) -> tuple[bool, str]:
    auth = aiohttp.BasicAuth(cfg.get("key_id", ""), cfg.get("key_secret", ""))
    async with aiohttp.ClientSession(auth=auth, timeout=TIMEOUT) as session:
        async with session.get("https://api.razorpay.com/v1/payment_links?count=1") as r:
            if r.status == 200:
                return True, "Razorpay keys work"
            return False, f"Razorpay answered HTTP {r.status} — check key id/secret"


# --------------------------------------------------------------- twilio sms


async def send_sms(client_cfg: dict, to: str, body: str) -> dict:
    """SMS via Twilio. Account creds come from env (shared with telephony);
    the per-client from_number (if set) overrides TWILIO_FROM_NUMBER."""
    import os

    cfg = connector_cfg(client_cfg, "twilio_sms")
    sid = cfg.get("account_sid") or os.environ.get("TWILIO_ACCOUNT_SID", "")
    token = cfg.get("auth_token") or os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_no = cfg.get("from_number") or os.environ.get("TWILIO_FROM_NUMBER", "")
    if not (sid and token and from_no):
        return {"error": "Twilio SMS is not configured"}
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    auth = aiohttp.BasicAuth(sid, token)
    async with aiohttp.ClientSession(auth=auth, timeout=TIMEOUT) as session:
        async with session.post(url, data={"To": to, "From": from_no, "Body": body[:1500]}) as r:
            data = await r.json()
            if r.status >= 300:
                return {"error": data.get("message", f"Twilio HTTP {r.status}")}
    return {"sent": True, "to": to, "sid": data.get("sid")}


async def _twilio_sms_test(cfg: dict) -> tuple[bool, str]:
    import os

    sid = cfg.get("account_sid") or os.environ.get("TWILIO_ACCOUNT_SID", "")
    token = cfg.get("auth_token") or os.environ.get("TWILIO_AUTH_TOKEN", "")
    if not (sid and token):
        return False, "No Twilio credentials (set env or account_sid/auth_token)"
    auth = aiohttp.BasicAuth(sid, token)
    async with aiohttp.ClientSession(auth=auth, timeout=TIMEOUT) as session:
        async with session.get(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json"
        ) as r:
            if r.status == 200:
                return True, "Twilio credentials work"
            return False, f"Twilio answered HTTP {r.status}"


# ----------------------------------------------------------------- calendly


async def calendly_available_times(client_cfg: dict, days_ahead: int = 7) -> dict:
    """Open slots for the configured Calendly event type (next N days)."""
    from datetime import datetime, timedelta, timezone

    cfg = connector_cfg(client_cfg, "calendly")
    token, event_type = cfg.get("token", ""), cfg.get("event_type", "")
    if not (token and event_type):
        return {"error": "Calendly is not connected (needs token + event_type URI)"}
    start = datetime.now(timezone.utc) + timedelta(minutes=30)
    end = start + timedelta(days=min(days_ahead, 7))  # API max range is 7 days
    params = {
        "event_type": event_type,
        "start_time": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_time": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    async with aiohttp.ClientSession(
        headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT
    ) as session:
        async with session.get(
            "https://api.calendly.com/event_type_available_times", params=params
        ) as r:
            data = await r.json()
            if r.status >= 300:
                return {"error": data.get("message", f"Calendly HTTP {r.status}")}
    slots = [s.get("start_time") for s in data.get("collection", [])][:20]
    return {"slots": slots, "booking_link": cfg.get("scheduling_link", "")}


async def _calendly_test(cfg: dict) -> tuple[bool, str]:
    async with aiohttp.ClientSession(
        headers={"Authorization": f"Bearer {cfg.get('token', '')}"}, timeout=TIMEOUT
    ) as session:
        async with session.get("https://api.calendly.com/users/me") as r:
            if r.status == 200:
                data = await r.json()
                return True, f"Calendly connected as {data.get('resource', {}).get('name', 'user')}"
            return False, f"Calendly answered HTTP {r.status} — check the token"


# ------------------------------------------------------------- google sheets


async def sheets_append_row(client_cfg: dict, values: dict) -> dict:
    """Append a row via a Google Apps Script web-app URL (no OAuth dance)."""
    url = connector_cfg(client_cfg, "google_sheets").get("webhook_url", "")
    if not url:
        return {"error": "Google Sheets is not connected"}
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.post(url, json=values) as r:
            if r.status < 300:
                return {"appended": True}
            return {"error": f"Sheets webhook answered HTTP {r.status}"}


# ------------------------------------------------------------- generic REST


async def rest_lookup(client_cfg: dict, query: str) -> dict:
    """GET {base_url}{lookup_path} with {query} substituted — customer/record lookup
    against the client's own system (EMR, PMS, CRM, order DB...)."""
    from urllib.parse import quote

    cfg = connector_cfg(client_cfg, "generic_rest")
    base, path = cfg.get("base_url", "").rstrip("/"), cfg.get("lookup_path", "")
    if not (base and path):
        return {"error": "No lookup endpoint configured"}
    url = base + path.replace("{query}", quote(query, safe=""))
    async with aiohttp.ClientSession(
        headers=cfg.get("headers") or {}, timeout=TIMEOUT
    ) as session:
        async with session.get(url) as r:
            text = await r.text()
            if r.status >= 300:
                return {"error": f"System answered HTTP {r.status}"}
    try:
        return {"result": json.loads(text)}
    except json.JSONDecodeError:
        return {"result": text[:2000]}


async def rest_save(client_cfg: dict, record: dict) -> dict:
    """POST a record (booking, order, form) into the client's own system."""
    cfg = connector_cfg(client_cfg, "generic_rest")
    base, path = cfg.get("base_url", "").rstrip("/"), cfg.get("save_path", "")
    if not (base and path):
        return {"error": "No save endpoint configured"}
    async with aiohttp.ClientSession(
        headers=cfg.get("headers") or {}, timeout=TIMEOUT
    ) as session:
        async with session.post(base + path, json=record) as r:
            text = await r.text()
            if r.status >= 300:
                return {"error": f"System answered HTTP {r.status}: {text[:200]}"}
    try:
        return {"saved": True, "response": json.loads(text)}
    except json.JSONDecodeError:
        return {"saved": True}


async def _generic_rest_test(cfg: dict) -> tuple[bool, str]:
    base = cfg.get("base_url", "").rstrip("/")
    if not base:
        return False, "base_url is empty"
    async with aiohttp.ClientSession(
        headers=cfg.get("headers") or {}, timeout=TIMEOUT
    ) as session:
        async with session.get(base) as r:
            return r.status < 500, f"{base} answered HTTP {r.status}"


# ----------------------------------------------------------------- registry

CONNECTORS = {
    "shopify": {
        "name": "Shopify",
        "category": "E-commerce",
        "description": "Order webhooks trigger calls; outcomes are tagged back on the order.",
        "fields": [
            {"key": "domain", "label": "Store domain (x.myshopify.com)", "required": True},
            {"key": "access_token", "label": "Admin API access token", "secret": True, "required": True},
            {"key": "webhook_secret", "label": "Webhook signing secret", "secret": True},
        ],
        "webhook_path": "/webhooks/shopify/{client_id}",
    },
    "woocommerce": {
        "name": "WooCommerce",
        "category": "E-commerce",
        "description": "Point a WooCommerce order webhook at the platform — no keys needed.",
        "fields": [],
        "webhook_path": "/webhooks/woocommerce/{client_id}",
    },
    "stripe": {
        "name": "Stripe",
        "category": "Payments",
        "description": "The agent sends payment links mid-call (send_payment_link tool).",
        "fields": [{"key": "api_key", "label": "Secret API key (sk_live_...)", "secret": True, "required": True}],
    },
    "razorpay": {
        "name": "Razorpay",
        "category": "Payments",
        "description": "UPI/card payment links, optionally SMS'd to the caller automatically.",
        "fields": [
            {"key": "key_id", "label": "Key ID", "required": True},
            {"key": "key_secret", "label": "Key secret", "secret": True, "required": True},
        ],
    },
    "twilio_sms": {
        "name": "Twilio SMS",
        "category": "Messaging",
        "description": "The agent texts links and confirmations during the call (send_sms tool).",
        "fields": [
            {"key": "from_number", "label": "From number (blank = telephony number)"},
            {"key": "account_sid", "label": "Account SID (blank = env)"},
            {"key": "auth_token", "label": "Auth token (blank = env)", "secret": True},
        ],
    },
    "calendly": {
        "name": "Calendly",
        "category": "Scheduling",
        "description": "The agent reads real open slots and books via your Calendly.",
        "fields": [
            {"key": "token", "label": "Personal access token", "secret": True, "required": True},
            {"key": "event_type", "label": "Event type URI (api.calendly.com/event_types/...)", "required": True},
            {"key": "scheduling_link", "label": "Public scheduling link (sent to callers)"},
        ],
    },
    "google_sheets": {
        "name": "Google Sheets",
        "category": "Data",
        "description": "Every captured lead/form lands as a row (Apps Script web-app URL).",
        "fields": [{"key": "webhook_url", "label": "Apps Script web-app URL", "required": True}],
    },
    "generic_rest": {
        "name": "Custom REST API",
        "category": "Custom",
        "description": "Wire any system — hospital EMR, hotel PMS, CRM — lookup + save endpoints.",
        "fields": [
            {"key": "base_url", "label": "Base URL", "required": True},
            {"key": "headers", "label": "Headers (JSON object)", "json": True},
            {"key": "lookup_path", "label": "Lookup path, {query} = search term (e.g. /patients?phone={query})"},
            {"key": "save_path", "label": "Save path (POST target, e.g. /appointments)"},
        ],
    },
}

_TESTS = {
    "stripe": _stripe_test,
    "razorpay": _razorpay_test,
    "twilio_sms": _twilio_sms_test,
    "calendly": _calendly_test,
    "generic_rest": _generic_rest_test,
}


async def test_connector(client_cfg: dict, connector_id: str) -> tuple[bool, str]:
    """Dashboard 'Test' button: verify the stored credentials actually work."""
    if connector_id == "shopify":
        cfg = connector_cfg(client_cfg, "shopify")
        if not (cfg.get("domain") and cfg.get("access_token")):
            return False, "Store domain and access token are not set"
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.get(
                f"https://{cfg['domain']}/admin/api/2024-10/shop.json",
                headers={"X-Shopify-Access-Token": cfg["access_token"]},
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    return True, f"Connected to {data.get('shop', {}).get('name', cfg['domain'])}"
                return False, f"Shopify answered HTTP {r.status}"
    test = _TESTS.get(connector_id)
    if not test:
        return True, "Nothing to test for this connector"
    try:
        return await test(connector_cfg(client_cfg, connector_id))
    except Exception as e:
        logger.warning(f"Connector test {connector_id} failed: {e}")
        return False, f"Could not reach the service: {e}"


def connector_status(client_cfg: dict) -> list[dict]:
    """Registry + per-client configured flags, for the dashboard Integrations tab."""
    return [
        {
            "id": cid,
            "name": spec["name"],
            "category": spec["category"],
            "description": spec["description"],
            "fields": spec["fields"],
            "webhook_path": spec.get("webhook_path", "").replace(
                "{client_id}", client_cfg.get("client_id", "")
            ),
            "configured": is_configured(client_cfg, cid),
        }
        for cid, spec in CONNECTORS.items()
    ]
