"""Web dashboard: client onboarding + live call view.

- Left panel: create/edit a client's business config (what a client fills in
  when they want the bot to work for THEIR company).
- Right panel: start a voice call session and watch the live transcript,
  including the tool calls the agent makes (availability checks, manager
  notifications).

Usage:  .venv\\Scripts\\python dashboard.py   (or via .claude/launch.json)
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from src.call_events import count_events, read_events

load_dotenv(override=True)

ROOT = Path(__file__).resolve().parent
CLIENTS_DIR = ROOT / "clients"
BOT_LOG = ROOT / "data" / "bot_process.log"

app = FastAPI(title="Voice Agent Dashboard")

bot_proc: subprocess.Popen | None = None
bot_client_id: str | None = None


# ---------------------------------------------------------------- clients API


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
    return out


@app.get("/api/clients/{client_id}")
def get_client(client_id: str):
    path = CLIENTS_DIR / f"{client_id}.json"
    if not path.exists():
        raise HTTPException(404, f"No client '{client_id}'")
    return json.loads(path.read_text(encoding="utf-8"))


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
    path = CLIENTS_DIR / f"{client_id}.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"saved": client_id}


# ------------------------------------------------------------------- call API


def _bot_running() -> bool:
    return bot_proc is not None and bot_proc.poll() is None


@app.post("/api/call/start")
def start_call(body: dict):
    global bot_proc, bot_client_id
    if _bot_running():
        raise HTTPException(409, "A call is already running. Stop it first.")
    client_id = body.get("client_id", "hotel_sunrise")
    if not (CLIENTS_DIR / f"{client_id}.json").exists():
        raise HTTPException(404, f"No client '{client_id}'")

    env = {**os.environ, "PYTHONUTF8": "1"}
    log_file = open(BOT_LOG, "w", encoding="utf-8")
    bot_proc = subprocess.Popen(
        [sys.executable, str(ROOT / "run_local.py"), "--client", client_id],
        cwd=str(ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    bot_client_id = client_id
    return {"started": client_id, "pid": bot_proc.pid}


@app.post("/api/call/stop")
def stop_call():
    global bot_proc
    if not _bot_running():
        return {"stopped": False, "reason": "not running"}
    bot_proc.terminate()
    try:
        bot_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        bot_proc.kill()
    return {"stopped": True}


@app.get("/api/call/status")
def call_status():
    status = {"running": _bot_running(), "client_id": bot_client_id}
    if bot_proc is not None and not _bot_running():
        status["exit_code"] = bot_proc.poll()
        if BOT_LOG.exists():
            lines = BOT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
            status["last_log"] = "\n".join(lines[-8:])
    return status


@app.get("/api/events")
def get_events(since: int = 0):
    return {"events": read_events(since), "total": count_events()}


# ----------------------------------------------------------------------- page


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Voice Agent Dashboard</title>
<style>
  :root {
    --bg: #f4f5f7; --card: #ffffff; --line: #e3e5e8; --text: #1c1e21;
    --muted: #6b7280; --accent: #4f46e5; --accent-soft: #eef2ff;
    --green: #059669; --red: #dc2626; --amber: #b45309; --amber-soft: #fef3c7;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: "Segoe UI", system-ui, sans-serif; background: var(--bg); color: var(--text); }
  header { padding: 14px 24px; background: var(--card); border-bottom: 1px solid var(--line);
           display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 17px; margin: 0; }
  header .sub { color: var(--muted); font-size: 13px; }
  .wrap { display: grid; grid-template-columns: 420px 1fr; gap: 18px; padding: 18px 24px; max-width: 1280px; margin: 0 auto; }
  @media (max-width: 900px) { .wrap { grid-template-columns: 1fr; } }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 18px; }
  .card h2 { font-size: 14px; margin: 0 0 12px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
  label { display: block; font-size: 12.5px; font-weight: 600; margin: 10px 0 4px; }
  input, select, textarea { width: 100%; padding: 7px 9px; border: 1px solid var(--line); border-radius: 6px;
    font: inherit; font-size: 13.5px; background: #fff; }
  textarea { resize: vertical; }
  .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  button { padding: 8px 14px; border: 0; border-radius: 7px; font: inherit; font-size: 13.5px;
    font-weight: 600; cursor: pointer; background: var(--accent); color: #fff; }
  button.secondary { background: var(--accent-soft); color: var(--accent); }
  button.danger { background: var(--red); }
  button:disabled { opacity: .5; cursor: default; }
  .btns { display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
  .hint { font-size: 12px; color: var(--muted); margin-top: 4px; }
  .msg { font-size: 13px; margin-top: 10px; min-height: 18px; }
  .msg.ok { color: var(--green); } .msg.err { color: var(--red); }

  /* call view */
  .call-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: #9ca3af; }
  .dot.live { background: var(--green); box-shadow: 0 0 0 4px rgba(5,150,105,.15); }
  #transcript { height: 520px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px;
    padding: 14px; background: var(--bg); border-radius: 8px; border: 1px solid var(--line); }
  .bubble { max-width: 78%; padding: 9px 13px; border-radius: 12px; font-size: 14px; line-height: 1.45; }
  .bubble .who { font-size: 11px; font-weight: 700; color: var(--muted); margin-bottom: 2px; text-transform: uppercase; }
  .user { align-self: flex-end; background: var(--accent); color: #fff; border-bottom-right-radius: 3px; }
  .user .who { color: rgba(255,255,255,.75); }
  .assistant { align-self: flex-start; background: #fff; border: 1px solid var(--line); border-bottom-left-radius: 3px; }
  .tool { align-self: center; background: var(--amber-soft); color: var(--amber); font-size: 12.5px;
    border-radius: 8px; padding: 7px 12px; max-width: 92%; font-family: Consolas, monospace; }
  .sys { align-self: center; color: var(--muted); font-size: 12px; }
  .interrupted { opacity: .7; }
  .empty { color: var(--muted); font-size: 13.5px; text-align: center; margin-top: 40px; }
</style>
</head>
<body>
<header>
  <h1>Voice Agent Platform</h1>
  <span class="sub">client onboarding &amp; live call monitor</span>
</header>
<div class="wrap">

  <div class="card">
    <h2>Client setup</h2>
    <label>Existing client</label>
    <select id="clientSelect" onchange="loadClient(this.value)"></select>

    <div class="row">
      <div><label>Client ID</label><input id="client_id" placeholder="hotel_sunrise"></div>
      <div><label>Agent name</label><input id="agent_name" placeholder="Priya"></div>
    </div>
    <label>Business name</label>
    <input id="business_name" placeholder="Hotel Sunrise, Jaipur">

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

    <label>Persona <span style="font-weight:400;color:var(--muted)">(who is the agent?)</span></label>
    <textarea id="persona" rows="3" placeholder="You are Priya, a warm and helpful front-desk agent at ..."></textarea>

    <label>Business knowledge (JSON)</label>
    <textarea id="knowledge" rows="10" spellcheck="false"
      placeholder='{"products": [...], "policies": "...", "location": "..."}'></textarea>
    <div class="hint">Everything the agent may state as fact: products/rooms, prices, timings, policies, address. Any JSON shape works.</div>

    <div class="btns">
      <button onclick="saveClient()">Save client</button>
      <button class="secondary" onclick="newClient()">+ New client</button>
    </div>
    <div class="msg" id="saveMsg"></div>
  </div>

  <div class="card">
    <div class="call-head">
      <h2 style="margin:0">Live call</h2>
      <span class="dot" id="statusDot"></span>
      <span class="sub" id="statusText">no call</span>
      <span style="flex:1"></span>
      <button id="startBtn" onclick="startCall()">Start call</button>
      <button id="stopBtn" class="danger" onclick="stopCall()" disabled>End call</button>
    </div>
    <div id="transcript"><div class="empty">Start a call and speak into your microphone.<br>
      The conversation and the agent's actions will appear here live.</div></div>
  </div>

</div>
<script>
let seen = 0, polling = null;

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
  return r.json();
}

async function refreshClients(selected) {
  const clients = await api('/api/clients');
  const sel = document.getElementById('clientSelect');
  sel.innerHTML = clients.map(c =>
    `<option value="${c.client_id}">${c.business_name}</option>`).join('');
  if (selected) sel.value = selected;
  if (sel.value) loadClient(sel.value);
}

async function loadClient(id) {
  if (!id) return;
  const c = await api('/api/clients/' + id);
  document.getElementById('client_id').value = c.client_id || id;
  document.getElementById('agent_name').value = c.agent_name || '';
  document.getElementById('business_name').value = c.business_name || '';
  document.getElementById('default_language').value = c.default_language || 'hi-IN';
  document.getElementById('tts_voice').value = c.tts_voice || 'priya';
  document.getElementById('persona').value = c.persona || '';
  document.getElementById('knowledge').value = JSON.stringify(c.knowledge || {}, null, 2);
}

function newClient() {
  for (const f of ['client_id','agent_name','business_name','persona']) document.getElementById(f).value = '';
  document.getElementById('knowledge').value = JSON.stringify(
    {about: "", products_or_services: [], prices: "", timings: "", location: "", policies: ""}, null, 2);
  document.getElementById('client_id').focus();
}

async function saveClient() {
  const msg = document.getElementById('saveMsg');
  msg.className = 'msg';
  let knowledge;
  try { knowledge = JSON.parse(document.getElementById('knowledge').value); }
  catch (e) { msg.className = 'msg err'; msg.textContent = 'Knowledge is not valid JSON: ' + e.message; return; }
  const id = document.getElementById('client_id').value.trim();
  if (!id) { msg.className = 'msg err'; msg.textContent = 'Client ID is required'; return; }
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
  };
  try {
    await api('/api/clients/' + encodeURIComponent(id), {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    msg.className = 'msg ok'; msg.textContent = 'Saved ✓';
    refreshClients(id);
  } catch (e) { msg.className = 'msg err'; msg.textContent = e.message; }
}

function addBubble(ev) {
  const t = document.getElementById('transcript');
  if (t.querySelector('.empty')) t.innerHTML = '';
  const div = document.createElement('div');
  if (ev.type === 'user' || ev.type === 'assistant') {
    div.className = 'bubble ' + ev.type + (ev.interrupted ? ' interrupted' : '');
    div.innerHTML = `<div class="who">${ev.type === 'user' ? 'Caller' : 'Agent'} · ${ev.time}</div>`;
    div.appendChild(document.createTextNode(ev.text));
    if (ev.interrupted) div.appendChild(Object.assign(document.createElement('div'),
      {className: 'who', textContent: '(interrupted)'}));
  } else if (ev.type === 'tool') {
    div.className = 'tool';
    div.textContent = `⚙ ${ev.name}(${JSON.stringify(ev.args)})`;
  } else if (ev.type === 'call_started') {
    div.className = 'sys';
    div.textContent = `— call started · ${ev.agent} @ ${ev.client} · ${ev.time} —`;
  } else if (ev.type === 'call_ended') {
    div.className = 'sys'; div.textContent = `— call ended · ${ev.time} —`;
  } else return;
  t.appendChild(div);
  t.scrollTop = t.scrollHeight;
}

async function poll() {
  try {
    const d = await api('/api/events?since=' + seen);
    if (seen === 0 && d.total > 0) document.getElementById('transcript').innerHTML = '';
    d.events.forEach(addBubble);
    seen = d.total;
    const s = await api('/api/call/status');
    const dot = document.getElementById('statusDot'), txt = document.getElementById('statusText');
    document.getElementById('startBtn').disabled = s.running;
    document.getElementById('stopBtn').disabled = !s.running;
    dot.className = 'dot' + (s.running ? ' live' : '');
    txt.textContent = s.running ? `LIVE — ${s.client_id}` :
      (s.exit_code !== undefined && s.exit_code !== 0 && s.exit_code !== null
        ? 'bot exited with error (see below)' : 'no call');
    if (!s.running && s.exit_code && s.last_log && !document.getElementById('botErr')) {
      const pre = document.createElement('pre');
      pre.id = 'botErr'; pre.className = 'sys'; pre.style.whiteSpace = 'pre-wrap';
      pre.textContent = s.last_log;
      document.getElementById('transcript').appendChild(pre);
    }
  } catch (e) { /* dashboard restarting; keep polling */ }
}

async function startCall() {
  const id = document.getElementById('clientSelect').value;
  document.getElementById('transcript').innerHTML = '<div class="empty">Starting the voice agent…</div>';
  const err = document.getElementById('botErr'); if (err) err.remove();
  seen = 0;
  try { await api('/api/call/start', {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({client_id: id})});
  } catch (e) { alert(e.message); }
}

async function stopCall() { await api('/api/call/stop', {method: 'POST'}); }

refreshClients();
polling = setInterval(poll, 1000);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    uvicorn.run(app, host="127.0.0.1", port=port)
