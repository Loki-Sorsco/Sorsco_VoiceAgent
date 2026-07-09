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

from src.call_events import log_event, reset_events
from src.config_loader import build_system_prompt
from src.llm_factory import create_llm
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


async def _handle_check_availability(params: FunctionCallParams):
    result = check_availability(**params.arguments)
    log_event("tool", name="check_availability", args=params.arguments, result=result)
    await params.result_callback(result)


async def _handle_notify_manager(params: FunctionCallParams):
    result = notify_manager(**params.arguments)
    log_event("tool", name="notify_manager", args=params.arguments, result=result)
    await params.result_callback(result)


async def run_bot(transport: BaseTransport, client_cfg: dict, handle_sigint: bool = True):
    """Run one call session on the given transport."""
    stt = SarvamSTTService(api_key=os.environ["SARVAM_API_KEY"])

    tts = SarvamTTSService(
        api_key=os.environ["SARVAM_API_KEY"],
        settings=SarvamTTSService.Settings(
            model="bulbul:v3",
            voice=client_cfg.get("tts_voice", "priya"),
            language=client_cfg.get("default_language", "hi-IN"),
        ),
    )

    llm = create_llm()
    llm.register_function("check_availability", _handle_check_availability)
    llm.register_function("notify_manager", _handle_notify_manager)

    context = LLMContext(
        messages=[{"role": "system", "content": build_system_prompt(client_cfg)}],
        tools=TOOL_SCHEMAS,
    )
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
    log_event("call_started", client=client_cfg["business_name"], agent=client_cfg["agent_name"])

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

    worker = PipelineWorker(pipeline, params=PipelineParams(enable_metrics=True))

    # Greet the caller as soon as the session starts.
    context.add_message(
        {
            "role": "developer",
            "content": (
                "The call just connected. Greet the caller warmly in one short sentence "
                f"as {client_cfg['agent_name']} from {client_cfg['business_name']} and "
                "ask how you can help. Use polite Hindi with easy English words."
            ),
        }
    )
    await worker.queue_frames([LLMRunFrame()])

    logger.info(f"Voice agent ready for client '{client_cfg['client_id']}'. Speak now.")
    runner = PipelineRunner(handle_sigint=handle_sigint)
    await runner.add_workers(worker)
    try:
        await runner.run()
    finally:
        log_event("call_ended")
