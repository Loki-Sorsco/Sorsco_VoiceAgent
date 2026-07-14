# Browser-call voice agent (run_web.py) for Dokploy / any Docker host.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

WORKDIR /app

COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

# Bake the free-voice (Kokoro) model files into the image so the first call
# doesn't wait on a ~330MB download.
RUN python -c "from pipecat.services.kokoro.tts import KOKORO_CACHE_DIR, _ensure_model_files; \
_ensure_model_files(KOKORO_CACHE_DIR / 'kokoro-v1.0.onnx', KOKORO_CACHE_DIR / 'voices-v1.0.bin')"

COPY . .

EXPOSE 7860

# Env vars to set in the deployment platform (NOT in the image):
#   GROQ_API_KEY, SARVAM_API_KEY, DAILY_API_KEY, CLIENT_ID (default hotel_sunrise)
# No -t flag: accept all transports. In Docker, browser calls must use Daily
# (select it in the playground's transport dropdown); SmallWebRTC can't cross
# the bridge network.
CMD ["python", "run_web.py", "--host", "0.0.0.0", "--port", "7860"]
