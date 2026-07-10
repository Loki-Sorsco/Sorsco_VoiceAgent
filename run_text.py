"""Text-only chat with the hotel agent — for testing the brain without audio.

Works with whichever LLM_PROVIDER is set in .env (groq by default, or google).
Both expose OpenAI-compatible APIs, so one client handles them all.
Type in any language; the agent replies in the same language and calls the same
tools the voice bot uses.

Usage:  .venv\\Scripts\\python run_text.py
"""

import json
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

from src.config_loader import build_system_prompt, load_client
from src.tools import check_availability, notify_manager

# Windows consoles default to cp1252, which can't print Hindi/Tamil text.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(override=True)  # .env always wins over stale inherited env vars

PROVIDERS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "default_model": "openai/gpt-oss-120b",
        "key_url": "https://console.groq.com",
    },
    "google": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_env": "GOOGLE_API_KEY",
        "default_model": "gemini-2.5-flash-lite",
        "key_url": "https://aistudio.google.com",
    },
}

TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": (
                "Check how many rooms of a given type are free for a date range. "
                "Always use this before telling the caller about availability."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "room_type": {"type": "string", "enum": ["standard", "deluxe", "suite"]},
                    "check_in": {"type": "string", "description": "Check-in date, YYYY-MM-DD"},
                    "check_out": {"type": "string", "description": "Check-out date, YYYY-MM-DD"},
                },
                "required": ["room_type", "check_in", "check_out"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notify_manager",
            "description": (
                "Send a confirmed booking lead to the hotel manager. Only call AFTER "
                "the caller has confirmed name, phone number, room type and dates."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "guest_name": {"type": "string"},
                    "guest_phone": {"type": "string"},
                    "room_type": {"type": "string", "enum": ["standard", "deluxe", "suite"]},
                    "check_in": {"type": "string", "description": "YYYY-MM-DD"},
                    "check_out": {"type": "string", "description": "YYYY-MM-DD"},
                    "num_guests": {"type": "integer"},
                    "notes": {"type": "string"},
                },
                "required": ["guest_name", "guest_phone", "room_type", "check_in", "check_out"],
            },
        },
    },
]

TOOL_FUNCS = {
    "check_availability": check_availability,
    "notify_manager": notify_manager,
}


def main():
    provider_name = os.environ.get("LLM_PROVIDER", "groq").lower()
    provider = PROVIDERS.get(provider_name)
    if provider is None:
        raise SystemExit(f"run_text.py supports providers: {list(PROVIDERS)}")

    api_key = os.environ.get(provider["key_env"], "")
    if not api_key or api_key == "...":
        raise SystemExit(
            f"\n{provider['key_env']} is not set in .env.\n"
            f"Get a FREE key at {provider['key_url']} and add it to .env.\n"
        )

    model = os.environ.get("LLM_MODEL", provider["default_model"])
    client = OpenAI(api_key=api_key, base_url=provider["base_url"])

    client_cfg = load_client(os.environ.get("CLIENT_ID", "hotel_sunrise"))
    messages = [{"role": "system", "content": build_system_prompt(client_cfg)}]

    print(f"\n--- {client_cfg['business_name']} | agent: {client_cfg['agent_name']}"
          f" | {provider_name}:{model} ---")
    print("Type in Hindi / English / Hinglish / Tamil... ('quit' to exit)\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input or user_input.lower() in ("quit", "exit"):
            break

        messages.append({"role": "user", "content": user_input})

        # Loop because the model may chain several tool calls before replying.
        while True:
            response = client.chat.completions.create(
                model=model, messages=messages, tools=TOOL_DEFS
            )
            msg = response.choices[0].message
            messages.append(msg.model_dump(exclude_none=True))

            if not msg.tool_calls:
                break
            for call in msg.tool_calls:
                args = json.loads(call.function.arguments)
                print(f"  [tool] {call.function.name}({json.dumps(args, ensure_ascii=False)})")
                result = TOOL_FUNCS[call.function.name](**args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        print(f"{client_cfg['agent_name']}: {msg.content}\n")


if __name__ == "__main__":
    main()
