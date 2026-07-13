"""Post-call analysis: summary, caller's issue, category — auto-generated.

Runs after each call (and lazily backfills older calls). Powers the history
view and the Excel export.
"""

import json

from loguru import logger

CATEGORIES = [
    "booking_inquiry",
    "order_confirmation",
    "order_cancellation",
    "payment_issue",
    "address_change",
    "product_question",
    "complaint",
    "callback_request",
    "casual_or_test",
    "wrong_number",
    "other",
]

_PROMPT = """You analyse call-centre transcripts. Reply with ONLY a JSON object, no other text:
{"summary": "<one sentence: what happened on this call>",
 "issue": "<the caller's main question/problem/request in one short sentence, or 'none'>",
 "category": "<one of: %s>",
 "resolution": "<resolved | unresolved | follow_up_needed>",
 "language": "<main language the CALLER spoke, e.g. Hindi, Hinglish, English>"}

Write summary and issue in simple English regardless of the call language.""" % ", ".join(CATEGORIES)


def analyze_call(record: dict) -> dict | None:
    """Return the analysis dict, or None if it can't be produced."""
    transcript = record.get("transcript") or []
    lines = []
    for e in transcript:
        if e.get("type") in ("user", "assistant"):
            who = "CALLER" if e["type"] == "user" else "AGENT"
            lines.append(f"{who}: {e.get('text', '')}")
        elif e.get("type") == "tool":
            lines.append(f"[action: {e.get('name')}]")
    if not lines:
        return {
            "summary": "Call connected but no conversation happened.",
            "issue": "none",
            "category": "casual_or_test",
            "resolution": "unresolved",
            "language": "-",
        }

    from src.llm_factory import chat_complete

    context = (
        f"Call type: {record.get('kind', 'inbound')}. "
        f"Business: {record.get('client', '')}. Outcome recorded: {record.get('outcome') or 'none'}.\n\n"
        + "\n".join(lines[:60])
    )
    try:
        reply = chat_complete(_PROMPT, [{"role": "user", "content": context}])
        start, end = reply.find("{"), reply.rfind("}")
        data = json.loads(reply[start : end + 1])
        if data.get("category") not in CATEGORIES:
            data["category"] = "other"
        return {
            "summary": str(data.get("summary", ""))[:300],
            "issue": str(data.get("issue", ""))[:300],
            "category": data["category"],
            "resolution": str(data.get("resolution", "unresolved"))[:40],
            "language": str(data.get("language", ""))[:40],
        }
    except Exception as e:
        logger.warning(f"Call analysis failed: {e}")
        return None
