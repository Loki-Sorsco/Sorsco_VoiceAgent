"""Client onboarding on the deployed server: /admin page + API.

Registered onto the Pipecat runner's FastAPI app by run_web.py, so the same
domain serves both the call page (/client/) and client setup (/admin).

Clients are JSON files in clients/. The "active client" (which business the
agent represents on the next call) is stored in data/active_client.txt so it
can be switched from the admin page without redeploying.
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

ROOT = Path(__file__).resolve().parent.parent
CLIENTS_DIR = ROOT / "clients"
ACTIVE_FILE = ROOT / "data" / "active_client.txt"


def get_active_client_id(default: str = "hotel_sunrise") -> str:
    if ACTIVE_FILE.exists():
        active = ACTIVE_FILE.read_text(encoding="utf-8").strip()
        if active and (CLIENTS_DIR / f"{active}.json").exists():
            return active
    return default


def register_admin(app: FastAPI):
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
        CLIENTS_DIR.mkdir(exist_ok=True)
        path = CLIENTS_DIR / f"{client_id}.json"
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"saved": client_id}

    @app.post("/api/active-client/{client_id}")
    def set_active(client_id: str):
        if not (CLIENTS_DIR / f"{client_id}.json").exists():
            raise HTTPException(404, f"No client '{client_id}'")
        ACTIVE_FILE.parent.mkdir(exist_ok=True)
        ACTIVE_FILE.write_text(client_id, encoding="utf-8")
        return {"active": client_id}

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page():
        return ADMIN_PAGE


ADMIN_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Voice Agent — Client Setup</title>
<style>
  :root { --bg:#f4f5f7; --card:#fff; --line:#e3e5e8; --text:#1c1e21; --muted:#6b7280;
          --accent:#4f46e5; --accent-soft:#eef2ff; --green:#059669; --red:#dc2626; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:"Segoe UI",system-ui,sans-serif; background:var(--bg); color:var(--text); }
  header { padding:14px 24px; background:var(--card); border-bottom:1px solid var(--line);
           display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
  header h1 { font-size:17px; margin:0; }
  header a { color:var(--accent); font-size:13.5px; text-decoration:none; font-weight:600; }
  .wrap { max-width:680px; margin:0 auto; padding:18px 24px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:18px; margin-bottom:16px; }
  .card h2 { font-size:14px; margin:0 0 12px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }
  label { display:block; font-size:12.5px; font-weight:600; margin:10px 0 4px; }
  input,select,textarea { width:100%; padding:7px 9px; border:1px solid var(--line); border-radius:6px;
    font:inherit; font-size:13.5px; background:#fff; }
  textarea { resize:vertical; }
  .row { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
  button { padding:8px 14px; border:0; border-radius:7px; font:inherit; font-size:13.5px;
    font-weight:600; cursor:pointer; background:var(--accent); color:#fff; }
  button.secondary { background:var(--accent-soft); color:var(--accent); }
  .btns { display:flex; gap:8px; margin-top:14px; flex-wrap:wrap; }
  .hint { font-size:12px; color:var(--muted); margin-top:4px; }
  .msg { font-size:13px; margin-top:10px; min-height:18px; }
  .msg.ok { color:var(--green); } .msg.err { color:var(--red); }
  .active-row { display:flex; gap:8px; align-items:center; }
  .badge { background:#d1fae5; color:var(--green); font-size:12px; font-weight:700;
           padding:3px 10px; border-radius:99px; }
</style>
</head>
<body>
<header>
  <h1>Client Setup</h1>
  <span style="flex:1"></span>
  <a href="/client/">→ Open call page</a>
</header>
<div class="wrap">

  <div class="card">
    <h2>Active client <span class="hint">(who the agent is on the next call)</span></h2>
    <div class="active-row">
      <select id="activeSelect" style="flex:1"></select>
      <button onclick="setActive()">Set active</button>
      <span class="badge" id="activeBadge"></span>
    </div>
  </div>

  <div class="card">
    <h2>Add / edit client</h2>
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
    <textarea id="knowledge" rows="12" spellcheck="false"></textarea>
    <div class="hint">Everything the agent may state as fact: products/services, prices, timings, policies, address. Any JSON shape works.</div>
    <div class="btns">
      <button onclick="saveClient()">Save client</button>
      <button class="secondary" onclick="newClient()">+ New client</button>
    </div>
    <div class="msg" id="saveMsg"></div>
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
}
function newClient() {
  for (const f of ['client_id','agent_name','business_name','persona'])
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
refresh();
</script>
</body>
</html>"""
