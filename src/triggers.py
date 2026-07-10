"""Trigger rules: which store events queue an outbound call.

Rules live in the client config JSON under "triggers" (editable in /admin):

  "triggers": {
    "cod_confirm":       {"enabled": true,  "min_value": 0},
    "pending_payment":   {"enabled": true,  "min_value": 500},
    "abandoned_checkout":{"enabled": false, "min_value": 1000}
  }

Each fired rule creates a task in the call queue. In demo mode tasks are taken
from /admin in the browser; with telephony they become automatic dials.
"""

from loguru import logger

from src.store import add_task, save_order

DEFAULT_TRIGGERS = {
    "cod_confirm": {"enabled": True, "min_value": 0},
    "pending_payment": {"enabled": True, "min_value": 0},
    "abandoned_checkout": {"enabled": False, "min_value": 0},
}

FLOW_DESCRIPTIONS = {
    "cod_confirm": "Confirm this Cash-on-Delivery order and verify the delivery address",
    "pending_payment": "Payment is pending — help the customer complete it and close the sale",
    "abandoned_checkout": "Customer left items in cart — help them complete the purchase",
}


def normalize_shopify_order(payload: dict, client_id: str) -> dict:
    """Flatten the fields the agent needs from a Shopify order/checkout payload."""
    customer = payload.get("customer") or {}
    address = payload.get("shipping_address") or payload.get("billing_address") or {}
    items = [
        {
            "title": li.get("title", "item"),
            "quantity": li.get("quantity", 1),
            "price": li.get("price", "0"),
        }
        for li in payload.get("line_items", [])
    ]
    name = " ".join(
        p for p in [customer.get("first_name"), customer.get("last_name")] if p
    ) or address.get("name", "")
    return {
        "order_id": payload.get("id") or payload.get("token", "unknown"),
        "order_number": payload.get("name") or payload.get("order_number", ""),
        "client_id": client_id,
        "customer_name": name,
        "customer_phone": payload.get("phone")
        or customer.get("phone")
        or address.get("phone", ""),
        "total": payload.get("total_price", "0"),
        "currency": payload.get("currency", "INR"),
        "items": items,
        "payment_gateway": ",".join(payload.get("payment_gateway_names", [])),
        "financial_status": payload.get("financial_status", ""),
        "address": ", ".join(
            str(p)
            for p in [
                address.get("address1"),
                address.get("city"),
                address.get("province"),
                address.get("zip"),
            ]
            if p
        ),
        "status": "new",
    }


def evaluate(event_topic: str, payload: dict, client_cfg: dict) -> dict | None:
    """Apply the client's trigger rules to an incoming store event.

    Returns the created call task, or None if no rule fired.
    """
    client_id = client_cfg["client_id"]
    triggers = {**DEFAULT_TRIGGERS, **client_cfg.get("triggers", {})}
    order = normalize_shopify_order(payload, client_id)
    save_order(order)

    total = float(order["total"] or 0)
    gateway = order["payment_gateway"].lower()
    fin_status = order["financial_status"].lower()

    def rule_on(name):
        rule = triggers.get(name, {})
        return rule.get("enabled") and total >= float(rule.get("min_value", 0) or 0)

    flow = None
    if event_topic.startswith("orders/create"):
        is_cod = "cash on delivery" in gateway or "cod" in gateway.split(",")
        if is_cod and rule_on("cod_confirm"):
            flow = "cod_confirm"
        elif fin_status == "pending" and not is_cod and rule_on("pending_payment"):
            flow = "pending_payment"
    elif event_topic.startswith("checkouts/") and rule_on("abandoned_checkout"):
        flow = "abandoned_checkout"

    if not flow:
        logger.info(f"No trigger fired for {event_topic} (order {order['order_number']})")
        return None

    task = add_task(client_id, order, FLOW_DESCRIPTIONS[flow], flow)
    logger.info(
        f"Trigger '{flow}' fired for order {order['order_number']} -> call task {task['task_id']}"
    )
    return task
