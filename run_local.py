"""Talk to the voice agent using your microphone and speakers.

Usage:  .venv\\Scripts\\python run_local.py [--client CLIENT_ID]

Needs GROQ_API_KEY and SARVAM_API_KEY in .env.
Swap LocalAudioTransport for a Twilio/Exotel transport to put this on a real
phone number — src/bot.py stays unchanged.
"""

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

# Windows consoles default to cp1252, which can't print Hindi/Tamil text.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(override=True)  # .env always wins over stale inherited env vars

from pipecat.transports.local.audio import (  # noqa: E402
    LocalAudioTransport,
    LocalAudioTransportParams,
)

from src.bot import run_bot  # noqa: E402
from src.config_loader import load_client  # noqa: E402


async def main():
    provider = os.environ.get("LLM_PROVIDER", "groq")
    llm_key = {
        "groq": "GROQ_API_KEY",
        "google": "GOOGLE_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }.get(provider, "GROQ_API_KEY")
    missing = [k for k in (llm_key, "SARVAM_API_KEY") if not os.environ.get(k)]
    if missing:
        raise SystemExit(
            f"\nMissing keys in .env: {', '.join(missing)}\n"
            "GROQ_API_KEY: free at https://console.groq.com\n"
            "SARVAM_API_KEY: free credits at https://dashboard.sarvam.ai\n"
        )

    parser = argparse.ArgumentParser()
    parser.add_argument("--client", default=os.environ.get("CLIENT_ID", "hotel_sunrise"))
    args = parser.parse_args()
    client_cfg = load_client(args.client)

    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        )
    )

    await run_bot(transport, client_cfg)


if __name__ == "__main__":
    asyncio.run(main())
