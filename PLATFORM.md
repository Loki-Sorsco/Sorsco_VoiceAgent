# The Platform Layer

The voice pipeline (Pipecat + STT/LLM/TTS) is the engine. This document covers
the **platform** built around it: how any business — a hotel, a clinic, an
e-commerce store — plugs the AI voice agent into their existing stack.

Everything below is served by the same process (`run_web.py`), so one
deployment gives you the call line, the dashboard, the API and the widget.

| Surface | URL | Who uses it |
|---|---|---|
| White-label dashboard | `/platform` | The business's team (role-based logins) |
| Public REST API | `/v1/*` | Their developers (`sk_` keys) |
| Embeddable widget | `/widget.js` + `/embed` | Their website visitors (`pk_` keys) |
| Inbound webhooks | `/webhooks/{shopify,woocommerce,generic}/<client>` | Their store/CRM |
| Outbound webhooks | pushed to their endpoints | Their backend |
| Legacy dev console | `/admin` | You, while developing |

---

## 1. Dashboard (`/platform`)

On first boot an admin login is created — credentials are written to
`data/platform/initial_admin.txt` (or set `PLATFORM_ADMIN_EMAIL` /
`PLATFORM_ADMIN_PASSWORD` env vars beforehand). Sign in and change the
password from the **Team** tab.

### Roles

| Role | Sees |
|---|---|
| `agent` | Handoff inbox, live call, conversations, leads, appointments |
| `supervisor` | + overview analytics, call queue, dial controls |
| `admin` | + agents, integrations, widget, API keys, webhooks, team |

Users can be **scoped to specific agents** (Team tab → agent access), so you
can hand a client's staff logins that only see their own agent — that plus
"hide branding" on the widget is white-label mode.

### No-code agent configuration (Agents tab)

Everything about an agent's behaviour is config, not code:

- **Persona, knowledge base, languages, TTS voice** — same as before.
- **Call workflow** — numbered steps the agent walks through.
- **Business rules** — hard constraints ("never discount").
- **Data capture** — the fields the agent must collect ("the caller fills the
  form by talking"). These become the schema of its `capture_lead` tool.
- **Appointments** — toggle booking on; connect Calendly for real slots.
- **Handoff phone** — staff number for live phone-call transfer.

## 2. Human handoff

The agent always has a `transfer_to_human` tool. When a caller asks for a
person (or the agent is stuck), it:

1. Creates a handoff record: reason, customer details, **full transcript so
   far and an instant AI summary** — visible immediately in every dashboard
   (Handoffs tab badge) and pushed as a `handoff.requested` webhook.
2. Staff click **Accept**. If the call is a real phone call (Twilio) and the
   agent has a handoff `transfer_number`, the customer's live call leg is
   redirected to the staff phone. Browser calls: staff read the context and
   take over at the desk / call back.
3. **Resolve** closes the loop; unanswered handoffs age to `missed` after
   15 minutes.

## 3. Public API (`/v1`)

Mint keys in **API & Webhooks**. Each key pair is bound to one agent
(client): the `sk_` secret is shown once and stored hashed; the `pk_` key is
public and only used by the widget.

```bash
# Queue an outbound call from your own system
curl -X POST https://voice.example.com/v1/calls \
  -H "Authorization: Bearer sk_..." -H "Content-Type: application/json" \
  -d '{"name":"Rahul","phone":"+91987...","purpose":"Confirm the 5pm appointment"}'

# Everything else
GET  /v1/me            key check
GET  /v1/agent         agent config       PATCH /v1/agent   update it
GET  /v1/calls         history + transcripts + AI analysis
GET  /v1/calls/{id}    one call           GET /v1/queue     pending calls
GET  /v1/handoffs      + POST /v1/handoffs/{id}/resolve
GET  /v1/leads         GET /v1/appointments
GET  /v1/analytics     volumes, outcomes, sentiment, categories
```

All endpoints are tenant-scoped by the key — a key can never read another
client's data. Interactive schema at `/docs`.

## 4. Widget

**Widget tab** → copy the snippet:

```html
<script src="https://voice.example.com/widget.js" data-key="pk_..." async></script>
```

That's the whole integration: a floating mic button appears; clicking it opens
the branded call panel (`/embed`) — WebRTC audio to this server, live captions,
themed with the agent's colour/greeting, optional "powered by" removal.
`data-color` and `data-position` attributes override the theme per page.

> Note: the current runner hosts one live call session at a time (the same
> demo-mode constraint as `/admin`); opening the embed page arms the line for
> that agent. Multi-session concurrency is the next scaling step.

## 5. Connectors (Integrations tab)

| Connector | What the agent can do with it |
|---|---|
| Shopify / WooCommerce | Order webhooks trigger outbound calls (COD confirm, pending payment, abandoned cart); outcomes tagged back on the order |
| Razorpay / Stripe | `send_payment_link` mid-call (Razorpay links can auto-SMS) |
| Twilio SMS | `send_sms` — text links, addresses, confirmations during the call |
| Calendly | `get_available_slots` (real openings) + booking-link SMS |
| Google Sheets | every captured lead lands as a row (Apps Script URL) |
| **Custom REST API** | the escape hatch: `lookup_customer` (GET with `{query}`) and record save (POST) against **any** system — hospital EMR, hotel PMS, CRM |

Tools appear in the agent's tool belt automatically when their connector is
configured — no prompt editing needed. Each connector has a **Test** button.

## 6. Webhooks out (bidirectional sync)

**API & Webhooks tab** → add endpoints. Events:

`call.started` `call.ended` (with transcript + analysis) `handoff.requested`
`handoff.accepted` `handoff.resolved` `lead.captured` `appointment.booked`
`task.queued` `payment_link.sent`

Deliveries are signed: `X-Voice-Signature: sha256=HMAC(body, secret)` —
verify with the endpoint's secret. Combined with the inbound generic webhook
(`POST /webhooks/generic/<client>` queues a call from any system) this closes
the loop: their events drive calls, call outcomes drive their systems.

## 7. Storage & scaling notes

Platform state lives in `data/platform/` (users, hashed keys, handoffs,
leads, appointments) — JSON files by design, same as the rest of the repo:
one process, no DB to operate. The module boundaries (`auth`, `records`,
`handoff`, `store`) are where SQLite/Postgres slots in when concurrent call
volume demands it. `data/platform/` is gitignored — it holds secrets.
