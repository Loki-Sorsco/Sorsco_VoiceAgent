"""Voice engine selection per agent: premium Sarvam or the free stack.

- "sarvam" (default): Sarvam Saaras STT + Bulbul TTS — best Indic quality,
  consumes Sarvam credits.
- "free": Groq-hosted Whisper STT (free tier) + Kokoro TTS running on our own
  server (open source, unlimited, ₹0). Hindi voices: hf_alpha / hf_beta
  (female), hm_omega / hm_psi (male). Quality is a step below Sarvam but
  costs nothing — ideal for testing and cost-sensitive clients.

Set per agent in the console (Voice style) or "voice_engine" in the JSON.
"""

import os

from loguru import logger

KOKORO_VOICES = {"hf_alpha", "hf_beta", "hm_omega", "hm_psi"}

_KOKORO = None


def _kokoro_instance():
    """Shared kokoro-onnx instance for previews (downloads models on first use)."""
    global _KOKORO
    if _KOKORO is None:
        from kokoro_onnx import Kokoro

        from pipecat.services.kokoro.tts import KOKORO_CACHE_DIR, _ensure_model_files

        model = KOKORO_CACHE_DIR / "kokoro-v1.0.onnx"
        voices = KOKORO_CACHE_DIR / "voices-v1.0.bin"
        _ensure_model_files(model, voices)
        _KOKORO = Kokoro(str(model), str(voices))
    return _KOKORO


def create_stt(client_cfg: dict):
    if client_cfg.get("voice_engine", "sarvam") == "free":
        from pipecat.services.groq.stt import GroqSTTService

        return GroqSTTService(
            api_key=os.environ["GROQ_API_KEY"],
            settings=GroqSTTService.Settings(model="whisper-large-v3-turbo"),
        )

    from pipecat.services.sarvam.stt import SarvamSTTService

    return SarvamSTTService(
        api_key=os.environ["SARVAM_API_KEY"],
        settings=SarvamSTTService.Settings(
            model="saaras:v3",
            language=_stt_language(client_cfg),
        ),
    )


def create_tts(client_cfg: dict):
    if client_cfg.get("voice_engine", "sarvam") == "free":
        from pipecat.services.kokoro.tts import KokoroTTSService
        from pipecat.transcriptions.language import Language

        voice = client_cfg.get("tts_voice", "hf_alpha")
        if voice not in KOKORO_VOICES:
            voice = "hf_alpha"
        # Kokoro speaks hi/en (not other Indic languages) — default to Hindi.
        lang = Language.EN if client_cfg.get("default_language") == "en-IN" else Language.HI
        logger.info(f"Free voice engine: Kokoro '{voice}' ({lang}) + Groq Whisper")
        return KokoroTTSService(
            settings=KokoroTTSService.Settings(voice=voice, language=lang),
        )

    from pipecat.services.sarvam.tts import SarvamTTSService

    voice_model = client_cfg.get("voice_model", "bulbul:v3")
    tts_kwargs = dict(
        model=voice_model,
        voice=client_cfg.get("tts_voice", "priya"),
        language=client_cfg.get("default_language", "hi-IN"),
        pace=float(client_cfg.get("speech_pace", 1.0)),
    )
    if voice_model.startswith("bulbul:v3"):
        # Keep near Sarvam's stable default (0.6) — higher can glitch/warble.
        tts_kwargs["temperature"] = float(client_cfg.get("voice_temperature", 0.65))
    return SarvamTTSService(
        api_key=os.environ["SARVAM_API_KEY"],
        settings=SarvamTTSService.Settings(**tts_kwargs),
    )


# Codes Sarvam's streaming STT accepts for the language parameter.
_SARVAM_STT_CODES = {
    "hi-IN", "bn-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN", "pa-IN", "ta-IN",
    "te-IN", "en-IN", "gu-IN", "as-IN", "ur-IN", "ne-IN",
}


def _stt_language(client_cfg: dict):
    """Sarvam language code to lock transcription to, or None for auto-detect."""
    if client_cfg.get("stt_language", "locked") == "auto":
        return None
    code = client_cfg.get("default_language", "hi-IN")
    return code if code in _SARVAM_STT_CODES else None
