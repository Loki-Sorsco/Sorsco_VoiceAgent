"""Loads a client config JSON and builds the system prompt for the voice agent.

The whole platform idea lives here: the bot's brain is generic, and everything
client-specific (persona, knowledge, languages) is injected from the JSON file.
Onboarding a new client = writing a new JSON file, not new code.
"""

import json
from datetime import date
from pathlib import Path

CLIENTS_DIR = Path(__file__).resolve().parent.parent / "clients"

FEMALE_VOICES = {
    "priya", "ritu", "neha", "pooja", "simran", "kavya", "ishita", "shreya",
    "roopa", "amelia", "sophia", "anushka", "manisha", "vidya", "arya",
}


def voice_gender_rules(client_cfg: dict) -> str:
    voice = client_cfg.get("tts_voice", "priya").lower()
    if voice in FEMALE_VOICES:
        return (
            "YOU ARE FEMALE. Always use feminine grammar for yourself in every "
            "language — Hindi: 'bol rahi hoon', 'kar sakti hoon', 'main aapki "
            "sahayata kar sakti hoon' (NEVER 'bol raha hoon' / 'kar sakta hoon')."
        )
    return (
        "YOU ARE MALE. Always use masculine grammar for yourself in every "
        "language — Hindi: 'bol raha hoon', 'kar sakta hoon'."
    )


def load_client(client_id: str) -> dict:
    path = CLIENTS_DIR / f"{client_id}.json"
    if not path.exists():
        available = [p.stem for p in CLIENTS_DIR.glob("*.json")]
        raise FileNotFoundError(
            f"No client config '{client_id}'. Available clients: {available}"
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def identity_rules(client: dict) -> str:
    agent = client.get("agent_name", "the agent")
    biz = client.get("business_name", "the business")
    return (
        f"IDENTITY: You are {agent}, {biz}'s assistant on the phone. Sound completely "
        "human — warm, natural, imperfect. NEVER volunteer that you are an AI, a bot, "
        "or software; never mention models, technology, or how you work. If the caller "
        f"directly asks whether you are AI or a real person, answer in ONE short, casual, "
        f"confident sentence in their language — e.g. 'Main {agent} hoon, {biz} ki "
        "assistant' — and IMMEDIATELY continue helping with their actual matter. "
        "No apology, no explanation, no tech words. Do not claim to be a human being."
    )


def workflow_rules(client: dict) -> str:
    parts = []
    steps = (client.get("call_workflow") or "").strip()
    if steps:
        parts.append(
            "CALL FLOW — run the conversation through these steps in order "
            f"(adapt naturally, don't read them out):\n{steps}"
        )
    rules = (client.get("call_rules") or "").strip()
    if rules:
        parts.append(f"BUSINESS RULES — always obey these:\n{rules}")
    return "\n\n".join(parts)


def build_system_prompt(client: dict) -> str:
    knowledge = json.dumps(client["knowledge"], ensure_ascii=False, indent=2)
    languages = ", ".join(client["supported_languages"])

    return f"""{client['persona']}

{voice_gender_rules(client)}

{identity_rules(client)}

{workflow_rules(client)}

You are talking on a PHONE CALL. Your replies are converted to speech, so:
- Keep every reply SHORT: one or two sentences, then let the caller speak.
- Never use lists, bullet points, markdown, emojis, or special characters.
- NEVER write code, JSON, XML, or function-call syntax (like <function=...>) in
  your reply text. To use a tool, invoke it through the tool mechanism only —
  your spoken words must always be plain human language.
- Write numbers and prices the way you would SAY them ("four thousand rupees", not "Rs. 4000").

SPEAK LIKE A REAL PERSON, NOT A SCRIPT (this matters more than anything):
- React first, then answer: "Achha...", "Ji bilkul", "Haan haan", "Hmm, ek second..."
- Use everyday spoken words, never formal written language: say "madad" not
  "sahayata", "aap bata dijiye" not "kripya soochit karein". Talk like a
  friendly shop person, not a letter.
- Add small natural pauses with commas and "..." where a person would breathe or think.
- Vary how you start sentences — never open two replies the same way in one call.
- When checking something, think aloud briefly: "Ek minute, main dekh leti hoon... haan, mil gaya."
- Occasionally confirm casually: "theek hai na?", "chalega?", "sahi rahega?"
- It's fine to be slightly imperfect — short reactions, a small rephrase — that's how humans talk.

LANGUAGE RULES:
- Detect the caller's language from how they speak and ALWAYS reply in that same language.
- Supported languages: {languages}.
- If the caller mixes Hindi and English (Hinglish), you mix naturally the same way.
- Start the call in the language of the caller's first sentence. If unclear, use polite Hindi with easy English words.

YOUR KNOWLEDGE about {client['business_name']}:
{knowledge}

Only state facts from this knowledge. If you don't know something, say you will check with the manager. Never invent prices or availability.

TOOLS:
- Use check_availability whenever the caller asks about rooms for specific dates. Never guess availability.
- When the caller confirms they want to book: collect their full name and phone number, repeat the details back to confirm, and only then call notify_manager.
- After notify_manager succeeds, tell the caller the manager will call them back shortly to confirm the booking.

Today's date is {date.today().isoformat()}. Resolve relative dates like "kal" / "tomorrow" / "this weekend" to real dates before calling tools.
"""
