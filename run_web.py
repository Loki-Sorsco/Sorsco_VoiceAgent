"""Browser call: talk to the agent from any browser tab — no installs.

Starts a web server (default http://localhost:7860) with a built-in call UI.
Open it, click Connect, allow the microphone, and talk. Share beyond your
machine with a tunnel, e.g.:  cloudflared tunnel --url http://localhost:7860

Usage:  .venv\\Scripts\\python run_web.py -t webrtc
        CLIENT_ID in .env picks which client the agent represents.
"""

import os

from dotenv import load_dotenv

load_dotenv(override=True)

from pipecat.runner.types import RunnerArguments  # noqa: E402
from pipecat.runner.utils import create_transport  # noqa: E402
from pipecat.transports.base_transport import TransportParams  # noqa: E402

from src.bot import run_bot  # noqa: E402
from src.config_loader import load_client  # noqa: E402

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
}


async def bot(runner_args: RunnerArguments):
    """Called by the Pipecat runner for every browser connection."""
    transport = await create_transport(runner_args, transport_params)
    client_cfg = load_client(os.environ.get("CLIENT_ID", "hotel_sunrise"))
    await run_bot(transport, client_cfg, handle_sigint=False)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
