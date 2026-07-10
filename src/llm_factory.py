"""Picks the LLM service for the voice pipeline based on LLM_PROVIDER.

- "groq" (default): free tier ~1000 req/day, fast — key from console.groq.com
- "google": Gemini — free tier is only ~20 req/day, fine for a quick test
- "anthropic": Claude, if you have a paid Anthropic key

The rest of the pipeline never knows which provider is running.
"""

import os

# gpt-oss-120b: native tool calling (llama-3.3 sometimes leaks tool calls as
# literal "<function=...>" text into replies, which then gets spoken).
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"


def create_llm():
    provider = os.environ.get("LLM_PROVIDER", "groq").lower()

    if provider == "groq":
        from pipecat.services.groq.llm import GroqLLMService

        return GroqLLMService(
            api_key=os.environ["GROQ_API_KEY"],
            settings=GroqLLMService.Settings(
                model=os.environ.get("LLM_MODEL", DEFAULT_GROQ_MODEL)
            ),
        )

    if provider == "google":
        from pipecat.services.google.llm import GoogleLLMService

        return GoogleLLMService(
            api_key=os.environ["GOOGLE_API_KEY"],
            settings=GoogleLLMService.Settings(
                model=os.environ.get("LLM_MODEL", "gemini-2.5-flash")
            ),
        )

    if provider == "anthropic":
        from pipecat.services.anthropic.llm import AnthropicLLMService

        return AnthropicLLMService(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            settings=AnthropicLLMService.Settings(
                model=os.environ.get("LLM_MODEL", "claude-sonnet-5")
            ),
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER '{provider}'. Use 'groq', 'google' or 'anthropic'."
    )
