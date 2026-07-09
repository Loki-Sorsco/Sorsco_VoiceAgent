"""Hotel tools the LLM can call during the conversation.

check_availability reads a mock JSON "database" (data/availability.json).
notify_manager prints the lead to the console and appends it to data/leads.json.

In production these become real connectors: check_availability queries the
hotel's PMS/database, notify_manager sends a WhatsApp/SMS/email to the manager.
The LLM-facing interface stays exactly the same.
"""

import json
from datetime import date, timedelta
from pathlib import Path

from loguru import logger

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
AVAILABILITY_FILE = DATA_DIR / "availability.json"
LEADS_FILE = DATA_DIR / "leads.json"


def _load_availability() -> dict:
    with open(AVAILABILITY_FILE, encoding="utf-8") as f:
        return json.load(f)


def check_availability(room_type: str, check_in: str, check_out: str) -> dict:
    """Check how many rooms of a given type are free for a date range.

    Always use this before telling the caller about availability.

    Args:
        room_type: One of "standard", "deluxe", "suite".
        check_in: Check-in date, YYYY-MM-DD.
        check_out: Check-out date, YYYY-MM-DD. Must be after check_in.
    """
    db = _load_availability()
    room_type = room_type.lower().strip()
    if room_type not in db:
        return {
            "available": False,
            "error": f"Unknown room type '{room_type}'. Valid types: {list(db.keys())}",
        }

    try:
        start = date.fromisoformat(check_in)
        end = date.fromisoformat(check_out)
    except ValueError:
        return {"available": False, "error": "Dates must be YYYY-MM-DD."}
    if end <= start:
        return {"available": False, "error": "check_out must be after check_in."}

    room = db[room_type]
    nights = []
    min_free = room["total_rooms"]
    day = start
    while day < end:
        booked = room["booked"].get(day.isoformat(), 0)
        free = room["total_rooms"] - booked
        min_free = min(min_free, free)
        nights.append({"date": day.isoformat(), "rooms_free": free})
        day += timedelta(days=1)

    return {
        "available": min_free > 0,
        "room_type": room_type,
        "check_in": check_in,
        "check_out": check_out,
        "rooms_free_all_nights": max(min_free, 0),
        "per_night": nights,
    }


def notify_manager(
    guest_name: str,
    guest_phone: str,
    room_type: str,
    check_in: str,
    check_out: str,
    num_guests: int = 1,
    notes: str = "",
) -> dict:
    """Send a confirmed booking lead to the hotel manager.

    Only call AFTER the caller has confirmed name, phone number, room type and
    dates. For the MVP this logs to the console and data/leads.json.

    Args:
        guest_name: Guest's full name.
        guest_phone: Guest's phone number.
        room_type: One of "standard", "deluxe", "suite".
        check_in: Check-in date, YYYY-MM-DD.
        check_out: Check-out date, YYYY-MM-DD.
        num_guests: Number of guests staying.
        notes: Any special requests from the guest.
    """
    lead = {
        "guest_name": guest_name,
        "guest_phone": guest_phone,
        "room_type": room_type,
        "check_in": check_in,
        "check_out": check_out,
        "num_guests": num_guests,
        "notes": notes,
    }

    leads = []
    if LEADS_FILE.exists():
        with open(LEADS_FILE, encoding="utf-8") as f:
            leads = json.load(f)
    leads.append(lead)
    with open(LEADS_FILE, "w", encoding="utf-8") as f:
        json.dump(leads, f, ensure_ascii=False, indent=2)

    logger.info("=" * 60)
    logger.info("NEW BOOKING LEAD -> notifying manager")
    for key, value in lead.items():
        logger.info(f"  {key}: {value}")
    logger.info("=" * 60)

    return {"status": "manager_notified", "lead": lead}
