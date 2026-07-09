# Browser-call voice agent (run_web.py) for Dokploy / any Docker host.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

WORKDIR /app

COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

COPY . .

EXPOSE 7860

# Env vars to set in the deployment platform (NOT in the image):
#   GROQ_API_KEY, SARVAM_API_KEY, CLIENT_ID (optional, default hotel_sunrise)
CMD ["python", "run_web.py", "-t", "webrtc", "--host", "0.0.0.0", "--port", "7860"]
