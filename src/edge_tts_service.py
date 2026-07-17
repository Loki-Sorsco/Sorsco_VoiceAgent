"""Free neural TTS via Microsoft Edge's read-aloud voices.

These are the same neural voices Azure sells (Swara, Madhur, and regional
Indian voices) exposed through Edge's free endpoint — dramatically more
human than Kokoro for Indian languages, still ₹0.

Caveat: unofficial API. If Microsoft ever changes it, the edge-tts package
usually adapts within days; agents can fall back to Kokoro meanwhile.
"""

import io
from collections.abc import AsyncGenerator

from loguru import logger

from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
from pipecat.services.tts_service import TTSService

# Short name -> Edge voice id. Female voices first per language.
EDGE_VOICES = {
    "swara": "hi-IN-SwaraNeural",
    "madhur": "hi-IN-MadhurNeural",
    "neerja": "en-IN-NeerjaNeural",
    "prabhat": "en-IN-PrabhatNeural",
    "pallavi": "ta-IN-PallaviNeural",
    "valluvar": "ta-IN-ValluvarNeural",
    "shruti": "te-IN-ShrutiNeural",
    "mohan": "te-IN-MohanNeural",
    "tanishaa": "bn-IN-TanishaaNeural",
    "bashkar": "bn-IN-BashkarNeural",
    "aarohi": "mr-IN-AarohiNeural",
    "manohar": "mr-IN-ManoharNeural",
    "dhwani": "gu-IN-DhwaniNeural",
    "niranjan": "gu-IN-NiranjanNeural",
    "sapna": "kn-IN-SapnaNeural",
    "gagan": "kn-IN-GaganNeural",
    "sobhana": "ml-IN-SobhanaNeural",
    "midhun": "ml-IN-MidhunNeural",
}

# Regional equivalents so an agent set to Tamil etc. automatically speaks it.
EDGE_BY_LANGUAGE = {
    "hi-IN": ("swara", "madhur"),
    "en-IN": ("neerja", "prabhat"),
    "ta-IN": ("pallavi", "valluvar"),
    "te-IN": ("shruti", "mohan"),
    "bn-IN": ("tanishaa", "bashkar"),
    "mr-IN": ("aarohi", "manohar"),
    "gu-IN": ("dhwani", "niranjan"),
    "kn-IN": ("sapna", "gagan"),
    "ml-IN": ("sobhana", "midhun"),
}

EDGE_FEMALE = {"swara", "neerja", "pallavi", "shruti", "tanishaa", "aarohi",
               "dhwani", "sapna", "sobhana"}


def _decode_mp3_to_pcm(data: bytes, sample_rate: int) -> bytes:
    """Decode MP3 bytes to mono s16 PCM at the pipeline's sample rate."""
    import av

    out = bytearray()
    with av.open(io.BytesIO(data)) as container:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=sample_rate)
        for frame in container.decode(audio=0):
            for rf in resampler.resample(frame):
                out.extend(bytes(rf.planes[0]))
        for rf in resampler.resample(None):
            out.extend(bytes(rf.planes[0]))
    return bytes(out)


class EdgeTTSService(TTSService):
    """Microsoft Edge neural voices as a Pipecat TTS service."""

    def __init__(self, *, voice: str = "swara", rate_pct: int = 0, **kwargs):
        super().__init__(**kwargs)
        self._voice_id = EDGE_VOICES.get(voice, voice)
        self._rate = f"{rate_pct:+d}%"
        self.set_voice(self._voice_id)

    def can_generate_metrics(self) -> bool:
        return True

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        logger.debug(f"{self}: Generating Edge TTS [{text}]")
        try:
            import edge_tts

            communicate = edge_tts.Communicate(text, self._voice_id, rate=self._rate)
            mp3 = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3.extend(chunk["data"])
            if not mp3:
                yield ErrorFrame(error="Edge TTS returned no audio")
                return
            pcm = _decode_mp3_to_pcm(bytes(mp3), self.sample_rate)
            await self.start_tts_usage_metrics(text)
            await self.stop_ttfb_metrics()
            chunk_size = getattr(self, "chunk_size", 0) or 9600
            for i in range(0, len(pcm), chunk_size):
                yield TTSAudioRawFrame(
                    pcm[i : i + chunk_size], self.sample_rate, 1, context_id=context_id
                )
        except Exception as e:
            logger.warning(f"Edge TTS failed: {e}")
            yield ErrorFrame(error=f"Edge TTS error: {e}")
