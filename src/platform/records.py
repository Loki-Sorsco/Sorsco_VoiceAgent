"""Leads and appointments captured by the agent on calls (JSONL stores).

Kept separate from agent_tools so the dashboard/API can read these without
importing the voice pipeline (pipecat) stack.
"""

import json
from pathlib import Path

PLATFORM_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "platform"
LEADS_FILE = PLATFORM_DIR / "leads.jsonl"
APPOINTMENTS_FILE = PLATFORM_DIR / "appointments.jsonl"


def append_jsonl(path: Path, record: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path: Path, client_id: str | None = None, limit: int = 200) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if client_id and r.get("client_id") != client_id:
                continue
            records.append(r)
    return records[-limit:][::-1]


def list_leads(client_id: str | None = None, limit: int = 200) -> list[dict]:
    return read_jsonl(LEADS_FILE, client_id, limit)


def list_appointments(client_id: str | None = None, limit: int = 200) -> list[dict]:
    return read_jsonl(APPOINTMENTS_FILE, client_id, limit)
