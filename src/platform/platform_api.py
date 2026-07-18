"""Dashboard backend for /platform — login, role-scoped data, admin actions.

Everything here requires a session token from POST /platform/api/login
(Authorization: Bearer <token>). Role gates:

  agent      handoffs, live view, history, leads, appointments
  supervisor + analytics, queue, campaigns
  admin      + agents (clients), connectors, widget, API keys, webhooks, users

Users can additionally be scoped to specific client_ids (white-label mode:
give a hotel's staff logins that only see the hotel's agent).
"""

import json
import secrets
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from src.call_events import read_history_raw
from src.platform import auth
from src.platform.records import list_appointments, list_leads
from src.platform.connectors import CONNECTORS, connector_status, test_connector
from src.platform.handoff import (
    accept_handoff,
    get_handoff,
    list_handoffs,
    resolve_handoff,
    waiting_count,
)
from src.store import list_tasks

ROOT = Path(__file__).resolve().parent.parent.parent
CLIENTS_DIR = ROOT / "clients"

router = APIRouter(prefix="/platform/api", tags=["platform-dashboard"])


def _load_client(client_id: str) -> dict:
    path = CLIENTS_DIR / f"{client_id}.json"
    if not path.exists():
        raise HTTPException(404, f"No client '{client_id}'")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_client(cfg: dict):
    CLIENTS_DIR.mkdir(exist_ok=True)
    (CLIENTS_DIR / f"{cfg['client_id']}.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _visible_clients(user: dict) -> list[str]:
    ids = [p.stem for p in sorted(CLIENTS_DIR.glob("*.json"))]
    return [c for c in ids if auth.user_can_see(user, c)]


def _check_client(user: dict, client_id: str) -> dict:
    if not auth.user_can_see(user, client_id):
        raise HTTPException(403, "This login cannot access that agent")
    return _load_client(client_id)


# ------------------------------------------------------------------ session


@router.post("/login")
def login(body: dict):
    auth.ensure_bootstrap_admin()
    token = auth.login(body.get("email", ""), body.get("password", ""))
    if not token:
        raise HTTPException(401, "Wrong email or password")
    user = auth.check_token(token)
    return {"token": token, "user": user}


@router.get("/session")
def session(request: Request):
    user = auth.current_user(request)
    return {
        "user": user,
        "clients": _visible_clients(user),
        "handoffs_waiting": sum(waiting_count(c) for c in _visible_clients(user)),
    }


@router.post("/change-password")
def change_password(body: dict, request: Request):
    user = auth.current_user(request)
    current, new = body.get("current", ""), body.get("new", "")
    if len(new) < 8:
        raise HTTPException(400, "New password must be at least 8 characters")
    if not auth.login(user["email"], current):
        raise HTTPException(401, "Current password is wrong")
    stored = auth.list_users()[user["email"]]
    auth.save_user(user["email"], stored["name"], stored["role"], new,
                   stored.get("client_ids"))
    return {"changed": True}


# -------------------------------------------------------------------- users


@router.get("/users")
def users(request: Request):
    auth.require_role(request, "admin")
    return {
        "users": [
            {"email": e, "name": u.get("name", ""), "role": u.get("role", ""),
             "client_ids": u.get("client_ids", ["*"]), "created": u.get("created", "")}
            for e, u in sorted(auth.list_users().items())
        ]
    }


@router.post("/users")
def save_user(body: dict, request: Request):
    auth.require_role(request, "admin")
    email = (body.get("email") or "").strip().lower()
    if "@" not in email:
        raise HTTPException(400, "A valid email is required")
    password = body.get("password") or None
    if password and len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    try:
        auth.save_user(
            email,
            body.get("name") or email.split("@")[0],
            body.get("role") or "agent",
            password,
            body.get("client_ids") if body.get("client_ids") else ["*"],
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"saved": email}


@router.delete("/users/{email}")
def delete_user(email: str, request: Request):
    user = auth.require_role(request, "admin")
    if email.strip().lower() == user["email"]:
        raise HTTPException(400, "You cannot delete your own login")
    auth.delete_user(email)
    return {"deleted": email}


# ----------------------------------------------------------------- API keys


@router.get("/keys")
def keys(request: Request, client_id: str | None = None):
    auth.require_role(request, "admin")
    return {"keys": auth.list_api_keys(client_id)}


@router.post("/keys")
def create_key(body: dict, request: Request):
    auth.require_role(request, "admin")
    client_id = body.get("client_id", "")
    _load_client(client_id)
    return auth.create_api_key(client_id, body.get("label", ""))


@router.post("/keys/{key_id}/revoke")
def revoke_key(key_id: str, request: Request):
    auth.require_role(request, "admin")
    auth.revoke_api_key(key_id)
    return {"revoked": key_id}


# --------------------------------------------------------------- connectors


@router.get("/connectors/{client_id}")
def get_connectors(client_id: str, request: Request):
    user = auth.require_role(request, "admin")
    cfg = _check_client(user, client_id)
    status = connector_status(cfg)
    # Include saved values so the form can be edited (secrets stay masked in UI).
    for item in status:
        if item["id"] == "shopify":
            item["values"] = cfg.get("shopify") or {}
        else:
            item["values"] = (cfg.get("connectors") or {}).get(item["id"]) or {}
    return {"connectors": status}


@router.post("/connectors/{client_id}/{connector_id}")
def save_connector(client_id: str, connector_id: str, body: dict, request: Request):
    user = auth.require_role(request, "admin")
    if connector_id not in CONNECTORS:
        raise HTTPException(404, "Unknown connector")
    cfg = _check_client(user, client_id)
    values = body.get("values") or {}
    if "headers" in values and isinstance(values["headers"], str):
        try:
            values["headers"] = json.loads(values["headers"] or "{}")
        except json.JSONDecodeError:
            raise HTTPException(400, "Headers must be a JSON object")
    if connector_id == "shopify":
        cfg["shopify"] = values
    else:
        cfg.setdefault("connectors", {})[connector_id] = values
    _save_client(cfg)
    return {"saved": connector_id}


@router.post("/connectors/{client_id}/{connector_id}/test")
async def check_connector(client_id: str, connector_id: str, request: Request):
    user = auth.require_role(request, "admin")
    cfg = _check_client(user, client_id)
    ok, message = await test_connector(cfg, connector_id)
    return {"ok": ok, "message": message}


# ----------------------------------------------------- webhooks (outbound)


@router.get("/webhooks/{client_id}")
def get_webhooks(client_id: str, request: Request):
    user = auth.require_role(request, "admin")
    cfg = _check_client(user, client_id)
    from src.platform.webhooks_out import EVENT_TYPES

    return {"webhooks": cfg.get("webhooks") or [], "event_types": EVENT_TYPES}


@router.post("/webhooks/{client_id}")
def save_webhooks(client_id: str, body: dict, request: Request):
    user = auth.require_role(request, "admin")
    cfg = _check_client(user, client_id)
    endpoints = []
    for ep in (body.get("webhooks") or [])[:10]:
        url = (ep.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        endpoints.append({
            "url": url,
            "secret": ep.get("secret") or "whsec_" + secrets.token_urlsafe(16),
            "events": ep.get("events") or [],
        })
    cfg["webhooks"] = endpoints
    _save_client(cfg)
    return {"saved": len(endpoints), "webhooks": endpoints}


# ------------------------------------------------------------------- widget


@router.get("/widget/{client_id}")
def widget_info(client_id: str, request: Request):
    """Embed snippet with a real pk key (mints the first key pair if none)."""
    user = auth.require_role(request, "admin")
    cfg = _check_client(user, client_id)
    existing = [k for k in auth.list_api_keys(client_id) if not k["revoked"]]
    if existing:
        publishable = existing[0]["publishable"]
        fresh_secret = None
    else:
        minted = auth.create_api_key(client_id, "default")
        publishable = minted["publishable"]
        fresh_secret = minted["secret"]
    return {
        "publishable": publishable,
        "fresh_secret": fresh_secret,  # only present right after first mint
        "widget": cfg.get("widget") or {},
        "snippet": (
            f'<script src="https://YOUR-DOMAIN/widget.js" data-key="{publishable}" async></script>'
        ),
    }


@router.post("/widget/{client_id}")
def save_widget(client_id: str, body: dict, request: Request):
    user = auth.require_role(request, "admin")
    cfg = _check_client(user, client_id)
    widget = body.get("widget") or {}
    cfg["widget"] = {
        "color": (widget.get("color") or "#4f46e5")[:16],
        "position": "left" if widget.get("position") == "left" else "right",
        "greeting": (widget.get("greeting") or "")[:120],
        "hide_branding": bool(widget.get("hide_branding")),
    }
    _save_client(cfg)
    return {"saved": True}


# ----------------------------------------------------------------- handoffs


@router.get("/handoffs")
def handoffs(request: Request, client_id: str | None = None):
    user = auth.current_user(request)
    if client_id:
        _check_client(user, client_id)
        return {"handoffs": list_handoffs(client_id)}
    out = []
    for c in _visible_clients(user):
        out.extend(list_handoffs(c))
    out.sort(key=lambda h: h.get("created", ""), reverse=True)
    return {"handoffs": out[:100]}


@router.post("/handoffs/{handoff_id}/accept")
async def accept(handoff_id: str, request: Request):
    user = auth.current_user(request)
    record = get_handoff(handoff_id)
    if not record:
        raise HTTPException(404, "No such handoff")
    cfg = _check_client(user, record["client_id"])
    record = await accept_handoff(handoff_id, user["name"], cfg)
    return {"accepted": handoff_id, "transferred": record.get("transferred", False)}


@router.post("/handoffs/{handoff_id}/resolve")
def resolve(handoff_id: str, body: dict, request: Request):
    user = auth.current_user(request)
    record = get_handoff(handoff_id)
    if not record:
        raise HTTPException(404, "No such handoff")
    cfg = _check_client(user, record["client_id"])
    resolve_handoff(handoff_id, cfg, (body or {}).get("note", ""))
    return {"resolved": handoff_id}


# ----------------------------------------------- history, leads, queue, stats


@router.get("/history")
def history(request: Request, client_id: str | None = None):
    user = auth.current_user(request)
    visible = set(_visible_clients(user))
    records = [
        r for r in read_history_raw()
        if r.get("client_id") in visible
        and (not client_id or r.get("client_id") == client_id)
    ]
    return {"calls": records[-100:][::-1]}


@router.get("/leads")
def leads(request: Request, client_id: str | None = None):
    user = auth.current_user(request)
    if client_id:
        _check_client(user, client_id)
        return {"leads": list_leads(client_id)}
    visible = set(_visible_clients(user))
    return {"leads": [r for r in list_leads() if r.get("client_id") in visible]}


@router.get("/appointments")
def appointments(request: Request, client_id: str | None = None):
    user = auth.current_user(request)
    if client_id:
        _check_client(user, client_id)
        return {"appointments": list_appointments(client_id)}
    visible = set(_visible_clients(user))
    return {"appointments": [r for r in list_appointments() if r.get("client_id") in visible]}


@router.get("/queue")
def queue(request: Request):
    user = auth.require_role(request, "supervisor")
    visible = set(_visible_clients(user))
    tasks = [t for t in list_tasks() if t["client_id"] in visible]
    return {"tasks": tasks[-100:][::-1]}


@router.get("/overview")
def overview(request: Request, client_id: str | None = None):
    user = auth.current_user(request)
    visible = set(_visible_clients(user))
    if client_id:
        if client_id not in visible:
            raise HTTPException(403, "This login cannot access that agent")
        visible = {client_id}
    records = [r for r in read_history_raw() if r.get("client_id") in visible]
    categories, sentiments = {}, {"positive": 0, "neutral": 0, "negative": 0}
    hot = 0
    for r in records:
        a = r.get("analysis") or {}
        if a.get("category"):
            categories[a["category"]] = categories.get(a["category"], 0) + 1
        if a.get("sentiment") in sentiments:
            sentiments[a["sentiment"]] += 1
        if a.get("intent") == "hot":
            hot += 1
    handoff_records = [h for c in visible for h in list_handoffs(c)]
    return {
        "calls_total": len(records),
        "inbound": sum(1 for r in records if r.get("kind") == "inbound"),
        "outbound": sum(1 for r in records if r.get("kind") != "inbound"),
        "confirmed": sum(1 for r in records if r.get("outcome") == "confirmed"),
        "minutes": round(sum(r.get("duration_s", 0) for r in records) / 60, 1),
        "hot_leads": hot,
        "sentiments": sentiments,
        "top_categories": sorted(categories.items(), key=lambda kv: -kv[1])[:6],
        "handoffs_waiting": sum(1 for h in handoff_records if h["status"] == "waiting"),
        "handoffs_resolved": sum(1 for h in handoff_records if h["status"] == "resolved"),
        "leads_captured": sum(1 for r in list_leads() if r.get("client_id") in visible),
        "appointments_booked": sum(
            1 for r in list_appointments() if r.get("client_id") in visible
        ),
    }


# ------------------------------------------------------------------- agents


AGENT_FORM_FIELDS = [
    "business_name", "agent_name", "persona", "knowledge", "default_language",
    "supported_languages", "tts_voice", "voice_engine", "call_workflow",
    "call_rules", "data_capture", "appointments", "handoff", "call_hours",
]


@router.get("/agents")
def agents(request: Request):
    user = auth.current_user(request)
    out = []
    for cid in _visible_clients(user):
        try:
            cfg = _load_client(cid)
        except HTTPException:
            continue
        out.append({
            "client_id": cid,
            "business_name": cfg.get("business_name", cid),
            "agent_name": cfg.get("agent_name", ""),
            "default_language": cfg.get("default_language", ""),
            "tts_voice": cfg.get("tts_voice", ""),
        })
    return {"agents": out}


@router.get("/agents/{client_id}")
def get_agent(client_id: str, request: Request):
    user = auth.current_user(request)
    cfg = _check_client(user, client_id)
    return {k: cfg.get(k) for k in ["client_id", *AGENT_FORM_FIELDS]}


@router.post("/agents/{client_id}")
def save_agent(client_id: str, body: dict, request: Request):
    user = auth.require_role(request, "admin")
    client_id = client_id.strip().lower().replace(" ", "_").replace("-", "_")
    if not client_id.replace("_", "").isalnum():
        raise HTTPException(400, "Agent ID must be letters, numbers, underscores")
    path = CLIENTS_DIR / f"{client_id}.json"
    cfg = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if path.exists() and not auth.user_can_see(user, client_id):
        raise HTTPException(403, "This login cannot access that agent")
    for field in AGENT_FORM_FIELDS:
        if field in body:
            cfg[field] = body[field]
    missing = [f for f in ("business_name", "agent_name", "persona") if not cfg.get(f)]
    if missing:
        raise HTTPException(400, f"Missing fields: {', '.join(missing)}")
    cfg["client_id"] = client_id
    cfg.setdefault("knowledge", {})
    cfg.setdefault("default_language", "hi-IN")
    cfg.setdefault("supported_languages", ["hi-IN", "en-IN"])
    cfg.setdefault("tts_voice", "priya")
    _save_client(cfg)
    return {"saved": client_id}


@router.post("/agents/{client_id}/activate")
def activate_agent(client_id: str, request: Request):
    """Point the live call line (browser + inbound phone) at this agent."""
    user = auth.require_role(request, "supervisor")
    _check_client(user, client_id)
    from src.admin import ACTIVE_FILE

    ACTIVE_FILE.parent.mkdir(exist_ok=True)
    ACTIVE_FILE.write_text(client_id, encoding="utf-8")
    return {"active": client_id}


def register_platform(app):
    """Mount all platform routers + the dashboard page onto the runner's app."""
    from src.platform.platform_ui import PLATFORM_PAGE
    from src.platform.public_api import router as public_router
    from src.platform.widget import router as widget_router

    auth.ensure_bootstrap_admin()
    app.include_router(router)
    app.include_router(public_router)
    app.include_router(widget_router)

    @app.get("/platform", response_class=HTMLResponse)
    def platform_page():
        return PLATFORM_PAGE
