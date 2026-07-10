"""Tiny JSON persistence for orders and the call queue.

Single-process by design: the Pipecat runner hosts the webhooks, the admin UI
and the bot, so plain JSON files are safe here. Swap for SQLite/Postgres when
calls run concurrently at scale.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ORDERS_FILE = DATA_DIR / "orders.json"
QUEUE_FILE = DATA_DIR / "call_queue.json"
ACTIVE_TASK_FILE = DATA_DIR / "active_task.json"


def _load(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return default


def _save(path: Path, data):
    DATA_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------------- orders


def save_order(order: dict):
    orders = _load(ORDERS_FILE, {})
    orders[str(order["order_id"])] = order
    _save(ORDERS_FILE, orders)


def get_order(order_id: str) -> dict | None:
    return _load(ORDERS_FILE, {}).get(str(order_id))


def update_order(order_id: str, **fields):
    orders = _load(ORDERS_FILE, {})
    if str(order_id) in orders:
        orders[str(order_id)].update(fields)
        _save(ORDERS_FILE, orders)


# --------------------------------------------------------------- call queue


def add_task(client_id: str, order: dict, reason: str, flow: str) -> dict:
    tasks = _load(QUEUE_FILE, [])
    task = {
        "task_id": uuid.uuid4().hex[:8],
        "client_id": client_id,
        "order_id": str(order["order_id"]),
        "customer_name": order.get("customer_name", ""),
        "customer_phone": order.get("customer_phone", ""),
        "reason": reason,
        "flow": flow,
        "status": "queued",
        "outcome": None,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    tasks.append(task)
    _save(QUEUE_FILE, tasks)
    return task


def list_tasks() -> list[dict]:
    return _load(QUEUE_FILE, [])


def get_task(task_id: str) -> dict | None:
    return next((t for t in list_tasks() if t["task_id"] == task_id), None)


def update_task(task_id: str, **fields):
    tasks = _load(QUEUE_FILE, [])
    for t in tasks:
        if t["task_id"] == task_id:
            t.update(fields)
    _save(QUEUE_FILE, tasks)


# -------------------------------------------------- active task (demo mode)


def set_active_task(task_id: str | None):
    if task_id is None:
        ACTIVE_TASK_FILE.unlink(missing_ok=True)
    else:
        _save(ACTIVE_TASK_FILE, {"task_id": task_id})


def get_active_task() -> dict | None:
    ref = _load(ACTIVE_TASK_FILE, None)
    if not ref:
        return None
    return get_task(ref.get("task_id", ""))
