"""The /platform dashboard — a single-page app served as one HTML string.

Role-gated views (the sidebar renders only what the login's role allows):

  agent       Handoffs inbox, Live call, History, Leads, Appointments
  supervisor  + Overview analytics, Call queue
  admin       + Agents, Integrations, Widget, API & Webhooks, Users

Same pattern as src/admin_ui.py (the legacy dev console at /admin): plain
HTML/CSS/JS, no build step, talks to /platform/api/* with a Bearer token.
"""

PLATFORM_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Voice Agent Platform</title>
<style>
  :root {
    --bg:#0b1020; --panel:#121a2e; --panel2:#182238; --line:#243050;
    --text:#e5e7eb; --dim:#8b98b8; --accent:#4f46e5; --accent2:#6366f1;
    --good:#34d399; --warn:#fbbf24; --bad:#f87171; --radius:12px;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:system-ui,-apple-system,'Segoe UI',sans-serif; background:var(--bg);
         color:var(--text); min-height:100vh; font-size:14px; }
  a { color:var(--accent2); }
  button { font:inherit; cursor:pointer; }
  input, select, textarea { font:inherit; background:var(--bg); color:var(--text);
    border:1px solid var(--line); border-radius:8px; padding:8px 10px; width:100%; }
  textarea { resize:vertical; min-height:70px; }
  label { display:block; font-size:12px; color:var(--dim); margin:10px 0 4px; }
  .btn { background:var(--accent); color:#fff; border:none; border-radius:8px;
         padding:9px 16px; font-weight:600; }
  .btn:hover { background:var(--accent2); }
  .btn.ghost { background:transparent; border:1px solid var(--line); color:var(--text); }
  .btn.small { padding:5px 10px; font-size:12px; }
  .btn.danger { background:#7f1d1d; }
  .chip { display:inline-block; padding:2px 9px; border-radius:99px; font-size:11px;
          font-weight:600; }
  .chip.waiting { background:#78350f; color:#fcd34d; }
  .chip.accepted { background:#1e3a8a; color:#93c5fd; }
  .chip.resolved { background:#064e3b; color:#6ee7b7; }
  .chip.missed { background:#7f1d1d; color:#fca5a5; }
  .chip.on { background:#064e3b; color:#6ee7b7; }
  .chip.off { background:#374151; color:#9ca3af; }

  /* login */
  #login { display:flex; align-items:center; justify-content:center; min-height:100vh; }
  #login .card { background:var(--panel); border:1px solid var(--line);
    border-radius:16px; padding:34px; width:360px; }
  #login h1 { font-size:20px; margin-bottom:4px; }
  #login p { color:var(--dim); font-size:13px; margin-bottom:18px; }

  /* shell */
  #app { display:none; grid-template-columns:225px 1fr; min-height:100vh; }
  aside { background:var(--panel); border-right:1px solid var(--line); padding:18px 12px;
          display:flex; flex-direction:column; gap:2px; }
  aside .brand { font-weight:800; font-size:15px; padding:6px 10px 16px; letter-spacing:.3px; }
  aside .brand span { color:var(--accent2); }
  aside button.nav { display:flex; justify-content:space-between; align-items:center;
    width:100%; text-align:left; background:none; border:none; color:var(--dim);
    padding:9px 10px; border-radius:8px; font-weight:500; }
  aside button.nav:hover { background:var(--panel2); color:var(--text); }
  aside button.nav.on { background:var(--accent); color:#fff; }
  aside .badge { background:var(--bad); color:#fff; border-radius:99px; padding:0 7px;
                 font-size:11px; font-weight:700; }
  aside .foot { margin-top:auto; padding:10px; font-size:12px; color:var(--dim); }
  main { padding:24px 28px; max-width:1200px; }
  main h2 { font-size:18px; margin-bottom:4px; }
  main .sub { color:var(--dim); font-size:13px; margin-bottom:18px; }
  .toolbar { display:flex; gap:10px; align-items:center; margin-bottom:16px; flex-wrap:wrap; }
  .toolbar select { width:auto; }

  .card { background:var(--panel); border:1px solid var(--line); border-radius:var(--radius);
          padding:18px; margin-bottom:14px; }
  .grid { display:grid; gap:12px; }
  .tiles { grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); }
  .tile { background:var(--panel); border:1px solid var(--line); border-radius:var(--radius);
          padding:16px; }
  .tile b { display:block; font-size:24px; margin-bottom:2px; }
  .tile span { color:var(--dim); font-size:12px; }
  table { width:100%; border-collapse:collapse; }
  th { text-align:left; color:var(--dim); font-size:11px; text-transform:uppercase;
       letter-spacing:.5px; padding:8px 10px; border-bottom:1px solid var(--line); }
  td { padding:9px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
  tr:hover td { background:var(--panel2); }
  .transcript { background:var(--bg); border:1px solid var(--line); border-radius:8px;
    padding:12px; max-height:340px; overflow-y:auto; font-size:13px; line-height:1.6; }
  .transcript .u { color:#93c5fd; }
  .transcript .a { color:var(--text); }
  .transcript .t { color:var(--warn); font-size:12px; }
  .row2 { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
  .muted { color:var(--dim); font-size:12px; }
  .ok { color:var(--good); } .err { color:var(--bad); }
  pre.code { background:var(--bg); border:1px solid var(--line); border-radius:8px;
    padding:12px; overflow-x:auto; font-size:12.5px; color:#a5b4fc; white-space:pre-wrap; }
  #toast { position:fixed; bottom:20px; right:20px; background:var(--panel2);
    border:1px solid var(--line); border-radius:10px; padding:12px 18px; display:none;
    z-index:99; max-width:380px; }
  @media (max-width:820px) { #app { grid-template-columns:1fr; } aside { flex-direction:row;
    flex-wrap:wrap; } aside .foot { display:none; } .row2 { grid-template-columns:1fr; } }
</style>
</head>
<body>

<div id="login">
  <div class="card">
    <h1>Voice Agent Platform</h1>
    <p>Sign in to your dashboard</p>
    <label>Email</label><input id="li-email" type="email" autocomplete="username">
    <label>Password</label><input id="li-pass" type="password" autocomplete="current-password">
    <div style="margin-top:16px"><button class="btn" style="width:100%" onclick="doLogin()">Sign in</button></div>
    <p id="li-err" class="err" style="margin-top:10px; display:none"></p>
    <p class="muted" style="margin-top:14px">First run? Credentials are in
      <code>data/platform/initial_admin.txt</code> on the server.</p>
  </div>
</div>

<div id="app">
  <aside>
    <div class="brand">Sorsco <span>Voice</span></div>
    <div id="nav"></div>
    <div class="foot">
      <div id="who"></div>
      <a href="#" onclick="logout(); return false">Sign out</a>
    </div>
  </aside>
  <main id="main"></main>
</div>

<div id="toast"></div>

<script>
let TOKEN = localStorage.getItem('pf_token') || '';
let USER = null, CLIENTS = [], VIEW = 'overview', CLIENT = '';

const VIEWS = [
  {id:'overview',  label:'Overview',      min:'supervisor'},
  {id:'live',      label:'Live call',     min:'agent'},
  {id:'handoffs',  label:'Handoffs',      min:'agent', badge:true},
  {id:'history',   label:'Conversations', min:'agent'},
  {id:'leads',     label:'Leads',         min:'agent'},
  {id:'appts',     label:'Appointments',  min:'agent'},
  {id:'queue',     label:'Call queue',    min:'supervisor'},
  {id:'agents',    label:'Agents',        min:'admin'},
  {id:'integrations', label:'Integrations', min:'admin'},
  {id:'widget',    label:'Widget',        min:'admin'},
  {id:'api',       label:'API & Webhooks',min:'admin'},
  {id:'users',     label:'Team',          min:'admin'},
];
const RANK = {agent:1, supervisor:2, admin:3};

function esc(s) { return String(s ?? '').replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function toast(msg, ok=true) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.style.borderColor = ok ? 'var(--good)' : 'var(--bad)';
  t.style.display = 'block'; setTimeout(() => t.style.display = 'none', 3500);
}
async function api(path, opts={}) {
  opts.headers = Object.assign({'Content-Type':'application/json',
    'Authorization':'Bearer ' + TOKEN}, opts.headers || {});
  if (opts.body && typeof opts.body !== 'string') opts.body = JSON.stringify(opts.body);
  const r = await fetch(path, opts);
  if (r.status === 401 && path !== '/platform/api/login') { logout(); throw new Error('Signed out'); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || ('HTTP ' + r.status));
  return data;
}

// ---------------------------------------------------------------- session
async function doLogin() {
  const email = document.getElementById('li-email').value.trim();
  const pass = document.getElementById('li-pass').value;
  try {
    const d = await api('/platform/api/login', {method:'POST', body:{email, password:pass}});
    TOKEN = d.token; localStorage.setItem('pf_token', TOKEN);
    boot();
  } catch (e) {
    const el = document.getElementById('li-err');
    el.textContent = e.message; el.style.display = 'block';
  }
}
function logout() {
  TOKEN = ''; localStorage.removeItem('pf_token');
  document.getElementById('app').style.display = 'none';
  document.getElementById('login').style.display = 'flex';
}
async function boot() {
  if (!TOKEN) return;
  let s;
  try { s = await api('/platform/api/session'); } catch (e) { return; }
  USER = s.user; CLIENTS = s.clients;
  document.getElementById('login').style.display = 'none';
  document.getElementById('app').style.display = 'grid';
  document.getElementById('who').textContent = USER.name + ' · ' + USER.role;
  if (RANK[USER.role] < 2) VIEW = 'handoffs';
  renderNav(s.handoffs_waiting);
  show(VIEW);
  setInterval(async () => {
    try { const s2 = await api('/platform/api/session'); renderNav(s2.handoffs_waiting); }
    catch (e) {}
  }, 15000);
}
function renderNav(waiting) {
  const nav = document.getElementById('nav');
  nav.innerHTML = VIEWS.filter(v => RANK[USER.role] >= RANK[v.min]).map(v =>
    `<button class="nav ${v.id === VIEW ? 'on' : ''}" onclick="show('${v.id}')">
       <span>${v.label}</span>
       ${v.badge && waiting ? `<span class="badge">${waiting}</span>` : ''}
     </button>`).join('');
}
function show(view) {
  VIEW = view;
  document.querySelectorAll('#nav .nav').forEach(b => b.classList.remove('on'));
  renderNav(0);
  ({overview, live, handoffs, history, leads, appts, queue, agents,
    integrations, widget, api:apiView, users}[view] ||
    (() => {}))();
}
function clientPicker(onchange) {
  return `<select onchange="${onchange}(this.value)">
    <option value="">All agents</option>
    ${CLIENTS.map(c => `<option ${c === CLIENT ? 'selected' : ''}>${c}</option>`).join('')}
  </select>`;
}

// --------------------------------------------------------------- overview
async function overview() {
  const d = await api('/platform/api/overview' + (CLIENT ? '?client_id=' + CLIENT : ''));
  document.getElementById('main').innerHTML = `
    <h2>Overview</h2><div class="sub">Calls, outcomes and agent performance</div>
    <div class="toolbar">${clientPicker('setClientAnd(overview)')}</div>
    <div class="grid tiles">
      <div class="tile"><b>${d.calls_total}</b><span>Total calls</span></div>
      <div class="tile"><b>${d.minutes}</b><span>Minutes talked</span></div>
      <div class="tile"><b>${d.confirmed}</b><span>Confirmed outcomes</span></div>
      <div class="tile"><b>${d.hot_leads}</b><span>Hot leads</span></div>
      <div class="tile"><b>${d.leads_captured}</b><span>Leads captured</span></div>
      <div class="tile"><b>${d.appointments_booked}</b><span>Appointments</span></div>
      <div class="tile"><b>${d.handoffs_waiting}</b><span>Handoffs waiting</span></div>
    </div>
    <div class="row2" style="margin-top:14px">
      <div class="card"><h3 style="margin-bottom:10px">Top call categories</h3>
        ${d.top_categories.length ? d.top_categories.map(([c, n]) =>
          `<div style="display:flex;justify-content:space-between;padding:5px 0">
             <span>${esc(c.replace(/_/g,' '))}</span><b>${n}</b></div>`).join('')
          : '<span class="muted">No analyzed calls yet</span>'}</div>
      <div class="card"><h3 style="margin-bottom:10px">Caller sentiment</h3>
        ${['positive','neutral','negative'].map(s =>
          `<div style="display:flex;justify-content:space-between;padding:5px 0">
             <span>${s}</span><b>${d.sentiments[s]}</b></div>`).join('')}
        <div class="muted" style="margin-top:8px">Inbound ${d.inbound} · Outbound ${d.outbound}</div>
      </div>
    </div>`;
}
function setClientAnd(fn) { return v => { CLIENT = v; fn(); }; }

// ------------------------------------------------------------------- live
let liveTimer = null, liveSeen = 0;
async function live() {
  if (liveTimer) clearInterval(liveTimer);
  liveSeen = 0;
  document.getElementById('main').innerHTML = `
    <h2>Live call</h2><div class="sub">Watch the active conversation in real time</div>
    <div class="card"><div id="live-status" class="muted">Waiting for a call to start…</div>
      <div class="transcript" id="live-log" style="margin-top:10px; max-height:60vh"></div></div>`;
  const tick = async () => {
    if (VIEW !== 'live') { clearInterval(liveTimer); return; }
    try {
      const d = await fetch('/api/events?since=' + liveSeen).then(r => r.json());
      if (d.count < liveSeen) { liveSeen = 0; document.getElementById('live-log').innerHTML = ''; return; }
      liveSeen = d.count;
      const log = document.getElementById('live-log');
      (d.events || []).forEach(e => {
        const div = document.createElement('div');
        if (e.type === 'user') { div.className = 'u'; div.textContent = 'Caller: ' + e.text; }
        else if (e.type === 'assistant') { div.className = 'a'; div.textContent = 'Agent: ' + e.text; }
        else if (e.type === 'tool') { div.className = 't'; div.textContent = '⚙ ' + e.name + ' ' + JSON.stringify(e.args || {}); }
        else if (e.type === 'handoff') { div.className = 't'; div.textContent = '🤝 Handoff requested: ' + (e.reason || ''); }
        else if (e.type === 'call_started') {
          document.getElementById('live-status').textContent =
            'Live: ' + (e.agent || '') + ' @ ' + (e.client || '') + (e.order_call ? ' — ' + e.order_call : '');
          div.textContent = '— call started ' + e.time + ' —'; div.className = 'muted';
        }
        else if (e.type === 'call_ended') { div.textContent = '— call ended —'; div.className = 'muted'; }
        else return;
        log.appendChild(div); log.scrollTop = log.scrollHeight;
      });
    } catch (e) {}
  };
  tick(); liveTimer = setInterval(tick, 1500);
}

// --------------------------------------------------------------- handoffs
async function handoffs() {
  const d = await api('/platform/api/handoffs' + (CLIENT ? '?client_id=' + CLIENT : ''));
  document.getElementById('main').innerHTML = `
    <h2>Human handoffs</h2>
    <div class="sub">Calls the AI passed to your team — with full context</div>
    <div class="toolbar">${clientPicker('setClientAnd(handoffs)')}
      <button class="btn ghost small" onclick="handoffs()">Refresh</button></div>
    <div id="ho-list">${d.handoffs.length ? '' : '<div class="card muted">No handoffs yet. The agent creates one when a caller asks for a person.</div>'}</div>`;
  const list = document.getElementById('ho-list');
  d.handoffs.forEach(h => {
    const div = document.createElement('div'); div.className = 'card';
    div.innerHTML = `
      <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap">
        <span class="chip ${h.status}">${h.status}</span>
        <b>${esc(h.customer_name || 'Unknown caller')}</b>
        <span class="muted">${esc(h.customer_phone || '')}</span>
        <span class="muted" style="margin-left:auto">${esc(h.created)} · ${esc(h.business_name)}</span>
      </div>
      <p style="margin:10px 0 4px"><b>Why:</b> ${esc(h.reason)}</p>
      <p class="muted" style="margin-bottom:10px"><b>AI summary:</b> ${esc(h.summary)}</p>
      <details><summary class="muted" style="cursor:pointer">Transcript (${h.transcript.length} turns)</summary>
        <div class="transcript" style="margin-top:8px">${h.transcript.map(t =>
          `<div class="${t.who === 'user' ? 'u' : 'a'}">${t.who === 'user' ? 'Caller' : 'Agent'}: ${esc(t.text)}</div>`).join('')}</div>
      </details>
      <div style="margin-top:10px; display:flex; gap:8px">
        ${h.status === 'waiting' ? `<button class="btn small" onclick="hoAccept('${h.handoff_id}')">Accept${h.call_sid ? ' & transfer call' : ''}</button>` : ''}
        ${h.status === 'accepted' ? `<button class="btn small" onclick="hoResolve('${h.handoff_id}')">Mark resolved</button>` : ''}
        ${h.accepted_by ? `<span class="muted">Taken by ${esc(h.accepted_by)}${h.transferred ? ' (call transferred)' : ''}</span>` : ''}
      </div>`;
    list.appendChild(div);
  });
}
async function hoAccept(id) {
  try {
    const d = await api('/platform/api/handoffs/' + id + '/accept', {method:'POST', body:{}});
    toast(d.transferred ? 'Accepted — phone call transferred to your line' :
      'Accepted — context is yours. Call the customer back or take over at the desk.');
    handoffs();
  } catch (e) { toast(e.message, false); }
}
async function hoResolve(id) {
  const note = prompt('Resolution note (optional):') || '';
  try { await api('/platform/api/handoffs/' + id + '/resolve', {method:'POST', body:{note}});
    toast('Resolved'); handoffs(); } catch (e) { toast(e.message, false); }
}

// ---------------------------------------------------------------- history
async function history() {
  const d = await api('/platform/api/history' + (CLIENT ? '?client_id=' + CLIENT : ''));
  document.getElementById('main').innerHTML = `
    <h2>Conversations</h2><div class="sub">Every call with transcript and AI analysis</div>
    <div class="toolbar">${clientPicker('setClientAnd(history)')}
      <a class="btn ghost small" href="/api/history/export">Export Excel</a></div>
    <div id="hist"></div>`;
  const el = document.getElementById('hist');
  if (!d.calls.length) { el.innerHTML = '<div class="card muted">No calls yet.</div>'; return; }
  d.calls.forEach(c => {
    const a = c.analysis || {};
    const div = document.createElement('div'); div.className = 'card';
    div.innerHTML = `
      <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:center">
        <b>${esc(c.customer_name || 'Caller')}</b>
        <span class="muted">${esc(c.customer_phone || '')}</span>
        <span class="chip ${a.sentiment === 'negative' ? 'missed' : a.sentiment === 'positive' ? 'resolved' : 'off'}">${esc(a.sentiment || '—')}</span>
        <span class="chip off">${esc((c.kind || '').replace(/_/g,' '))}</span>
        ${c.outcome ? `<span class="chip ${c.outcome === 'confirmed' ? 'resolved' : 'off'}">${esc(c.outcome)}</span>` : ''}
        <span class="muted" style="margin-left:auto">${esc(c.started || '')} · ${c.duration_s || 0}s · ${esc(c.client || '')}</span>
      </div>
      ${a.summary ? `<p style="margin-top:8px">${esc(a.summary)}</p>` : ''}
      ${a.unanswered && a.unanswered !== 'none' ? `<p class="err" style="margin-top:4px">Couldn't answer: ${esc(a.unanswered)}</p>` : ''}
      <details style="margin-top:8px"><summary class="muted" style="cursor:pointer">Transcript</summary>
        <div class="transcript" style="margin-top:8px">${(c.transcript || []).map(t =>
          t.type === 'tool'
            ? `<div class="t">⚙ ${esc(t.name)}</div>`
            : `<div class="${t.type === 'user' ? 'u' : 'a'}">${t.type === 'user' ? 'Caller' : 'Agent'}: ${esc(t.text)}</div>`).join('')}</div>
      </details>`;
    el.appendChild(div);
  });
}

// ------------------------------------------------------- leads & appts
async function leads() {
  const d = await api('/platform/api/leads' + (CLIENT ? '?client_id=' + CLIENT : ''));
  tableView('Leads', 'Structured records the agent captured on calls',
    'setClientAnd(leads)', d.leads);
}
async function appts() {
  const d = await api('/platform/api/appointments' + (CLIENT ? '?client_id=' + CLIENT : ''));
  tableView('Appointments', 'Bookings the agent made or requested',
    'setClientAnd(appts)', d.appointments);
}
function tableView(title, sub, picker, rows) {
  const cols = [...new Set(rows.flatMap(r => Object.keys(r)))]
    .filter(c => c !== 'client_id').slice(0, 8);
  document.getElementById('main').innerHTML = `
    <h2>${title}</h2><div class="sub">${sub}</div>
    <div class="toolbar">${clientPicker(picker)}</div>
    <div class="card" style="overflow-x:auto">${rows.length ? `
      <table><tr>${cols.map(c => `<th>${esc(c)}</th>`).join('')}</tr>
      ${rows.map(r => `<tr>${cols.map(c => `<td>${esc(r[c] ?? '')}</td>`).join('')}</tr>`).join('')}</table>`
      : '<span class="muted">Nothing here yet.</span>'}</div>`;
}

// ------------------------------------------------------------------ queue
async function queue() {
  const d = await api('/platform/api/queue');
  document.getElementById('main').innerHTML = `
    <h2>Call queue</h2><div class="sub">Outbound calls waiting to be made (store triggers, API, campaigns)</div>
    <div class="toolbar"><button class="btn small" onclick="dialAll()">Dial all queued</button>
      <button class="btn ghost small" onclick="queue()">Refresh</button></div>
    <div class="card" style="overflow-x:auto">
      ${d.tasks.length ? `<table>
      <tr><th>Created</th><th>Customer</th><th>Phone</th><th>Purpose</th><th>Status</th><th>Outcome</th><th></th></tr>
      ${d.tasks.map(t => `<tr>
        <td>${esc(t.created)}</td><td>${esc(t.customer_name)}</td><td>${esc(t.customer_phone)}</td>
        <td>${esc(t.reason)}</td><td><span class="chip ${t.status === 'queued' ? 'waiting' : 'off'}">${esc(t.status)}</span></td>
        <td>${esc(t.outcome || '')}</td>
        <td style="white-space:nowrap">${t.status === 'queued' ? `
          <button class="btn small" onclick="dial('${t.task_id}')">Dial</button>
          <button class="btn ghost small" onclick="takeTask('${t.task_id}')">Browser</button>` : ''}</td>
      </tr>`).join('')}</table>` : '<span class="muted">Queue is empty.</span>'}</div>`;
}
async function dial(id) {
  try { await api('/api/queue/' + id + '/dial', {method:'POST'}); toast('Dialing…'); queue(); }
  catch (e) { toast(e.message, false); }
}
async function dialAll() {
  try { const d = await api('/api/queue/dial-all', {method:'POST'});
    toast(`Dialed ${d.dialed}, held ${d.held_for_hours} (calling hours)`); queue(); }
  catch (e) { toast(e.message, false); }
}
async function takeTask(id) {
  try { await api('/api/queue/' + id + '/take', {method:'POST'});
    toast('Armed — open the call page and Connect: you play the customer.'); }
  catch (e) { toast(e.message, false); }
}

// ----------------------------------------------------------------- agents
async function agents() {
  const d = await api('/platform/api/agents');
  document.getElementById('main').innerHTML = `
    <h2>Agents</h2><div class="sub">One AI voice agent per business/brand — behavior is all config, no code</div>
    <div class="toolbar"><button class="btn small" onclick="editAgent('')">+ New agent</button>
      <a class="btn ghost small" href="/admin" target="_blank">Open legacy console</a></div>
    <div class="card" style="overflow-x:auto"><table>
      <tr><th>Agent ID</th><th>Business</th><th>Voice persona</th><th>Language</th><th></th></tr>
      ${d.agents.map(a => `<tr>
        <td><code>${esc(a.client_id)}</code></td><td>${esc(a.business_name)}</td>
        <td>${esc(a.agent_name)} (${esc(a.tts_voice)})</td><td>${esc(a.default_language)}</td>
        <td style="white-space:nowrap">
          <button class="btn small" onclick="editAgent('${a.client_id}')">Configure</button>
          <button class="btn ghost small" onclick="activate('${a.client_id}')">Set live</button></td>
      </tr>`).join('')}</table></div>
    <div id="agent-form"></div>`;
}
async function activate(id) {
  try { await api('/platform/api/agents/' + id + '/activate', {method:'POST'});
    toast(id + ' now answers browser & inbound phone calls'); } catch (e) { toast(e.message, false); }
}
async function editAgent(id) {
  let a = {client_id:'', business_name:'', agent_name:'', persona:'', knowledge:{},
    default_language:'hi-IN', supported_languages:['hi-IN','en-IN'], tts_voice:'priya',
    call_workflow:'', call_rules:'', data_capture:null, appointments:{}, handoff:{}, call_hours:{}};
  if (id) a = await api('/platform/api/agents/' + id);
  const dc = a.data_capture || [];
  document.getElementById('agent-form').innerHTML = `<div class="card">
    <h3>${id ? 'Configure ' + esc(id) : 'New agent'}</h3>
    <div class="row2">
      <div><label>Agent ID (letters/underscores)</label>
        <input id="af-id" value="${esc(a.client_id)}" ${id ? 'disabled' : ''}></div>
      <div><label>Business name</label><input id="af-biz" value="${esc(a.business_name)}"></div>
      <div><label>Agent (voice persona) name</label><input id="af-name" value="${esc(a.agent_name)}"></div>
      <div><label>TTS voice</label><input id="af-voice" value="${esc(a.tts_voice)}"></div>
      <div><label>Main language (e.g. hi-IN)</label><input id="af-lang" value="${esc(a.default_language)}"></div>
      <div><label>All languages (comma separated)</label>
        <input id="af-langs" value="${esc((a.supported_languages || []).join(', '))}"></div>
    </div>
    <label>Persona — who the agent is, tone, style</label>
    <textarea id="af-persona">${esc(a.persona)}</textarea>
    <label>Knowledge base (JSON: services, prices, timings, policies…)</label>
    <textarea id="af-knowledge" style="min-height:120px">${esc(JSON.stringify(a.knowledge || {}, null, 2))}</textarea>
    <div class="row2">
      <div><label>Call workflow (numbered steps the agent follows)</label>
        <textarea id="af-flow">${esc(a.call_workflow || '')}</textarea></div>
      <div><label>Business rules (hard rules, e.g. "never discount")</label>
        <textarea id="af-rules">${esc(a.call_rules || '')}</textarea></div>
    </div>
    <label>Data capture — fields the agent must collect (the caller "fills the form" by talking)</label>
    <div id="af-dc">${dc.map((f, i) => dcRow(f, i)).join('')}</div>
    <button class="btn ghost small" onclick="addDcRow()">+ field</button>
    <div class="row2" style="margin-top:6px">
      <div><label>Handoff phone (staff line for live call transfer)</label>
        <input id="af-handoff" value="${esc((a.handoff || {}).transfer_number || '')}" placeholder="+91..."></div>
      <div><label>Appointments</label>
        <select id="af-appts"><option value="">Off</option>
          <option value="on" ${(a.appointments || {}).enabled ? 'selected' : ''}>On (agent can book)</option></select></div>
    </div>
    <div style="margin-top:14px; display:flex; gap:8px">
      <button class="btn" onclick="saveAgent('${esc(a.client_id)}')">Save agent</button>
      <button class="btn ghost" onclick="document.getElementById('agent-form').innerHTML=''">Cancel</button>
    </div></div>`;
}
function dcRow(f, i) {
  return `<div style="display:flex; gap:8px; margin-bottom:6px" class="dc-row">
    <input placeholder="key (e.g. patient_name)" value="${esc(f.key || '')}" style="flex:1">
    <input placeholder="what to ask for" value="${esc(f.label || '')}" style="flex:2">
    <select style="width:110px"><option value="">optional</option>
      <option value="1" ${f.required ? 'selected' : ''}>required</option></select>
    <button class="btn ghost small" onclick="this.parentElement.remove()">×</button></div>`;
}
function addDcRow() {
  document.getElementById('af-dc').insertAdjacentHTML('beforeend', dcRow({}, 99));
}
async function saveAgent(existingId) {
  let knowledge;
  try { knowledge = JSON.parse(document.getElementById('af-knowledge').value || '{}'); }
  catch (e) { toast('Knowledge must be valid JSON', false); return; }
  const dc = [...document.querySelectorAll('#af-dc .dc-row')].map(row => {
    const [k, l] = row.querySelectorAll('input');
    return {key: k.value.trim(), label: l.value.trim(),
      required: !!row.querySelector('select').value};
  }).filter(f => f.key);
  const id = existingId || document.getElementById('af-id').value.trim();
  const body = {
    business_name: document.getElementById('af-biz').value.trim(),
    agent_name: document.getElementById('af-name').value.trim(),
    tts_voice: document.getElementById('af-voice').value.trim() || 'priya',
    default_language: document.getElementById('af-lang').value.trim() || 'hi-IN',
    supported_languages: document.getElementById('af-langs').value.split(',')
      .map(s => s.trim()).filter(Boolean),
    persona: document.getElementById('af-persona').value.trim(),
    knowledge,
    call_workflow: document.getElementById('af-flow').value,
    call_rules: document.getElementById('af-rules').value,
    data_capture: dc.length ? dc : null,
    handoff: {transfer_number: document.getElementById('af-handoff').value.trim()},
    appointments: {enabled: !!document.getElementById('af-appts').value},
  };
  try { await api('/platform/api/agents/' + id, {method:'POST', body});
    toast('Saved ' + id); agents(); } catch (e) { toast(e.message, false); }
}

// ----------------------------------------------------------- integrations
async function integrations() {
  if (!CLIENT && CLIENTS.length) CLIENT = CLIENTS[0];
  document.getElementById('main').innerHTML = `
    <h2>Integrations</h2><div class="sub">Connect the agent to the systems this business already uses</div>
    <div class="toolbar"><select onchange="CLIENT=this.value; integrations()">
      ${CLIENTS.map(c => `<option ${c === CLIENT ? 'selected' : ''}>${c}</option>`).join('')}
    </select></div><div id="conn-list"></div>`;
  if (!CLIENT) return;
  const d = await api('/platform/api/connectors/' + CLIENT);
  const el = document.getElementById('conn-list');
  el.innerHTML = '';
  d.connectors.forEach(c => {
    const div = document.createElement('div'); div.className = 'card';
    div.innerHTML = `
      <div style="display:flex; align-items:center; gap:10px">
        <b>${esc(c.name)}</b><span class="muted">${esc(c.category)}</span>
        <span class="chip ${c.configured ? 'on' : 'off'}">${c.configured ? 'connected' : 'not set up'}</span>
      </div>
      <p class="muted" style="margin:6px 0 4px">${esc(c.description)}</p>
      ${c.webhook_path ? `<p class="muted">Webhook in: <code>POST ${esc(c.webhook_path)}</code></p>` : ''}
      ${c.fields.map(f => `<label>${esc(f.label)}${f.required ? ' *' : ''}</label>
        <input data-conn="${c.id}" data-key="${f.key}" ${f.secret ? 'type="password"' : ''}
          value="${esc(typeof c.values[f.key] === 'object' ? JSON.stringify(c.values[f.key]) : (c.values[f.key] || ''))}">`).join('')}
      <div style="margin-top:10px; display:flex; gap:8px">
        ${c.fields.length ? `<button class="btn small" onclick="saveConn('${c.id}')">Save</button>` : ''}
        <button class="btn ghost small" onclick="testConn('${c.id}')">Test</button>
        <span id="conn-msg-${c.id}" class="muted"></span>
      </div>`;
    el.appendChild(div);
  });
}
async function saveConn(id) {
  const values = {};
  document.querySelectorAll(`input[data-conn="${id}"]`).forEach(i => values[i.dataset.key] = i.value.trim());
  try { await api(`/platform/api/connectors/${CLIENT}/${id}`, {method:'POST', body:{values}});
    toast('Saved — the agent picks it up on the next call'); integrations(); }
  catch (e) { toast(e.message, false); }
}
async function testConn(id) {
  const el = document.getElementById('conn-msg-' + id);
  el.textContent = 'Testing…';
  try { const d = await api(`/platform/api/connectors/${CLIENT}/${id}/test`, {method:'POST'});
    el.textContent = d.message; el.className = d.ok ? 'ok' : 'err'; }
  catch (e) { el.textContent = e.message; el.className = 'err'; }
}

// ------------------------------------------------------------------ widget
async function widget() {
  if (!CLIENT && CLIENTS.length) CLIENT = CLIENTS[0];
  document.getElementById('main').innerHTML = `
    <h2>Widget</h2><div class="sub">Embed the voice agent on any website or portal with one script tag</div>
    <div class="toolbar"><select onchange="CLIENT=this.value; widget()">
      ${CLIENTS.map(c => `<option ${c === CLIENT ? 'selected' : ''}>${c}</option>`).join('')}
    </select></div><div id="wg"></div>`;
  if (!CLIENT) return;
  const d = await api('/platform/api/widget/' + CLIENT);
  const w = d.widget;
  document.getElementById('wg').innerHTML = `
    <div class="card"><h3>Embed code</h3>
      <p class="muted" style="margin:6px 0">Paste before <code>&lt;/body&gt;</code> — replace YOUR-DOMAIN with this server's public domain.</p>
      <pre class="code">${esc(d.snippet)}</pre>
      ${d.fresh_secret ? `<p class="warn" style="color:var(--warn)">A secret API key was also minted for this agent (shown once):</p>
        <pre class="code">${esc(d.fresh_secret)}</pre>` : ''}
      <p class="muted">Publishable key: <code>${esc(d.publishable)}</code> — safe to expose; it only picks which agent answers.</p>
    </div>
    <div class="card"><h3>Appearance</h3>
      <div class="row2">
        <div><label>Accent color</label><input id="wg-color" value="${esc(w.color || '#4f46e5')}"></div>
        <div><label>Button position</label><select id="wg-pos">
          <option value="right" ${w.position !== 'left' ? 'selected' : ''}>Bottom right</option>
          <option value="left" ${w.position === 'left' ? 'selected' : ''}>Bottom left</option></select></div>
      </div>
      <label>Greeting line</label><input id="wg-greet" value="${esc(w.greeting || '')}"
        placeholder="Tap the mic and start talking">
      <label style="display:flex; gap:8px; align-items:center; margin-top:10px">
        <input type="checkbox" id="wg-brand" style="width:auto" ${w.hide_branding ? 'checked' : ''}>
        Hide "Powered by" branding (white-label)</label>
      <div style="margin-top:12px"><button class="btn" onclick="saveWidget()">Save</button>
        <a class="btn ghost" style="margin-left:8px" target="_blank"
          href="/embed?key=${encodeURIComponent(d.publishable)}">Preview the call page</a></div>
    </div>`;
}
async function saveWidget() {
  try {
    await api('/platform/api/widget/' + CLIENT, {method:'POST', body:{widget:{
      color: document.getElementById('wg-color').value,
      position: document.getElementById('wg-pos').value,
      greeting: document.getElementById('wg-greet').value,
      hide_branding: document.getElementById('wg-brand').checked,
    }}});
    toast('Widget saved'); widget();
  } catch (e) { toast(e.message, false); }
}

// --------------------------------------------------------- api & webhooks
async function apiView() {
  if (!CLIENT && CLIENTS.length) CLIENT = CLIENTS[0];
  document.getElementById('main').innerHTML = `
    <h2>API &amp; Webhooks</h2><div class="sub">API-first: everything the dashboard does, your code can do too</div>
    <div class="toolbar"><select onchange="CLIENT=this.value; apiView()">
      ${CLIENTS.map(c => `<option ${c === CLIENT ? 'selected' : ''}>${c}</option>`).join('')}
    </select></div><div id="api-body"></div>`;
  if (!CLIENT) return;
  const [keys, hooks] = await Promise.all([
    api('/platform/api/keys?client_id=' + CLIENT),
    api('/platform/api/webhooks/' + CLIENT),
  ]);
  document.getElementById('api-body').innerHTML = `
    <div class="card"><h3>API keys</h3>
      <table><tr><th>Label</th><th>Secret</th><th>Publishable</th><th>Created</th><th></th></tr>
      ${keys.keys.map(k => `<tr ${k.revoked ? 'style="opacity:.45"' : ''}>
        <td>${esc(k.label || '—')}</td><td><code>${esc(k.secret_hint)}</code></td>
        <td><code>${esc(k.publishable)}</code></td><td>${esc(k.created)}</td>
        <td>${k.revoked ? 'revoked' : `<button class="btn danger small" onclick="revokeKey('${k.key_id}')">Revoke</button>`}</td>
      </tr>`).join('')}</table>
      <div style="margin-top:10px; display:flex; gap:8px">
        <input id="key-label" placeholder="Label (e.g. production)" style="width:220px">
        <button class="btn small" onclick="mintKey()">Create key pair</button></div>
      <div id="key-fresh"></div>
    </div>
    <div class="card"><h3>Outbound webhooks</h3>
      <p class="muted" style="margin-bottom:8px">POSTs signed with <code>X-Voice-Signature</code> (HMAC-SHA256 of the body). Leave events blank for all: ${hooks.event_types.map(e => `<code>${e}</code>`).join(' ')}</p>
      <div id="hook-rows">${(hooks.webhooks.length ? hooks.webhooks : [{}]).map(h => hookRow(h)).join('')}</div>
      <div style="display:flex; gap:8px; margin-top:8px">
        <button class="btn ghost small" onclick="document.getElementById('hook-rows').insertAdjacentHTML('beforeend', hookRow({}))">+ endpoint</button>
        <button class="btn small" onclick="saveHooks()">Save webhooks</button></div>
    </div>
    <div class="card"><h3>Quick start</h3>
      <pre class="code"># Queue an outbound call from your system
curl -X POST https://YOUR-DOMAIN/v1/calls \\
  -H "Authorization: Bearer sk_..." -H "Content-Type: application/json" \\
  -d '{"name":"Rahul","phone":"+91987...","purpose":"Confirm tomorrow 5pm appointment"}'

# Read calls with transcripts + AI analysis
curl https://YOUR-DOMAIN/v1/calls -H "Authorization: Bearer sk_..."

# Full endpoint list: /v1/me /v1/agent /v1/calls /v1/queue /v1/handoffs
#                     /v1/leads /v1/appointments /v1/analytics
# Inbound event -> call:  POST /webhooks/generic/${esc(CLIENT)} {"name","phone","purpose"}</pre>
      <p class="muted">Full docs: <code>PLATFORM.md</code> in the repo · interactive schema at <a href="/docs" target="_blank">/docs</a></p>
    </div>`;
}
function hookRow(h) {
  return `<div class="hook-row" style="display:flex; gap:8px; margin-bottom:6px">
    <input placeholder="https://your-system.com/hooks/voice" value="${esc(h.url || '')}" style="flex:2">
    <input placeholder="events (comma sep, blank = all)" value="${esc((h.events || []).join(','))}" style="flex:1">
    <input placeholder="secret (blank = generate)" value="${esc(h.secret || '')}" style="flex:1">
    <button class="btn ghost small" onclick="this.parentElement.remove()">×</button></div>`;
}
async function saveHooks() {
  const webhooks = [...document.querySelectorAll('.hook-row')].map(r => {
    const [url, events, secret] = r.querySelectorAll('input');
    return {url: url.value.trim(), secret: secret.value.trim(),
      events: events.value.split(',').map(s => s.trim()).filter(Boolean)};
  }).filter(h => h.url);
  try { const d = await api('/platform/api/webhooks/' + CLIENT, {method:'POST', body:{webhooks}});
    toast('Saved ' + d.saved + ' endpoint(s)'); apiView(); } catch (e) { toast(e.message, false); }
}
async function mintKey() {
  try {
    const d = await api('/platform/api/keys', {method:'POST',
      body:{client_id: CLIENT, label: document.getElementById('key-label').value}});
    document.getElementById('key-fresh').innerHTML =
      `<p class="ok" style="margin-top:10px">Copy the secret now — it is shown ONCE:</p>
       <pre class="code">${esc(d.secret)}</pre>`;
  } catch (e) { toast(e.message, false); }
}
async function revokeKey(id) {
  if (!confirm('Revoke this key? Anything using it stops working.')) return;
  try { await api('/platform/api/keys/' + id + '/revoke', {method:'POST'}); apiView(); }
  catch (e) { toast(e.message, false); }
}

// ------------------------------------------------------------------- users
async function users() {
  const d = await api('/platform/api/users');
  document.getElementById('main').innerHTML = `
    <h2>Team</h2><div class="sub">Logins for this dashboard — scope staff to specific agents for white-label access</div>
    <div class="card" style="overflow-x:auto"><table>
      <tr><th>Email</th><th>Name</th><th>Role</th><th>Agents</th><th></th></tr>
      ${d.users.map(u => `<tr>
        <td>${esc(u.email)}</td><td>${esc(u.name)}</td><td>${esc(u.role)}</td>
        <td>${esc((u.client_ids || []).join(', '))}</td>
        <td>${u.email !== USER.email ? `<button class="btn danger small" onclick="delUser('${esc(u.email)}')">Remove</button>` : '<span class="muted">you</span>'}</td>
      </tr>`).join('')}</table></div>
    <div class="card"><h3>Add / update user</h3>
      <div class="row2">
        <div><label>Email</label><input id="u-email"></div>
        <div><label>Name</label><input id="u-name"></div>
        <div><label>Role</label><select id="u-role">
          <option value="agent">agent — handoffs & history</option>
          <option value="supervisor">supervisor — + analytics & queue</option>
          <option value="admin">admin — everything</option></select></div>
        <div><label>Password (min 8, blank = keep)</label><input id="u-pass" type="password"></div>
      </div>
      <label>Agent access (* = all, or comma-separated agent IDs)</label>
      <input id="u-scope" value="*">
      <div style="margin-top:12px"><button class="btn" onclick="saveUser()">Save user</button></div>
    </div>
    <div class="card"><h3>Change my password</h3>
      <div class="row2">
        <div><label>Current</label><input id="cp-cur" type="password"></div>
        <div><label>New (min 8)</label><input id="cp-new" type="password"></div>
      </div>
      <div style="margin-top:12px"><button class="btn ghost" onclick="changePass()">Change password</button></div>
    </div>`;
}
async function saveUser() {
  const scope = document.getElementById('u-scope').value.trim();
  try {
    await api('/platform/api/users', {method:'POST', body:{
      email: document.getElementById('u-email').value,
      name: document.getElementById('u-name').value,
      role: document.getElementById('u-role').value,
      password: document.getElementById('u-pass').value || null,
      client_ids: scope === '*' || !scope ? ['*'] : scope.split(',').map(s => s.trim()),
    }});
    toast('User saved'); users();
  } catch (e) { toast(e.message, false); }
}
async function delUser(email) {
  if (!confirm('Remove ' + email + '?')) return;
  try { await api('/platform/api/users/' + encodeURIComponent(email), {method:'DELETE'});
    users(); } catch (e) { toast(e.message, false); }
}
async function changePass() {
  try {
    await api('/platform/api/change-password', {method:'POST', body:{
      current: document.getElementById('cp-cur').value,
      new: document.getElementById('cp-new').value}});
    toast('Password changed');
  } catch (e) { toast(e.message, false); }
}

document.getElementById('li-pass').addEventListener('keydown',
  e => { if (e.key === 'Enter') doLogin(); });
boot();
</script>
</body>
</html>"""
