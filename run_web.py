"""Browser call: talk to the agent from any browser tab — no installs.

Starts a web server (default http://localhost:7860) with a built-in call UI.
Open it, click Connect, allow the microphone, and talk. Share beyond your
machine with a tunnel, e.g.:  cloudflared tunnel --url http://localhost:7860

Usage:  .venv\\Scripts\\python run_web.py -t webrtc
        CLIENT_ID in .env picks which client the agent represents.
"""

import json
import os

from dotenv import load_dotenv

load_dotenv(override=True)

from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402
from starlette.responses import Response  # noqa: E402

from pipecat.runner.types import RunnerArguments, WebSocketRunnerArguments  # noqa: E402
from pipecat.runner.utils import create_transport  # noqa: E402
from pipecat.serializers.protobuf import ProtobufFrameSerializer  # noqa: E402
from pipecat.transports.base_transport import TransportParams  # noqa: E402
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams  # noqa: E402

from src.admin import get_active_client_id, register_admin  # noqa: E402
from src.bot import run_bot  # noqa: E402
from src.config_loader import load_client  # noqa: E402
from src.store import get_active_task, set_active_task  # noqa: E402


class RewritePublicWsUrl(BaseHTTPMiddleware):
    """Fix the wsUrl the runner returns from POST /start.

    Behind a reverse proxy (Dokploy/Traefik) the runner advertises its bind
    address (wss://0.0.0.0:7860/ws-client), which the browser can't use.
    Rewrite it to the host the request actually came through.
    """

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path != "/start":
            return response
        body = b"".join([chunk async for chunk in response.body_iterator])
        try:
            data = json.loads(body)
            if isinstance(data, dict) and data.get("wsUrl"):
                host = request.headers.get("x-forwarded-host") or request.headers.get("host")
                proto = request.headers.get("x-forwarded-proto", request.url.scheme)
                scheme = "wss" if proto == "https" else "ws"
                path = "/" + data["wsUrl"].split("://", 1)[-1].split("/", 1)[-1]
                data["wsUrl"] = f"{scheme}://{host}{path}"
                body = json.dumps(data).encode()
        except (json.JSONDecodeError, IndexError, KeyError):
            pass
        return Response(
            content=body,
            status_code=response.status_code,
            media_type=response.headers.get("content-type"),
        )

def _daily_params():
    # Imported lazily: daily-python has no Windows wheel; only needed on the
    # server, where Daily's hosted infra carries the audio (works from inside
    # Docker because the container only makes outbound connections).
    from pipecat.transports.daily.transport import DailyParams

    return DailyParams(audio_in_enabled=True, audio_out_enabled=True)


transport_params = {
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
    "daily": _daily_params,
    # Plain WebSocket: audio rides the same HTTPS/TCP path as the web page, so
    # it works through any reverse proxy / Docker network. This is the reliable
    # transport for the deployed server (select "WebSocket" in the playground).
    "websocket": lambda: FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        add_wav_header=False,
        serializer=ProtobufFrameSerializer(),
    ),
    # Real phone calls (Twilio media streams). The serializer is set
    # automatically by create_transport from the parsed handshake.
    "twilio": lambda: FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
    "exotel": lambda: FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
}


async def bot(runner_args: RunnerArguments):
    """Called by the Pipecat runner for every browser or phone connection."""
    transport = await create_transport(runner_args, transport_params)

    # Real phone call (Twilio media stream): the TwiML we sent when dialing
    # carries the task_id, so this call IS that outbound order/campaign call.
    if isinstance(runner_args, WebSocketRunnerArguments):
        call_data = getattr(runner_args, "call_data", None)
        body = (call_data.get("body") if isinstance(call_data, dict)
                else getattr(call_data, "body", None)) or {}
        # Twilio CallSid (lets the platform live-transfer this call on handoff).
        call_sid = (call_data.get("call_id") if isinstance(call_data, dict)
                    else getattr(call_data, "call_id", None))
        task_id = body.get("task_id")
        if task_id:
            from src.store import get_task

            call_task = get_task(task_id)
            if call_task:
                client_cfg = load_client(call_task["client_id"])
                await run_bot(
                    transport, client_cfg, handle_sigint=False,
                    call_task=call_task, telephony=True, call_sid=call_sid,
                )
                return
        # Inbound phone call with no task: normal receptionist, phone audio.
        if getattr(runner_args, "transport_type", "websocket") != "websocket":
            from_number = (call_data.get("from_number") if isinstance(call_data, dict)
                           else getattr(call_data, "from_number", None))
            client_cfg = load_client(
                get_active_client_id(default=os.environ.get("CLIENT_ID", "hotel_sunrise"))
            )
            await run_bot(transport, client_cfg, handle_sigint=False,
                          telephony=True, caller_phone=from_number, call_sid=call_sid)
            return

    # If an order call was "taken" in /admin, this browser connection becomes
    # that outbound call (demo mode: the browser user plays the customer).
    call_task = get_active_task()
    if call_task and call_task.get("status") == "queued":
        set_active_task(None)
        client_cfg = load_client(call_task["client_id"])
        await run_bot(transport, client_cfg, handle_sigint=False, call_task=call_task)
        return

    # Active client is switchable at runtime from /admin (falls back to env).
    client_cfg = load_client(
        get_active_client_id(default=os.environ.get("CLIENT_ID", "hotel_sunrise"))
    )
    await run_bot(transport, client_cfg, handle_sigint=False)


if __name__ == "__main__":
    from pipecat.runner import run as _runner

    from src.platform.platform_api import register_platform

    _runner.app.add_middleware(RewritePublicWsUrl)
    register_admin(_runner.app)
    register_platform(_runner.app)  # /platform dashboard, /v1 API, /widget.js
    _runner.main()
