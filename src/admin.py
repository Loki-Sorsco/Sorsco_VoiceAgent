"""Client onboarding + store integration + call queue on the deployed server.

Registered onto the Pipecat runner's FastAPI app by run_web.py, so one domain
serves: the call page (/client/), client setup (/admin), Shopify webhooks
(/webhooks/shopify/{client_id}) and the call-queue API.

Clients are JSON files in clients/. The "active client" and "active call task"
live in data/ so they can be switched at runtime without redeploying.
"""

import base64
import hashlib
import hmac
import json
import random
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from loguru import logger

from src.store import get_task, list_tasks, set_active_task, update_task
from src.triggers import DEFAULT_TRIGGERS, evaluate

ROOT = Path(__file__).resolve().parent.parent
CLIENTS_DIR = ROOT / "clients"
ACTIVE_FILE = ROOT / "data" / "active_client.txt"


def get_active_client_id(default: str = "hotel_sunrise") -> str:
    if ACTIVE_FILE.exists():
        active = ACTIVE_FILE.read_text(encoding="utf-8").strip()
        if active and (CLIENTS_DIR / f"{active}.json").exists():
            return active
    return default


def _load_client(client_id: str) -> dict:
    path = CLIENTS_DIR / f"{client_id}.json"
    if not path.exists():
        raise HTTPException(404, f"No client '{client_id}'")
    return json.loads(path.read_text(encoding="utf-8"))


def register_admin(app: FastAPI):
    # ------------------------------------------------------------- clients

    @app.get("/api/clients")
    def list_clients():
        out = []
        for p in sorted(CLIENTS_DIR.glob("*.json")):
            try:
                cfg = json.loads(p.read_text(encoding="utf-8"))
                out.append(
                    {
                        "client_id": cfg.get("client_id", p.stem),
                        "business_name": cfg.get("business_name", p.stem),
                    }
                )
            except json.JSONDecodeError:
                continue
        return {"clients": out, "active": get_active_client_id()}

    @app.get("/api/clients/{client_id}")
    def get_client(client_id: str):
        cfg = _load_client(client_id)
        cfg.setdefault("triggers", DEFAULT_TRIGGERS)
        cfg.setdefault("shopify", {"domain": "", "access_token": "", "webhook_secret": ""})
        return cfg

    @app.post("/api/clients/{client_id}")
    def save_client(client_id: str, cfg: dict):
        client_id = client_id.strip().lower().replace(" ", "_")
        if not client_id.replace("_", "").isalnum():
            raise HTTPException(400, "client_id must be letters, numbers, underscores")
        required = ["business_name", "agent_name", "persona", "knowledge"]
        missing = [f for f in required if not cfg.get(f)]
        if missing:
            raise HTTPException(400, f"Missing fields: {', '.join(missing)}")
        cfg["client_id"] = client_id
        cfg.setdefault("default_language", "hi-IN")
        cfg.setdefault("supported_languages", ["hi-IN", "en-IN"])
        cfg.setdefault("tts_voice", "priya")
        CLIENTS_DIR.mkdir(exist_ok=True)
        path = CLIENTS_DIR / f"{client_id}.json"
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"saved": client_id}

    @app.post("/api/active-client/{client_id}")
    def set_active(client_id: str):
        _load_client(client_id)
        ACTIVE_FILE.parent.mkdir(exist_ok=True)
        ACTIVE_FILE.write_text(client_id, encoding="utf-8")
        return {"active": client_id}

    # ----------------------------------------------------- shopify webhooks

    @app.post("/webhooks/shopify/{client_id}")
    async def shopify_webhook(client_id: str, request: Request):
        cfg = _load_client(client_id)
        raw = await request.body()

        secret = (cfg.get("shopify") or {}).get("webhook_secret", "")
        if secret:
            sent = request.headers.get("X-Shopify-Hmac-Sha256", "")
            digest = base64.b64encode(
                hmac.new(secret.encode(), raw, hashlib.sha256).digest()
            ).decode()
            if not hmac.compare_digest(digest, sent):
                logger.warning(f"Shopify webhook HMAC mismatch for {client_id}")
                raise HTTPException(401, "HMAC verification failed")

        topic = request.headers.get("X-Shopify-Topic", "orders/create")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            raise HTTPException(400, "Invalid JSON")

        task = evaluate(topic, payload, cfg)
        return {"received": topic, "call_queued": task["task_id"] if task else None}

    @app.post("/api/simulate-order/{client_id}")
    def simulate_order(client_id: str, body: dict):
        """Free demo mode: fake a Shopify orders/create webhook."""
        cfg = _load_client(client_id)
        kind = body.get("type", "cod")
        n = random.randint(1000, 9999)
        payload = {
            "id": n,
            "name": f"#{n}",
            "total_price": str(random.choice([799, 1499, 2499, 3999])),
            "currency": "INR",
            "financial_status": "pending",
            "payment_gateway_names": (
                ["Cash on Delivery (COD)"] if kind == "cod" else ["razorpay"]
            ),
            "customer": {"first_name": "Rahul", "last_name": "Sharma", "phone": "+919876501234"},
            "shipping_address": {
                "address1": "42 MG Road",
                "city": "Jaipur",
                "province": "Rajasthan",
                "zip": "302001",
                "phone": "+919876501234",
            },
            "line_items": [
                {"title": random.choice(
                    ["Cotton Kurta (L)", "Wireless Earbuds", "Steel Water Bottle 1L"]
                ), "quantity": 1, "price": "1499"}
            ],
        }
        task = evaluate("orders/create", payload, cfg)
        if not task:
            return {"queued": None, "note": "No trigger fired — check trigger settings."}
        return {"queued": task["task_id"], "order": payload["name"]}

    # ------------------------------------------------------------ call queue

    @app.get("/api/queue")
    def queue():
        return {"tasks": list(reversed(list_tasks()))[:50]}

    @app.post("/api/queue/{task_id}/take")
    def take_task(task_id: str):
        task = get_task(task_id)
        if not task:
            raise HTTPException(404, "No such task")
        # The next browser call becomes this outbound call, as this client.
        ACTIVE_FILE.parent.mkdir(exist_ok=True)
        ACTIVE_FILE.write_text(task["client_id"], encoding="utf-8")
        set_active_task(task_id)
        return {"armed": task_id, "note": "Open the call page and Connect — you are the customer."}

    @app.post("/api/queue/{task_id}/dismiss")
    def dismiss_task(task_id: str):
        update_task(task_id, status="done", outcome="dismissed")
        return {"dismissed": task_id}

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page():
        return ADMIN_PAGE


