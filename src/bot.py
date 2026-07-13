"""The voice agent pipeline: STT -> LLM -> TTS, with barge-in and tool calling.

This is the generic "brain + voice" of the platform. Everything client-specific
comes from the client config JSON; everything transport-specific (local mic,
Twilio, Exotel...) is passed in, so the same pipeline serves a demo on your
laptop and a real phone call.
"""

import os

from loguru import logger

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transports.base_transport import BaseTransport

from src.call_events import append_history, log_event, read_events, reset_events
from src.config_loader import build_system_prompt
from src.llm_factory import create_llm
from src.order_tools import ORDER_TOOLS, build_outbound_prompt, register_order_tools
from src.store import get_task, update_task
from src.tools import check_availability, notify_manager

TOOL_SCHEMAS = ToolsSchema(
    standard_tools=[
        FunctionSchema(
            name="check_availability",
            description=(
                "Check how many rooms of a given type are free for a date range. "
                "Always use this before telling the caller about availability."
            ),
            properties={
                "room_type": {"type": "string", "enum": ["standard", "deluxe", "suite"]},
                "check_in": {"type": "string", "description": "Check-in date, YYYY-MM-DD"},
                "check_out": {"type": "string", "description": "Check-out date, YYYY-MM-DD"},
            },
            required=["room_type", "check_in", "check_out"],
        ),
        FunctionSchema(
            name="notify_manager",
            description=(
                "Send a confirmed booking lead to the hotel manager. Only call AFTER "
                "the caller has confirmed name, phone number, room type and dates."
            ),
            properties={
                "guest_name": {"type": "string"},
                "guest_phone": {"type": "string"},
                "room_type": {"type": "string", "enum": ["standard", "deluxe", "suite"]},
                "check_in": {"type": "string", "description": "YYYY-MM-DD"},
                "check_out": {"type": "string", "description": "YYYY-MM-DD"},
                "num_guests": {"type": "integer"},
                "notes": {"type": "string", "description": "Any special requests"},
            },
            required=["guest_name", "guest_phone", "room_type", "check_in", "check_out"],
        ),
    ]
)


# Codes Sarvam's streaming STT accepts for the language parameter.
_SARVAM_STT_CODES = {
    "hi-IN", "bn-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN", "pa-IN", "ta-IN",
    "te-IN", "en-IN", "gu-IN", "as-IN", "ur-IN", "ne-IN",
}


def _stt_language(client_cfg: dict):
    """Sarvam language code to lock transcription to, or None for auto-detect.

    Sarvam expects its own region codes ('hi-IN'); passing anything else kills
    the STT stream mid-call (the 'agent goes deaf' bug).
    """
    if client_cfg.get("stt_language", "locked") == "auto":
        return None
    code = client_cfg.get("default_language", "hi-IN")
    return code if code in _SARVAM_STT_CODES else None


async def _handle_check_availability(params: FunctionCallParams):
    result = check_availability(**params.arguments)
    log_event("tool", name="check_availability", args=params.arguments, result=result)
    await params.result_callback(result)


async def _handle_notify_manager(params: FunctionCallParams):
    result = notify_manager(**params.arguments)
    log_event("tool", name="notify_manager", args=params.arguments, result=result)
    await params.result_callback(result)


