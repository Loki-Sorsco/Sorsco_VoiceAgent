"""Tools the agent uses on ORDER calls (COD confirm, pending payment, cart).

Outcomes are written to the call queue and the local order store. If the
client config has Shopify credentials ("shopify": {"domain", "access_token"}),
the outcome is also tagged on the real order via the Admin API — otherwise
everything still works locally (free demo mode, no Shopify account needed).
"""

import os

from loguru import logger

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams

from src.call_events import log_event
from src.store import get_order, update_order, update_task

ORDER_TOOLS = ToolsSchema(
    standard_tools=[
        FunctionSchema(
            name="confirm_order",
            description=(
                "Record that the customer CONFIRMED the order (wants it delivered / "
                "will pay). Call after the customer clearly says yes."
            ),
            properties={
                "notes": {"type": "string", "description": "Anything the customer asked or changed"}
            },
            required=[],
        ),
        FunctionSchema(
            name="cancel_order",
            description=(
                "Record that the customer wants to CANCEL the order. Call only after "
                "the customer clearly says they don't want it."
            ),
            properties={
                "reason": {"type": "string", "description": "Why the customer cancelled"}
            },
            required=["reason"],
        ),
        FunctionSchema(
            name="update_delivery_address",
            description="Save a corrected delivery address the customer gives you.",
            properties={"new_address": {"type": "string"}},
            required=["new_address"],
        ),
        FunctionSchema(
            name="send_payment_link",
            description=(
                "Send the customer a payment link by SMS so they can complete a "
                "pending payment. Confirm their phone number first."
            ),
            properties={"phone": {"type": "string"}},
            required=["phone"],
        ),
        FunctionSchema(
            name="schedule_callback",
            description="Customer asked to be called back later. Record when.",
            properties={"when": {"type": "string", "description": "e.g. 'tomorrow 11am', 'this evening'"}},
            required=["when"],
        ),
    ]
)


async def _tag_shopify_order(client_cfg: dict, order_id: str, tag: str, note: str = ""):
    """Write the outcome back to the real Shopify order, if store is connected."""
    shop = client_cfg.get("shopify") or {}
    domain, token = shop.get("domain"), shop.get("access_token")
    if not (domain and token):
        return
    try:
        import aiohttp

        url = f"https://{domain}/admin/api/2024-10/orders/{order_id}.json"
        headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as r:
                current = (await r.json()).get("order", {})
            tags = ", ".join(filter(None, [current.get("tags", ""), tag]))
            body = {"order": {"id": int(order_id), "tags": tags}}
            if note:
                body["order"]["note"] = note
            async with session.put(url, headers=headers, json=body) as r:
                logger.info(f"Shopify order {order_id} tagged '{tag}' -> HTTP {r.status}")
    except Exception as e:
        logger.warning(f"Shopify writeback failed (local record kept): {e}")


def register_order_tools(llm, client_cfg: dict, task: dict):
    """Bind tool handlers to this specific call task and register them."""
    task_id, order_id = task["task_id"], task["order_id"]

    def record(outcome: str, **extra):
        update_task(task_id, status="done", outcome=outcome, **extra)
        update_order(order_id, status=outcome)
        log_event("tool", name=f"outcome:{outcome}", args=extra, result={"task": task_id})

    async def confirm_order(params: FunctionCallParams):
        notes = params.arguments.get("notes", "")
        record("confirmed", notes=notes)
        await _tag_shopify_order(client_cfg, order_id, "ai-confirmed", notes)
        await params.result_callback({"status": "order_confirmed"})

    async def cancel_order(params: FunctionCallParams):
        reason = params.arguments.get("reason", "")
        record("cancelled", notes=reason)
        await _tag_shopify_order(client_cfg, order_id, "ai-cancelled", reason)
        await params.result_callback({"status": "order_cancelled"})

    async def update_delivery_address(params: FunctionCallParams):
        addr = params.arguments["new_address"]
        update_order(order_id, address=addr)
        log_event("tool", name="update_delivery_address", args={"new_address": addr}, result={})
        await _tag_shopify_order(client_cfg, order_id, "ai-address-updated", f"New address: {addr}")
        await params.result_callback({"status": "address_updated", "address": addr})

    async def send_payment_link(params: FunctionCallParams):
        phone = params.arguments["phone"]
        # MVP: recorded, not actually sent (SMS gateway = paid). The link that
        # would be sent is the order's Shopify invoice/checkout URL.
        record("payment_link_sent", notes=f"link to {phone}")
        logger.info(f"[MOCK SMS] payment link for order {order_id} -> {phone}")
        await params.result_callback(
            {"status": "payment_link_sent", "note": "Tell the customer the SMS is on its way."}
        )

    async def schedule_callback(params: FunctionCallParams):
        when = params.arguments["when"]
        update_task(task_id, status="callback", outcome="callback", notes=when)
        await params.result_callback({"status": "callback_scheduled", "when": when})

    llm.register_function("confirm_order", confirm_order)
    llm.register_function("cancel_order", cancel_order)
    llm.register_function("update_delivery_address", update_delivery_address)
    llm.register_function("send_payment_link", send_payment_link)
    llm.register_function("schedule_callback", schedule_callback)


