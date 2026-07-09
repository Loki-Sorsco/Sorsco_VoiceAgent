# Multilingual Voice Agent — MVP

A config-driven phone-call voice bot. The brain is generic; each client is a JSON
config (persona + knowledge + tools). This MVP ships one client — **Hotel Sunrise,
Jaipur** — and runs locally with your **microphone and speakers**, so you can talk
to it before wiring up real telephony (Twilio/Exotel).

## Stack

| Piece | What we use |
|---|---|
| Orchestration (latency, barge-in, VAD) | [Pipecat](https://github.com/pipecat-ai/pipecat) |
| STT (speech → text, 11+ Indian languages) | Sarvam AI *Saarika* (free credits on signup) |
| Brain (conversation + tool calling) | Groq Llama 3.3 70B (FREE, ~1000 req/day) — or Gemini/Claude via `LLM_PROVIDER` |
| TTS (text → speech, Indian voices) | Sarvam AI *Bulbul* |
| Availability "database" | `data/availability.json` (mock) |
| Manager notification | Console log + `data/leads.json` (mock) |

## Setup

```powershell
# 1. Install (already done if Claude set this up)
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# 2. Keys (both free, no card needed)
copy .env.example .env
# edit .env — add GROQ_API_KEY (console.groq.com)
#              and SARVAM_API_KEY (dashboard.sarvam.ai)

# 3. Talk to the bot (needs a working mic + speakers)
.venv\Scripts\python run_local.py
```

Speak in Hindi, English, Hinglish, Tamil, Telugu, Bengali... the bot detects and
mirrors your language.

## Browser call (share a link, no installs)

```powershell
.venv\Scripts\python run_web.py -t webrtc     # then open http://localhost:7860
```

Click **Connect**, allow the microphone, talk. To let someone outside your
machine test it:

```powershell
# same WiFi: run with --host 0.0.0.0 and share http://YOUR_LAN_IP:7860
.venv\Scripts\python run_web.py -t webrtc --host 0.0.0.0

# anywhere: free Cloudflare quick tunnel (winget install Cloudflare.cloudflared)
cloudflared tunnel --url http://localhost:7860
# share the https://....trycloudflare.com link it prints
```

`CLIENT_ID` in `.env` picks which client the agent represents.

### Self-hosted deployment (Dokploy, host networking)

`docker-compose.yml` runs the container with `network_mode: host` so WebRTC
audio (UDP) reaches the process directly. Because of that, Dokploy's Domains
tab can't route to it — add a Traefik dynamic config instead
(Dokploy → Traefik File System → new file `voice-agent.yml`):

```yaml
http:
  routers:
    voice-agent:
      rule: Host(`YOUR-DOMAIN-HERE`)
      entryPoints:
        - websecure
      service: voice-agent
      tls:
        certResolver: letsencrypt
  services:
    voice-agent:
      loadBalancer:
        servers:
          - url: "http://SERVER-IP:7860"
```

Also remove any domain for this service from the Domains tab (it would
conflict), and allow inbound UDP on the server firewall (WebRTC media uses
random high ports).

## Dashboard (client onboarding + live call view)

```powershell
.venv\Scripts\python dashboard.py    # then open http://127.0.0.1:8765
```

- **Client setup** (left): create/edit a client — business name, agent name &
  voice, main language, persona, and a free-form JSON knowledge base. Saving
  writes `clients/<id>.json`; no code changes needed.
- **Live call** (right): pick a client, click **Start call**, speak into your
  mic. The conversation transcript and every tool call the agent makes appear
  live. **End call** stops the session.

Note: the demo tools (`check_availability`, `notify_manager`) are hotel-shaped.
A real new client also needs their tools/integrations wired in `src/tools.py`
(their DB, their notification channel) — that part is per-client work by design.

Try: *"kal ke liye deluxe room available hai kya?"* → it calls `check_availability`
against the mock DB. Confirm a booking and it "notifies the manager" (console +
`data/leads.json`).

There is also a **text-only mode** for testing the brain without mic/speakers or a
Sarvam key (needs only GROQ_API_KEY):

```powershell
.venv\Scripts\python run_text.py
```

## Project layout

```
clients/hotel_sunrise.json   # ALL client-specific stuff: persona, knowledge, languages
data/availability.json       # mock room inventory
data/leads.json              # booking leads land here (created on first booking)
dashboard.py                 # web UI: client onboarding + live call monitor
src/call_events.py           # call event log shared by bot and dashboard
src/config_loader.py         # client JSON -> system prompt
src/tools.py                 # check_availability, notify_manager
src/llm_factory.py           # picks Gemini (default) or Claude via LLM_PROVIDER
src/bot.py                   # Pipecat pipeline: STT -> LLM -> TTS + tool registration
run_local.py                 # voice entry point (local mic/speakers)
run_text.py                  # text chat entry point (no audio, no Sarvam needed)
```

## Onboarding the next client

1. Add `clients/<new_client>.json` (persona, knowledge, languages, voice).
2. Add/point tools at their data source in `src/tools.py`.
3. Set `CLIENT_ID=<new_client>` in `.env`.

No changes to the pipeline.

## Next steps (after the demo call feels good)

- **Telephony**: swap `LocalAudioTransport` for a Twilio/Exotel websocket transport
  (Pipecat supports this) — the rest of the pipeline is unchanged.
- **Flow engine**: structured question modules with branching conditions (the
  medical-assessment use case).
- **Admin dashboard**: create client configs in a UI instead of editing JSON.
- **Real connectors**: hotel PMS/database, WhatsApp/email for manager alerts.