ADMIN_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Voice Agent — Admin</title>
<style>
  :root { --bg:#f4f5f7; --card:#fff; --line:#e3e5e8; --text:#1c1e21; --muted:#6b7280;
          --accent:#4f46e5; --accent-soft:#eef2ff; --green:#059669; --green-soft:#d1fae5;
          --red:#dc2626; --amber:#b45309; --amber-soft:#fef3c7; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:"Segoe UI",system-ui,sans-serif; background:var(--bg); color:var(--text); }
  header { padding:14px 24px; background:var(--card); border-bottom:1px solid var(--line);
           display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
  header h1 { font-size:17px; margin:0; }
  header a { color:var(--accent); font-size:13.5px; text-decoration:none; font-weight:600; }
  .wrap { max-width:1160px; margin:0 auto; padding:18px 24px; display:grid;
          grid-template-columns: 420px 1fr; gap:16px; align-items:start; }
  @media (max-width: 980px) { .wrap { grid-template-columns:1fr; } }
  .col { display:flex; flex-direction:column; gap:16px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:18px; }
  .card h2 { font-size:13.5px; margin:0 0 12px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }
  label { display:block; font-size:12.5px; font-weight:600; margin:10px 0 4px; }
  input,select,textarea { width:100%; padding:7px 9px; border:1px solid var(--line); border-radius:6px;
    font:inherit; font-size:13.5px; background:#fff; }
  textarea { resize:vertical; }
  .row { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
  button { padding:8px 14px; border:0; border-radius:7px; font:inherit; font-size:13.5px;
    font-weight:600; cursor:pointer; background:var(--accent); color:#fff; }
  button.secondary { background:var(--accent-soft); color:var(--accent); }
  button.small { padding:5px 10px; font-size:12.5px; }
  .btns { display:flex; gap:8px; margin-top:14px; flex-wrap:wrap; }
  .hint { font-size:12px; color:var(--muted); margin-top:4px; }
  .msg { font-size:13px; margin-top:10px; min-height:18px; }
  .msg.ok { color:var(--green); } .msg.err { color:var(--red); }
  .active-row { display:flex; gap:8px; align-items:center; }
  .badge { background:var(--green-soft); color:var(--green); font-size:12px; font-weight:700;
           padding:3px 10px; border-radius:99px; white-space:nowrap; }
  .trig { display:flex; align-items:center; gap:10px; padding:8px 0; border-bottom:1px solid var(--line); }
  .trig:last-child { border-bottom:0; }
  .trig label { margin:0; flex:1; font-weight:600; font-size:13.5px; }
  .trig .sub { display:block; font-weight:400; color:var(--muted); font-size:12px; }
  .trig input[type=checkbox] { width:auto; }
  .trig input[type=number] { width:110px; }
  table { border-collapse:collapse; width:100%; font-size:13px; }
  th { text-align:left; font-size:11px; letter-spacing:.07em; text-transform:uppercase;
       color:var(--muted); padding:8px 10px; border-bottom:2px solid var(--line); white-space:nowrap; }
  td { padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
  .pill { font-size:11.5px; font-weight:700; padding:2px 9px; border-radius:99px; white-space:nowrap; }
  .pill.queued { background:var(--amber-soft); color:var(--amber); }
  .pill.in_progress { background:var(--accent-soft); color:var(--accent); }
  .pill.done { background:var(--green-soft); color:var(--green); }
  .pill.callback { background:var(--accent-soft); color:var(--accent); }
  .tablewrap { overflow-x:auto; }
</style>
</head>
<body>
<header>
  <h1>Voice Agent Admin</h1>
  <span class="badge" id="activeBadge"></span>
  <span style="flex:1"></span>
  <a href="/client/">→ Open call page</a>
</header>
<div class="wrap">

<div class="col">
  <div class="card">
    <h2>Active client</h2>
    <div class="active-row">
      <select id="activeSelect" style="flex:1"></select>
      <button onclick="setActive()">Set active</button>
    </div>
  </div>

  <div class="card">
    <h2>Add / edit client</h2>
    <label>Existing client</label>
    <select id="clientSelect" onchange="loadClient(this.value)"></select>
    <div class="row">
      <div><label>Client ID</label><input id="client_id"></div>
      <div><label>Agent name</label><input id="agent_name"></div>
    </div>
    <label>Business name</label>
    <input id="business_name">
    <div class="row">
      <div>
        <label>Main language</label>
        <select id="default_language">
          <option value="hi-IN">Hindi</option><option value="en-IN">English (India)</option>
          <option value="ta-IN">Tamil</option><option value="te-IN">Telugu</option>
          <option value="bn-IN">Bengali</option><option value="mr-IN">Marathi</option>
          <option value="kn-IN">Kannada</option><option value="gu-IN">Gujarati</option>
          <option value="pa-IN">Punjabi</option><option value="ml-IN">Malayalam</option>
        </select>
      </div>
      <div>
        <label>Voice</label>
        <select id="tts_voice">
          <option>priya</option><option>ritu</option><option>neha</option><option>pooja</option>
          <option>simran</option><option>kavya</option><option>ishita</option><option>shreya</option>
          <option>aditya</option><option>rahul</option><option>rohan</option><option>amit</option>
          <option>dev</option><option>varun</option><option>kabir</option>
        </select>
      </div>
    </div>
    <label>Persona</label>
    <textarea id="persona" rows="3"></textarea>
    <label>Business knowledge (JSON)</label>
    <textarea id="knowledge" rows="9" spellcheck="false"></textarea>
    <div class="hint">Products/services, prices, timings, policies — any JSON shape.</div>

    <h2 style="margin-top:20px">Shopify store (optional)</h2>
    <label>Store domain</label>
    <input id="shop_domain" placeholder="yourstore.myshopify.com">
    <label>Admin API access token</label>
    <input id="shop_token" placeholder="shpat_..." type="password">
    <label>Webhook secret (recommended)</label>
    <input id="shop_secret" type="password">
    <div class="hint">Free dev store works. Point Shopify webhooks (orders/create) at:
      <b>/webhooks/shopify/&lt;client id&gt;</b> on this domain.</div>

    <h2 style="margin-top:20px">Call triggers</h2>
    <div class="trig">
      <input type="checkbox" id="t_cod">
      <label for="t_cod">COD confirmation
        <span class="sub">New Cash-on-Delivery order → call to confirm (cuts RTO)</span></label>
      <input type="number" id="t_cod_min" min="0" title="Min order value ₹">
    </div>
    <div class="trig">
      <input type="checkbox" id="t_pending">
      <label for="t_pending">Pending payment
        <span class="sub">Order placed, payment not completed → call to close</span></label>
      <input type="number" id="t_pending_min" min="0" title="Min order value ₹">
    </div>
    <div class="trig">
      <input type="checkbox" id="t_cart">
      <label for="t_cart">Abandoned checkout
        <span class="sub">Cart left behind → call to recover</span></label>
      <input type="number" id="t_cart_min" min="0" title="Min cart value ₹">
    </div>

    <div class="btns">
      <button onclick="saveClient()">Save client</button>
      <button class="secondary" onclick="newClient()">+ New client</button>
    </div>
    <div class="msg" id="saveMsg"></div>
  </div>
</div>

<div class="col">
  <div class="card">
    <h2>Order calls <span class="hint" style="display:inline">(queued by store events)</span></h2>
    <div class="btns" style="margin:0 0 12px">
      <button class="secondary small" onclick="simulate('cod')">Simulate COD order</button>
      <button class="secondary small" onclick="simulate('pending')">Simulate pending payment</button>
      <span class="hint" style="align-self:center">Simulations use the client selected in the editor.</span>
    </div>
    <div class="tablewrap">
    <table id="queueTable">
      <thead><tr><th>Time</th><th>Order</th><th>Customer</th><th>Why</th><th>Status</th><th></th></tr></thead>
      <tbody></tbody>
    </table>
    </div>
    <div class="hint" style="margin-top:10px">
      <b>Take call</b> arms the next browser call as this outbound call — open the call page,
      Connect, and play the customer. With telephony connected, these dial automatically.
    </div>
    <div class="msg" id="queueMsg"></div>
  </div>
</div>

</div>
<script>
async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
  return r.json();
}
async function refresh(selected) {
  const d = await api('/api/clients');
  const opts = d.clients.map(c => `<option value="${c.client_id}">${c.business_name}</option>`).join('');
  document.getElementById('clientSelect').innerHTML = opts;
  document.getElementById('activeSelect').innerHTML = opts;
  document.getElementById('activeSelect').value = d.active;
  document.getElementById('activeBadge').textContent = 'active: ' + d.active;
  const sel = document.getElementById('clientSelect');
  if (selected) sel.value = selected;
  if (sel.value) loadClient(sel.value);
}
async function loadClient(id) {
  if (!id) return;
  const c = await api('/api/clients/' + id);
  for (const f of ['client_id','agent_name','business_name','persona'])
    document.getElementById(f).value = c[f] || '';
  document.getElementById('default_language').value = c.default_language || 'hi-IN';
  document.getElementById('tts_voice').value = c.tts_voice || 'priya';
  document.getElementById('knowledge').value = JSON.stringify(c.knowledge || {}, null, 2);
  const s = c.shopify || {};
  document.getElementById('shop_domain').value = s.domain || '';
  document.getElementById('shop_token').value = s.access_token || '';
  document.getElementById('shop_secret').value = s.webhook_secret || '';
  const t = c.triggers || {};
  setTrig('t_cod','t_cod_min', t.cod_confirm);
  setTrig('t_pending','t_pending_min', t.pending_payment);
  setTrig('t_cart','t_cart_min', t.abandoned_checkout);
}
function setTrig(box, min, rule) {
  document.getElementById(box).checked = !!(rule && rule.enabled);
  document.getElementById(min).value = (rule && rule.min_value) || 0;
}
function getTrig(box, min) {
  return { enabled: document.getElementById(box).checked,
           min_value: Number(document.getElementById(min).value) || 0 };
}
function newClient() {
  for (const f of ['client_id','agent_name','business_name','persona','shop_domain','shop_token','shop_secret'])
    document.getElementById(f).value = '';
  document.getElementById('knowledge').value = JSON.stringify(
    {about:"", products_or_services:[], prices:"", timings:"", location:"", policies:""}, null, 2);
  document.getElementById('client_id').focus();
}
async function saveClient() {
  const msg = document.getElementById('saveMsg');
  msg.className = 'msg';
  let knowledge;
  try { knowledge = JSON.parse(document.getElementById('knowledge').value); }
  catch (e) { msg.className='msg err'; msg.textContent='Knowledge is not valid JSON: '+e.message; return; }
  const id = document.getElementById('client_id').value.trim();
  if (!id) { msg.className='msg err'; msg.textContent='Client ID is required'; return; }
  const lang = document.getElementById('default_language').value;
  const body = {
    client_id: id,
    agent_name: document.getElementById('agent_name').value.trim(),
    business_name: document.getElementById('business_name').value.trim(),
    default_language: lang,
    supported_languages: [...new Set([lang, 'hi-IN', 'en-IN'])],
    tts_voice: document.getElementById('tts_voice').value,
    persona: document.getElementById('persona').value.trim(),
    knowledge: knowledge,
    shopify: {
      domain: document.getElementById('shop_domain').value.trim(),
      access_token: document.getElementById('shop_token').value.trim(),
      webhook_secret: document.getElementById('shop_secret').value.trim(),
    },
    triggers: {
      cod_confirm: getTrig('t_cod','t_cod_min'),
      pending_payment: getTrig('t_pending','t_pending_min'),
      abandoned_checkout: getTrig('t_cart','t_cart_min'),
    },
  };
  try {
    await api('/api/clients/' + encodeURIComponent(id),
      {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    msg.className='msg ok'; msg.textContent='Saved ✓';
    refresh(id);
  } catch (e) { msg.className='msg err'; msg.textContent=e.message; }
}
async function setActive() {
  const id = document.getElementById('activeSelect').value;
  await api('/api/active-client/' + encodeURIComponent(id), {method:'POST'});
  refresh(document.getElementById('clientSelect').value);
}
async function simulate(type) {
  const id = document.getElementById('clientSelect').value;
  const m = document.getElementById('queueMsg');
  try {
    const r = await api('/api/simulate-order/' + encodeURIComponent(id),
      {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({type})});
    m.className='msg ok';
    m.textContent = r.queued ? `Order ${r.order} received — call queued ✓` : (r.note || 'No call queued');
    pollQueue();
  } catch (e) { m.className='msg err'; m.textContent=e.message; }
}
async function takeTask(id) {
  const m = document.getElementById('queueMsg');
  const r = await api('/api/queue/' + id + '/take', {method:'POST'});
  m.className='msg ok';
  m.textContent = 'Armed. Open the call page, pick WebSocket, Connect — you are the customer.';
  refresh(document.getElementById('clientSelect').value);
}
async function dismissTask(id) { await api('/api/queue/' + id + '/dismiss', {method:'POST'}); pollQueue(); }
async function pollQueue() {
  try {
    const d = await api('/api/queue');
    const tb = document.querySelector('#queueTable tbody');
    tb.innerHTML = d.tasks.map(t => `
      <tr>
        <td>${t.created.slice(11,16)}</td>
        <td><b>${t.order_id ? '#'+String(t.order_id).slice(-4) : ''}</b></td>
        <td>${t.customer_name || '—'}<br><span class="hint">${t.customer_phone || ''}</span></td>
        <td>${t.flow.replace(/_/g,' ')}</td>
        <td><span class="pill ${t.status}">${t.status}</span>
            ${t.outcome ? '<br><span class="hint">'+t.outcome+'</span>' : ''}</td>
        <td>${t.status === 'queued'
          ? `<button class="small" onclick="takeTask('${t.task_id}')">Take call</button>
             <button class="small secondary" onclick="dismissTask('${t.task_id}')">Dismiss</button>`
          : ''}</td>
      </tr>`).join('') || '<tr><td colspan="6" class="hint">No calls queued yet — simulate an order or connect a store.</td></tr>';
  } catch (e) { /* server restarting */ }
}
refresh();
pollQueue();
setInterval(pollQueue, 4000);
</script>
</body>
</html>"""
