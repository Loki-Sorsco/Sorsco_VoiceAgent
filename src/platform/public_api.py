"""Public REST API (/v1) — the API-first surface for custom integrations.

Auth: every request carries the client's secret key:

  Authorization: Bearer sk_...        (minted in the dashboard, per client)

The key IS the tenant — every endpoint is automatically scoped to the client
the key belongs to, so a hotel can never read a clinic's calls.

  GET  /v1/me                     who am I / key check
  GET  /v1/agent                  agent config (persona, languages, workflow...)
  PATCH /v1/agent                 update the agent from your own admin panel
  POST /v1/calls                  queue an outbound call {name, phone, purpose, dial?}
  GET  /v1/calls                  call history incl. transcripts + AI analysis
  GET  /v1/calls/{call_id}        one call
  GET  /v1/queue                  pending outbound-call tasks
  GET  /v1/handoffs               human-handoff requests (context + summary)
  POST /v1/handoffs/{id}/resolve  close a handoff from your own tooling
  GET  /v1/leads                  leads the agent captured on calls
  GET  /v1/appointments           appointments the agent booked
  GET  /v1/analytics              call volume, outcomes, sentiment, categories
"""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from src.call_events import read_history_raw
from src.platform.records import list_appointments, list_leads
from src.platform.auth import api_client
from src.platform.handoff import get_handoff, list_handoffs, resolve_handoff
from src.platform.webhooks_out import emit
from src.store import list_tasks
from src.triggers import queue_manual_call

ROOT = Path(__file__).resolve().parent.parent.parent
CLIENTS_DIR = ROOT / "clients"

router = APIRouter(prefix="/v1", tags=["public-api"])

# Fields an API caller may read/write on the agent config. Secrets (connector
# credentials, webhook secrets) are managed in the dashboard only.
AGENT_READ_FIELDS = [
    "client_id", "business_name", "agent_name", "persona", "knowledge",
    "default_language", "supported_languages", "tts_voice", "call_workflow",
    "call_rules", "data_capture", "triggers", "call_hours", "widget",
]
AGENT_WRITE_FIELDS = [
    "business_name", "agent_name", "persona", "knowledge", "default_language",
    "supported_languages", "tts_voice", "call_workflow", "call_rules",
    "data_capture", "triggers", "call_hours", "widget",
]


def _load_client(client_id: str) -> dict:
    path = CLIENTS_DIR / f"{client_id}.json"
    if not path.exists():
        raise HTTPException(404, f"Client '{client_id}' no longer exists")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_client(cfg: dict):
    path = CLIENTS_DIR / f"{cfg['client_id']}.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


@router.get("/me")
def me(client_id: str = Depends(api_client)):
    cfg = _load_client(client_id)
    return {
        "client_id": client_id,
        "business_name": cfg.get("business_name", ""),
        "agent_name": cfg.get("agent_name", ""),
    }


@router.get("/agent")
def get_agent(client_id: str = Depends(api_client)):
    cfg = _load_client(client_id)
    return {k: cfg.get(k) for k in AGENT_READ_FIELDS}


@router.patch("/agent")
def update_agent(body: dict, client_id: str = Depends(api_client)):
    cfg = _load_client(client_id)
    changed = [k for k in AGENT_WRITE_FIELDS if k in body]
    if not changed:
        raise HTTPException(400, f"Nothing to update. Writable fields: {AGENT_WRITE_FIELDS}")
    for k in changed:
        cfg[k] = body[k]
    _save_client(cfg)
    return {"updated": changed}


@router.post("/calls")
def create_call(body: dict, client_id: str = Depends(api_client)):
    cfg = _load_client(client_id)
    phone = (body.get("phone") or "").strip()
    if not phone:
        raise HTTPException(400, "phone is required")
    task = queue_manual_call(
        cfg,
        body.get("name") or "the customer",
        phone,
        body.get("purpose") or "Follow up with this customer",
    )
    emit("task.queued", cfg, {"task_id": task["task_id"], "phone": phone,
                              "purpose": task["reason"]})
    return {"task_id": task["task_id"], "status": "queued",
            "note": "Dial from the dashboard queue, or enable telephony auto-dial."}


@router.get("/calls")
def calls(limit: int = 50, client_id: str = Depends(api_client)):
    records = [r for r in read_history_raw() if r.get("client_id") == client_id]
    return {"calls": records[-min(limit, 200):][::-1]}


@router.get("/calls/{call_id}")
def call_detail(call_id: str, client_id: str = Depends(api_client)):
    for r in read_history_raw():
        if r.get("call_id") == call_id and r.get("client_id") == client_id:
            return r
    raise HTTPException(404, "No such call")


@router.get("/queue")
def queue(client_id: str = Depends(api_client)):
    tasks = [t for t in list_tasks() if t["client_id"] == client_id]
    return {"tasks": tasks[-100:][::-1]}


@router.get("/handoffs")
def handoffs(client_id: str = Depends(api_client)):
    return {"handoffs": list_handoffs(client_id)}


@router.post("/handoffs/{handoff_id}/resolve")
def handoff_resolve(handoff_id: str, body: dict | None = None,
                    client_id: str = Depends(api_client)):
    record = get_handoff(handoff_id)
    if not record or record["client_id"] != client_id:
        raise HTTPException(404, "No such handoff")
    resolve_handoff(handoff_id, _load_client(client_id), (body or {}).get("note", ""))
    return {"resolved": handoff_id}


@router.get("/leads")
def leads(limit: int = 100, client_id: str = Depends(api_client)):
    return {"leads": list_leads(client_id, min(limit, 500))}


@router.get("/appointments")
def appointments(limit: int = 100, client_id: str = Depends(api_client)):
    return {"appointments": list_appointments(client_id, min(limit, 500))}


@router.get("/analytics")
def analytics(client_id: str = Depends(api_client)):
    records = [r for r in read_history_raw() if r.get("client_id") == client_id]
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
    return {
        "calls_total": len(records),
        "inbound": sum(1 for r in records if r.get("kind") == "inbound"),
        "outbound": sum(1 for r in records if r.get("kind") != "inbound"),
        "confirmed": sum(1 for r in records if r.get("outcome") == "confirmed"),
        "cancelled": sum(1 for r in records if r.get("outcome") == "cancelled"),
        "minutes": round(sum(r.get("duration_s", 0) for r in records) / 60, 1),
        "hot_leads": hot,
        "sentiments": sentiments,
        "top_categories": sorted(categories.items(), key=lambda kv: -kv[1])[:6],
        "handoffs_waiting": sum(
            1 for h in list_handoffs(client_id) if h["status"] == "waiting"
        ),
        "leads_captured": len(list_leads(client_id, 500)),
        "appointments_booked": len(list_appointments(client_id, 500)),
    }