async def run_bot(
    transport: BaseTransport,
    client_cfg: dict,
    handle_sigint: bool = True,
    call_task: dict | None = None,
    telephony: bool = False,
    caller_phone: str | None = None,
):
    """Run one call session on the given transport.

    call_task: an outbound order-call task from the call queue (COD confirm,
    pending payment, abandoned cart). None = normal inbound receptionist call.
    telephony: True for real phone lines (8 kHz audio).
    caller_phone: the customer's number (for cross-call memory), if known.
    """
    phone = caller_phone or (call_task or {}).get("customer_phone", "")
    stt = SarvamSTTService(
        api_key=os.environ["SARVAM_API_KEY"],
        settings=SarvamSTTService.Settings(
            model="saaras:v3",
            # Lock transcription to the agent's language: auto-detect on 8kHz
            # phone audio misfires into wrong scripts (Hindi heard as Odia).
            # Set "stt_language": "auto" in the client JSON to re-enable
            # auto-detection for genuinely multilingual lines.
            language=_stt_language(client_cfg),
        ),
    )

    tts = SarvamTTSService(
        api_key=os.environ["SARVAM_API_KEY"],
        settings=SarvamTTSService.Settings(
            model="bulbul:v3",
            voice=client_cfg.get("tts_voice", "priya"),
            language=client_cfg.get("default_language", "hi-IN"),
            # Natural speed by default; per-client override via "speech_pace"
            # (e.g. 0.9 slower, 1.1 brisker).
            pace=float(client_cfg.get("speech_pace", 1.0)),
        ),
    )

    llm = create_llm()
    if call_task:
        register_order_tools(llm, client_cfg, call_task)
        system_prompt = build_outbound_prompt(client_cfg, call_task)
        tools = ORDER_TOOLS
        update_task(call_task["task_id"], status="in_progress")
    else:
        llm.register_function("check_availability", _handle_check_availability)
        llm.register_function("notify_manager", _handle_notify_manager)
        system_prompt = build_system_prompt(client_cfg)
        tools = TOOL_SCHEMAS

    # Cross-call memory: if we've spoken with this number before, give the
    # agent a short recap so it treats them as a returning customer.
    messages = [{"role": "system", "content": system_prompt}]
    if phone:
        from src.memory import memory_note

        note = memory_note(phone, (call_task or {}).get("customer_name", ""))
        if note:
            messages.append({"role": "system", "content": note})

    context = LLMContext(messages=messages, tools=tools)
    # Slightly stricter than the defaults to resist speaker echo, but low
    # enough that a quiet microphone still triggers turns. min_volume is the
    # sensitive knob: too high (>0.7) and quiet mics never get a reply.
    vad = SileroVADAnalyzer(
        params=VADParams(confidence=0.75, min_volume=0.5, start_secs=0.3)
    )
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=vad),
    )

    # Live transcript -> dashboard call view
    reset_events()
    log_event(
        "call_started",
        client=client_cfg["business_name"],
        agent=client_cfg["agent_name"],
        order_call=call_task["reason"] if call_task else None,
    )

    @user_aggregator.event_handler("on_user_turn_message_added")
    async def on_user_message(aggregator, message):
        if message.content:
            log_event("user", text=message.content)

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def on_assistant_message(aggregator, message):
        if message.content:
            log_event("assistant", text=message.content, interrupted=message.interrupted)

    pipeline = Pipeline(
        [
            transport.input(),      # audio from mic / phone line
            stt,                    # Sarvam saaras:v3 — auto-detects language
            user_aggregator,        # collects the user's turn into the context
            llm,                    # Claude: conversation + tool calls
            tts,                    # Sarvam bulbul:v3 — Indian voices
            transport.output(),     # audio to speakers / phone line
            assistant_aggregator,   # records what the bot said
        ]
    )

    pipeline_params = (
        PipelineParams(
            enable_metrics=True, audio_in_sample_rate=8000, audio_out_sample_rate=8000
        )
        if telephony
        else PipelineParams(enable_metrics=True)
    )
    worker = PipelineWorker(pipeline, params=pipeline_params)

    # End the session the moment the caller hangs up / closes the page —
    # otherwise the pipeline lingers until idle-timeout and history/outcomes
    # are written minutes late. (LocalAudioTransport has no such event.)
    try:

        @transport.event_handler("on_client_disconnected")
        async def _on_client_disconnected(_transport, _client):
            logger.info("Client disconnected — ending call session")
            await worker.cancel()

        @transport.event_handler("on_session_timeout")
        async def _on_session_timeout(_transport, _client):
            logger.info("Session timeout — ending call session")
            await worker.cancel()

    except Exception:
        pass

    # Greet as soon as the session starts.
    if call_task:
        opening = (
            "The customer just answered the phone. Greet them politely as "
            f"{client_cfg['agent_name']} from {client_cfg['business_name']}, confirm "
            "you are speaking with the right person, and state in one short sentence "
            "why you are calling. Use polite Hindi with easy English words."
        )
    else:
        opening = (
            "The call just connected. Greet the caller warmly in one short sentence "
            f"as {client_cfg['agent_name']} from {client_cfg['business_name']} and "
            "ask how you can help. Use polite Hindi with easy English words."
        )
    context.add_message({"role": "developer", "content": opening})
    await worker.queue_frames([LLMRunFrame()])

    logger.info(f"Voice agent ready for client '{client_cfg['client_id']}'. Speak now.")
    runner = PipelineRunner(handle_sigint=handle_sigint)
    await runner.add_workers(worker)
    import time as _time

    started = _time.time()
    try:
        await runner.run()
    finally:
        log_event("call_ended")
        outcome = None
        if call_task:
            latest = get_task(call_task["task_id"])
            if latest and latest.get("status") == "in_progress":
                update_task(call_task["task_id"], status="done", outcome="no_outcome")
            latest = get_task(call_task["task_id"])
            outcome = (latest or {}).get("outcome")
        try:
            events = read_events()
            record = {
                "client_id": client_cfg["client_id"],
                "client": client_cfg["business_name"],
                "agent": client_cfg["agent_name"],
                "kind": call_task["flow"] if call_task else "inbound",
                "order_id": call_task["order_id"] if call_task else None,
                "customer_name": (call_task or {}).get("customer_name", ""),
                "customer_phone": phone,
                "outcome": outcome,
                "started": events[0]["time"] if events else "",
                "duration_s": int(_time.time() - started),
                "turns": sum(1 for e in events if e["type"] in ("user", "assistant")),
                "transcript": [
                    e for e in events if e["type"] in ("user", "assistant", "tool")
                ],
            }
            # Auto-analysis (summary/issue/category) — off the event loop.
            try:
                import asyncio

                from src.analysis import analyze_call

                record["analysis"] = await asyncio.wait_for(
                    asyncio.to_thread(analyze_call, record), timeout=30
                )
            except Exception as e:
                logger.warning(f"Post-call analysis skipped: {e}")
            append_history(record)
        except Exception as e:
            logger.warning(f"Could not write call history: {e}")
