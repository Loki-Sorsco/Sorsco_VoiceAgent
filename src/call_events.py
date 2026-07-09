"""Shared call-event log between the voice bot and the dashboard.

The voice bot process appends events (user/assistant turns, tool calls) to
data/call_events.jsonl; the dashboard process polls and renders them as the
live call view. A file is the simplest thing that works across two processes —
in production this becomes a message queue / websocket.
"""

import json
from datetime import datetime
from pathlib import Path

EVENTS_FILE = Path(__file__).resolve().parent.parent / "data" / "call_events.jsonl"


def reset_events():
    EVENTS_FILE.parent.mkdir(exist_ok=True)
    EVENTS_FILE.write_text("", encoding="utf-8")


def log_event(event_type: str, **data):
    event = {
        "type": event_type,
        "time": datetime.now().strftime("%H:%M:%S"),
        **data,
    }
    with open(EVENTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_events(since: int = 0) -> list[dict]:
    """Return events after line index `since` (for incremental polling)."""
    if not EVENTS_FILE.exists():
        return []
    events = []
    with open(EVENTS_FILE, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i < since or not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def count_events() -> int:
    if not EVENTS_FILE.exists():
        return 0
    with open(EVENTS_FILE, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())