def build_outbound_prompt(client_cfg: dict, task: dict) -> str:
    """System prompt for an outbound order call."""
    order = get_order(task["order_id"]) or {}
    items = "; ".join(
        f"{i['quantity']}x {i['title']} (₹{i['price']})" for i in order.get("items", [])
    )
    languages = ", ".join(client_cfg.get("supported_languages", ["hi-IN", "en-IN"]))

    if task.get("flow") == "campaign":
        details = f"""CALL CONTEXT:
- Customer: {order.get('customer_name') or 'the customer'}
- Purpose of this call: {task['reason']}
Use the business knowledge from your persona/knowledge to answer questions."""
    else:
        details = f"""ORDER DETAILS (only source of truth — never invent anything):
- Order: {order.get('order_number', task['order_id'])}
- Customer: {order.get('customer_name') or 'the customer'}
- Items: {items or 'not listed'}
- Total: ₹{order.get('total', '?')} ({order.get('payment_gateway') or 'payment method unknown'})
- Payment status: {order.get('financial_status') or 'unknown'}
- Delivery address: {order.get('address') or 'not on file'}"""

    from src.config_loader import current_time_line, identity_rules, voice_gender_rules

    rules = (client_cfg.get("call_rules") or "").strip()
    rules_block = f"\nBUSINESS RULES — always obey these:\n{rules}\n" if rules else ""

    return f"""{client_cfg['persona']}

{voice_gender_rules(client_cfg)}

{identity_rules(client_cfg)}

{current_time_line()}
{rules_block}
You are making an OUTBOUND phone call to a customer of {client_cfg['business_name']}.

WHY YOU ARE CALLING: {task['reason']}.

{details}

HOW TO RUN THIS CALL:
1. Greet, say who you are and which business you're calling from, and confirm
   you are speaking with {order.get('customer_name') or 'the customer'}.
2. State why you're calling in one short sentence.
3. For COD confirmation: confirm they want the order, verify the address, then
   use confirm_order. For pending payment: help them pay (send_payment_link).
   For an abandoned cart: ask if they'd like to complete the purchase.
4. If they want to cancel, accept gracefully and use cancel_order.
5. If it's a bad time, use schedule_callback.
6. End politely and briefly. Never pressure the customer.

SPEAKING RULES (this is a voice call):
- One or two SHORT sentences per turn. No lists, no markdown, no emojis.
- NEVER write code, JSON, XML or function-call syntax in your reply text.
- Numbers and prices the way you would SAY them.
- Detect the customer's language and reply in it. Supported: {languages}.
  Mix Hindi-English naturally if they do.
- SOUND HUMAN: react before answering ("Achha...", "Ji bilkul"), use everyday
  spoken words not formal ones, add small pauses with commas and "...", vary
  your sentence openings, and confirm casually ("theek hai na?"). When looking
  something up, think aloud: "Ek second, main check karti hoon... haan."
"""
