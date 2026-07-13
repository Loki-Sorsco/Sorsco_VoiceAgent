"""Cross-call customer memory + knowledge-gap mining over call history.

Two capabilities most budget voice agents lack:

- Customer memory: the agent recognises a returning caller (by phone number)
  and gets a short recap of past calls injected into its prompt, so it can
  greet them by name and continue prior context — like a receptionist who
  remembers regulars.

- Knowledge gaps: questions the agent could not answer are surfaced so the
  business can add them and the agent gets smarter over time.
"""

import re

from src.call_events import read_history_raw


def _digits(phone: str) -> str:
    d = re.sub(r"\D", "", phone or "")
    return d[-10:]  # last 10 digits — India mobile, ignores +91 / 0 prefixes


def prior_calls(phone: str, limit: int = 3) -> list[dict]:
    """Past finished calls with this number, newest first (max `limit`)."""
    key = _digits(phone)
    if not key:
        return []
    out = []
    for r in read_history_raw():
        if _digits(r.get("customer_phone", "")) == key:
            out.append(r)
    return out[::-1][:limit]


def memory_note(phone: str, current_name: str = "") -> str:
    """One short block to inject into the system prompt, or '' if new caller."""
    calls = prior_calls(phone)
    if not calls:
        return ""
    lines = []
    name = current_name
    for c in calls:
        a = c.get("analysis") or {}
        name = name or c.get("customer_name") or ""
        when = (c.get("started") or "")[:10] or "earlier"
        summ = a.get("summary") or c.get("outcome") or "spoke with us"
        lines.append(f"- {when}: {summ}")
    who = f" ({name})" if name else ""
    return (
        f"RETURNING CALLER{who}: you have spoken with this customer before. "
        "Recent history:\n" + "\n".join(lines) + "\n"
        "Greet them warmly as a returning customer and reference this naturally "
        "if relevant — do not pretend it's the first contact."
    )


def knowledge_gaps(client_id: str | None = None) -> list[dict]:
    """Questions the agent couldn't answer, grouped, most frequent first."""
    buckets: dict[str, dict] = {}
    for r in read_history_raw():
        if client_id and r.get("client_id") != client_id:
            continue
        a = r.get("analysis") or {}
        q = (a.get("unanswered") or "").strip()
        if not q or q.lower() in ("none", "n/a", "-", ""):
            continue
        key = re.sub(r"\s+", " ", q.lower())[:80]
        b = buckets.setdefault(key, {"question": q, "count": 0, "agent": r.get("agent", ""),
                                     "last": r.get("started", "")})
        b["count"] += 1
    return sorted(buckets.values(), key=lambda x: -x["count"])
