"""Universal agent tools — the per-client tool belt, built from config.

Every client's agent gets transfer_to_human and capture_lead. The rest switch
on automatically when the matching connector is configured in the dashboard:

  book_appointment / get_available_slots   appointments enabled or Calendly
  send_payment_link                        Razorpay or Stripe connected
  send_sms                                 Twilio SMS configured
  lookup_customer                          generic_rest lookup_path set

build_platform_tools() returns (schemas, handlers) that bot.py merges into the
LLM's tool set; handlers close over the call context (client, caller phone,
call sid) so the LLM never sees or supplies identifiers it could get wrong.

Captured leads/appointments land in data/platform/*.jsonl, fan out to the
configured connectors (Sheets row, generic REST save) and fire webhooks — the
"bidirectional sync" path: events in via /webhooks/*, data out via these.
"""

import asyncio
from datetime import datetime

from loguru import logger

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.services.llm_service import FunctionCallParams

from src.call_events import log_event, read_events
from src.platform import connectors
from src.platform.handoff import create_handoff
from src.platform.records import APPOINTMENTS_FILE, LEADS_FILE, append_jsonl
from src.platform.webhooks_out import emit


# ------------------------------------------------------------ tool builders


def build_platform_tools(
    client_cfg: dict,
    caller_phone: str = "",
    call_sid: str | None = None,
) -> tuple[list[FunctionSchema], dict]:
    """Schemas + handlers for every tool this client's config enables."""
    schemas: list[FunctionSchema] = []
    handlers: dict = {}

    def add(schema: FunctionSchema, handler):
        schemas.append(schema)
        handlers[schema.name] = handler

    # ---- transfer_to_human: always on --------------------------------------
    async def _transfer(params: FunctionCallParams):
        reason = params.arguments.get("reason", "Caller asked for a human")
        record = await asyncio.to_thread(
            create_handoff,
            client_cfg,
            reason,
            read_events(),
            params.arguments.get("customer_name", ""),
            params.arguments.get("customer_phone", "") or caller_phone,
            call_sid,
        )
        log_event("handoff", handoff_id=record["handoff_id"], reason=reason)
        result = {
            "status": "handoff_created",
            "note": (
                "A staff member has been alerted with the full conversation so far. "
                "Tell the caller a colleague will be with them right away; keep them "
                "company politely until then (or promise an immediate callback if "
                "no one joins)."
            ),
        }
        await params.result_callback(result)

    add(
        FunctionSchema(
            name="transfer_to_human",
            description=(
                "Hand this call to a human staff member. Use when the caller asks for "
                "a person, is upset, or you cannot help after two honest attempts. "
                "Collect their name first if you don't have it."
            ),
            properties={
                "reason": {"type": "string", "description": "Why the handoff is needed, one sentence"},
                "customer_name": {"type": "string"},
                "customer_phone": {"type": "string"},
            },
            required=["reason"],
        ),
        _transfer,
    )

    # ---- capture_lead: always on, fields are per-client --------------------
    capture_fields = client_cfg.get("data_capture") or [
        {"key": "name", "label": "Full name", "required": True},
        {"key": "phone", "label": "Phone number", "required": True},
        {"key": "interest", "label": "What they want / are interested in", "required": True},
        {"key": "notes", "label": "Anything else important"},
    ]
    props = {
        f["key"]: {"type": "string", "description": f.get("label", f["key"])}
        for f in capture_fields
    }
    required = [f["key"] for f in capture_fields if f.get("required")]

    async def _capture(params: FunctionCallParams):
        lead = {
            "client_id": client_cfg["client_id"],
            "captured": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **{k: str(v) for k, v in params.arguments.items()},
        }
        lead.setdefault("phone", caller_phone)
        append_jsonl(LEADS_FILE, lead)
        log_event("tool", name="capture_lead", args=params.arguments, result={"saved": True})
        emit("lead.captured", client_cfg, lead)
        # Fan out to connected systems; failures never break the call.
        if connectors.is_configured(client_cfg, "google_sheets"):
            try:
                await connectors.sheets_append_row(client_cfg, lead)
            except Exception as e:
                logger.warning(f"Sheets lead sync failed: {e}")
        if connectors.is_configured(client_cfg, "generic_rest"):
            try:
                await connectors.rest_save(client_cfg, {"type": "lead", **lead})
            except Exception as e:
                logger.warning(f"REST lead sync failed: {e}")
        await params.result_callback(
            {"status": "saved", "note": "Details noted. Confirm them back to the caller."}
        )

    add(
        FunctionSchema(
            name="capture_lead",
            description=(
                "Save the caller's details/enquiry as a structured record for the team. "
                "Call once you have the required fields; repeat details back first."
            ),
            properties=props,
            required=required,
        ),
        _capture,
    )

    # ---- appointments ------------------------------------------------------
    appts_on = (client_cfg.get("appointments") or {}).get("enabled") or connectors.is_configured(
        client_cfg, "calendly"
    )
    if appts_on:

        async def _book(params: FunctionCallParams):
            appt = {
                "client_id": client_cfg["client_id"],
                "booked": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "requested",
                **{k: str(v) for k, v in params.arguments.items()},
            }
            appt.setdefault("phone", caller_phone)
            append_jsonl(APPOINTMENTS_FILE, appt)
            log_event("tool", name="book_appointment", args=params.arguments, result={"saved": True})
            emit("appointment.booked", client_cfg, appt)
            note = "Appointment request recorded — the team will confirm."
            if connectors.is_configured(client_cfg, "generic_rest"):
                try:
                    saved = await connectors.rest_save(client_cfg, {"type": "appointment", **appt})
                    if saved.get("saved"):
                        note = "Appointment saved in the booking system."
                except Exception as e:
                    logger.warning(f"REST appointment sync failed: {e}")
            link = connectors.connector_cfg(client_cfg, "calendly").get("scheduling_link", "")
            if link and appt.get("phone") and connectors.is_configured(client_cfg, "twilio_sms"):
                try:
                    await connectors.send_sms(
                        client_cfg, appt["phone"],
                        f"{client_cfg['business_name']}: confirm your appointment here: {link}",
                    )
                    note += " A booking link was also texted to them."
                except Exception as e:
                    logger.warning(f"Appointment SMS failed: {e}")
            await params.result_callback({"status": "booked", "note": note})

        add(
            FunctionSchema(
                name="book_appointment",
                description=(
                    "Book/request an appointment for the caller. Only call after "
                    "confirming name, phone, service and preferred date-time back to them."
                ),
                properties={
                    "name": {"type": "string"},
                    "phone": {"type": "string"},
                    "service": {"type": "string", "description": "What the appointment is for"},
                    "datetime_preferred": {"type": "string", "description": "YYYY-MM-DD HH:MM, resolve relative dates first"},
                    "notes": {"type": "string"},
                },
                required=["name", "phone", "service", "datetime_preferred"],
            ),
            _book,
        )

    if connectors.is_configured(client_cfg, "calendly"):

        async def _slots(params: FunctionCallParams):
            result = await connectors.calendly_available_times(
                client_cfg, int(params.arguments.get("days_ahead", 7) or 7)
            )
            log_event("tool", name="get_available_slots", args=params.arguments, result=result)
            await params.result_callback(result)

        add(
            FunctionSchema(
                name="get_available_slots",
                description="Fetch real open appointment slots from the calendar. Use before offering times.",
                properties={"days_ahead": {"type": "integer", "description": "How many days to look ahead, max 7"}},
                required=[],
            ),
            _slots,
        )

    # ---- payments ----------------------------------------------------------
    razorpay_on = connectors.is_configured(client_cfg, "razorpay")
    stripe_on = connectors.is_configured(client_cfg, "stripe")
    if razorpay_on or stripe_on:

        async def _pay_link(params: FunctionCallParams):
            amount = float(params.arguments.get("amount", 0) or 0)
            currency = params.arguments.get("currency") or "INR"
            description = params.arguments.get("description", "")
            phone = params.arguments.get("customer_phone", "") or caller_phone
            if amount <= 0:
                await params.result_callback({"error": "Amount must be positive"})
                return
            if razorpay_on:
                result = await connectors.razorpay_payment_link(
                    client_cfg, amount, currency, description,
                    params.arguments.get("customer_name", ""), phone,
                )
            else:
                result = await connectors.stripe_payment_link(
                    client_cfg, amount, currency, description
                )
            log_event("tool", name="send_payment_link", args=params.arguments, result=result)
            if result.get("url"):
                emit("payment_link.sent", client_cfg, {**result, "customer_phone": phone})
                if not result.get("sms_sent") and phone and connectors.is_configured(
                    client_cfg, "twilio_sms"
                ):
                    sms = await connectors.send_sms(
                        client_cfg, phone,
                        f"{client_cfg['business_name']}: complete your payment here: {result['url']}",
                    )
                    result["sms_sent"] = bool(sms.get("sent"))
                result["note"] = (
                    "Payment link sent to their phone."
                    if result.get("sms_sent")
                    else "Link created — read out that it's being sent, or offer to text it."
                )
            await params.result_callback(result)

        add(
            FunctionSchema(
                name="send_payment_link",
                description=(
                    "Create a payment link for a specific amount and text it to the "
                    "caller. Confirm the amount out loud before calling this."
                ),
                properties={
                    "amount": {"type": "number", "description": "Amount in major units (e.g. 1499.00)"},
                    "currency": {"type": "string", "description": "e.g. INR, USD"},
                    "description": {"type": "string", "description": "What the payment is for"},
                    "customer_name": {"type": "string"},
                    "customer_phone": {"type": "string", "description": "Only if different from the caller"},
                },
                required=["amount", "description"],
            ),
            _pay_link,
        )

    # ---- SMS ---------------------------------------------------------------
    if connectors.is_configured(client_cfg, "twilio_sms"):

        async def _sms(params: FunctionCallParams):
            to = params.arguments.get("phone", "") or caller_phone
            if not to:
                await params.result_callback(
                    {"error": "No phone number known — ask the caller for it"}
                )
                return
            result = await connectors.send_sms(client_cfg, to, params.arguments.get("message", ""))
            log_event("tool", name="send_sms", args=params.arguments, result=result)
            await params.result_callback(result)

        add(
            FunctionSchema(
                name="send_sms",
                description="Text the caller a short message (address, link, confirmation).",
                properties={
                    "message": {"type": "string"},
                    "phone": {"type": "string", "description": "Only if different from the caller"},
                },
                required=["message"],
            ),
            _sms,
        )

    # ---- customer lookup ---------------------------------------------------
    if connectors.connector_cfg(client_cfg, "generic_rest").get("lookup_path"):

        async def _lookup(params: FunctionCallParams):
            result = await connectors.rest_lookup(client_cfg, params.arguments.get("query", ""))
            log_event("tool", name="lookup_customer", args=params.arguments, result=result)
            await params.result_callback(result)

        add(
            FunctionSchema(
                name="lookup_customer",
                description=(
                    "Look up a customer/record in the business's own system by phone "
                    "number, name or ID. Use before answering account-specific questions."
                ),
                properties={"query": {"type": "string", "description": "Phone, name or record ID"}},
                required=["query"],
            ),
            _lookup,
        )

    return schemas, handlers


def platform_tools_prompt(schemas: list[FunctionSchema]) -> str:
    """One prompt block telling the agent what its enabled tools are for."""
    if not schemas:
        return ""
    hints = {
        "transfer_to_human": "If the caller wants a human or you are stuck, use transfer_to_human — never just refuse.",
        "capture_lead": "Whenever a caller shows interest or leaves details, save them with capture_lead before the call ends.",
        "book_appointment": "Book appointments with book_appointment after confirming the details back.",
        "get_available_slots": "Always check get_available_slots before offering appointment times.",
        "send_payment_link": "To take a payment, confirm the amount and use send_payment_link.",
        "send_sms": "You can text the caller with send_sms when a link or address is easier to read than to hear.",
        "lookup_customer": "For account/order/record questions, use lookup_customer first instead of guessing.",
    }
    lines = [hints[s.name] for s in schemas if s.name in hints]
    return "PLATFORM ACTIONS:\n- " + "\n- ".join(lines) if lines else ""
