"""The dashboard UI served at /admin — dark SaaS console (ElevenLabs-style).

Single-file SPA: sidebar navigation, agent cards, a no-JSON agent editor for
non-technical users, call queue + history with transcripts, analytics tiles,
Sarvam voice preview, and an embedded in-page test call (Pipecat JS client
over the same WebSocket transport the deployed server uses).
"""

ADMIN_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sorsco Voice — Console</title>
<style>
  :root {
    --bg:#0d0f12; --surface:#15181c; --surface2:#1c2026; --line:#2a2f36;
    --text:#eef0f3; --muted:#8b929d; --accent:#8b7cf7; --accent-soft:#241f45;
    --good:#34d399; --good-soft:#0b2e22; --bad:#f87171; --bad-soft:#3a1414;
    --warn:#fbbf24; --warn-soft:#33260a;
  }
  * { box-sizing:border-box; }
  html,body { margin:0; height:100%; }
  body { background:var(--bg); color:var(--text);
    font:14px/1.55 "Segoe UI",system-ui,sans-serif; display:flex; }
  ::selection { background:var(--accent); color:#fff; }

  /* ---------- sidebar ---------- */
  aside { width:210px; flex:none; background:var(--surface); border-right:1px solid var(--line);
    display:flex; flex-direction:column; padding:18px 12px; gap:4px; min-height:100vh; }
  .logo { font-weight:700; font-size:15.5px; padding:4px 10px 16px; letter-spacing:.01em; }
  .logo span { color:var(--accent); }
  .nav { display:flex; flex-direction:column; gap:2px; }
  .nav button { display:flex; align-items:center; gap:10px; width:100%; text-align:left;
    background:none; border:0; color:var(--muted); font:inherit; font-weight:600;
    padding:9px 10px; border-radius:8px; cursor:pointer; }
  .nav button:hover { background:var(--surface2); color:var(--text); }
  .nav button.on { background:var(--surface2); color:var(--text); }
  .nav button .ic { width:17px; text-align:center; opacity:.9; }
  aside .foot { margin-top:auto; padding:10px; font-size:12px; color:var(--muted); }
  aside .foot a { color:var(--accent); text-decoration:none; }

  /* ---------- main ---------- */
  main { flex:1; padding:26px 34px 60px; overflow-y:auto; min-width:0; }
  .view { display:none; } .view.on { display:block; }
  h1 { font-size:21px; margin:0; font-weight:700; }
  .sub { color:var(--muted); font-size:13.5px; margin:4px 0 22px; }
  .topbar { display:flex; align-items:flex-start; gap:12px; flex-wrap:wrap; }
  .topbar .grow { flex:1; }

  /* ---------- primitives ---------- */
  .btn { padding:8px 15px; border:0; border-radius:8px; font:inherit; font-size:13.5px;
    font-weight:600; cursor:pointer; background:#fff; color:#0d0f12; }
  .btn:hover { background:#e8eaee; }
  .btn.ghost { background:var(--surface2); color:var(--text); border:1px solid var(--line); }
  .btn.ghost:hover { background:#242933; }
  .btn.danger { background:var(--bad-soft); color:var(--bad); border:1px solid #5c2626; }
  .btn.small { padding:5px 11px; font-size:12.5px; }
  .btn:disabled { opacity:.45; cursor:default; }
  input,select,textarea { width:100%; padding:8px 11px; border:1px solid var(--line);
    border-radius:8px; font:inherit; font-size:13.5px; background:var(--surface2); color:var(--text); }
  input:focus,select:focus,textarea:focus,button:focus-visible { outline:2px solid var(--accent); outline-offset:1px; }
  textarea { resize:vertical; }
  label { display:block; font-size:12px; font-weight:600; margin:14px 0 5px; color:var(--muted);
    text-transform:uppercase; letter-spacing:.06em; }
  .card { background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:20px; }
  .chip { display:inline-block; font-size:11.5px; font-weight:700; padding:2px 9px;
    border-radius:99px; background:var(--surface2); border:1px solid var(--line); color:var(--muted); }
  .chip.acc { color:var(--accent); border-color:var(--accent-soft); background:var(--accent-soft); }
  .chip.ok { color:var(--good); background:var(--good-soft); border-color:transparent; }
  .chip.bad { color:var(--bad); background:var(--bad-soft); border-color:transparent; }
  .chip.warn { color:var(--warn); background:var(--warn-soft); border-color:transparent; }
  .row2 { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
  .hint { font-size:12.5px; color:var(--muted); }
  table { border-collapse:collapse; width:100%; font-size:13.5px; }
  th { text-align:left; font-size:11px; letter-spacing:.07em; text-transform:uppercase;
    color:var(--muted); padding:9px 12px; border-bottom:1px solid var(--line); white-space:nowrap; }
  td { padding:10px 12px; border-bottom:1px solid var(--line); vertical-align:top; }
  tr:last-child td { border-bottom:0; }
  .tablewrap { overflow-x:auto; }
  #toast { position:fixed; bottom:22px; left:50%; transform:translateX(-50%);
    background:#fff; color:#0d0f12; font-weight:600; font-size:13.5px;
    padding:10px 18px; border-radius:10px; opacity:0; transition:opacity .25s; pointer-events:none; z-index:99; }
  #toast.err { background:var(--bad); color:#fff; }

  /* ---------- overview ---------- */
  .tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:22px; }
  .tile { background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:16px 18px; }
  .tile .k { font-size:11.5px; color:var(--muted); text-transform:uppercase; letter-spacing:.07em; font-weight:600; }
  .tile .v { font-size:26px; font-weight:700; margin-top:4px; font-variant-numeric:tabular-nums; }
  .tile .v small { font-size:14px; color:var(--muted); font-weight:600; }

  /* ---------- agents ---------- */
  .agents { display:grid; grid-template-columns:repeat(auto-fill,minmax(250px,1fr)); gap:14px; }
  .agent { background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:18px; }
  .agent:hover { border-color:#3a414c; }
  .agent .top { display:flex; gap:12px; align-items:center; margin-bottom:10px; }
  .avatar { width:42px; height:42px; border-radius:50%; flex:none; display:flex; align-items:center;
    justify-content:center; font-weight:700; font-size:17px; background:var(--accent-soft); color:var(--accent); }
  .agent h3 { margin:0; font-size:15px; }
  .agent .who { color:var(--muted); font-size:12.5px; }
  .agent .chips { display:flex; gap:6px; flex-wrap:wrap; margin:8px 0 14px; }
  .agent .acts { display:flex; gap:8px; flex-wrap:wrap; }
  .agent.newcard { display:flex; align-items:center; justify-content:center; min-height:150px;
    border-style:dashed; cursor:pointer; color:var(--muted); font-weight:600; }
  .agent.newcard:hover { color:var(--text); border-color:var(--accent); }

  /* ---------- editor ---------- */
  .tabs { display:flex; gap:4px; border-bottom:1px solid var(--line); margin:18px 0 20px; }
  .tabs button { background:none; border:0; color:var(--muted); font:inherit; font-weight:600;
    padding:9px 14px; cursor:pointer; border-bottom:2px solid transparent; }
  .tabs button.on { color:var(--text); border-bottom-color:var(--accent); }
  .tabpane { display:none; } .tabpane.on { display:block; }
  .prod { display:grid; grid-template-columns:2fr 1fr 3fr 34px; gap:8px; margin-bottom:8px; }
  .prod button { background:var(--bad-soft); color:var(--bad); border:0; border-radius:8px; cursor:pointer; }
  .voice-row { display:flex; gap:8px; align-items:center; }
  .voice-row select { flex:1; }
  .webhook { display:flex; gap:8px; align-items:center; background:var(--surface2);
    border:1px solid var(--line); border-radius:8px; padding:8px 12px; font-size:12.5px;
    font-family:Consolas,monospace; overflow-x:auto; white-space:nowrap; }
  .trig { display:flex; align-items:center; gap:12px; padding:12px 0; border-bottom:1px solid var(--line); }
  .trig:last-child { border-bottom:0; }
  .trig .tx { flex:1; } .trig .tx b { display:block; font-size:13.5px; }
  .trig .tx span { color:var(--muted); font-size:12.5px; }
  .trig input[type=number] { width:110px; }
  .switch { position:relative; width:38px; height:22px; flex:none; }
  .switch input { opacity:0; width:0; height:0; }
  .switch .sl { position:absolute; inset:0; background:var(--surface2); border:1px solid var(--line);
    border-radius:99px; cursor:pointer; transition:.15s; }
  .switch .sl:before { content:""; position:absolute; width:16px; height:16px; border-radius:50%;
    background:var(--muted); top:2px; left:2px; transition:.15s; }
  .switch input:checked + .sl { background:var(--accent); border-color:var(--accent); }
  .switch input:checked + .sl:before { background:#fff; transform:translateX(16px); }

  /* ---------- calls ---------- */
  .pill { font-size:11.5px; font-weight:700; padding:2px 9px; border-radius:99px; white-space:nowrap; }
  .pill.queued { background:var(--warn-soft); color:var(--warn); }
  .pill.dialing { background:var(--accent-soft); color:var(--accent); }
  .pill.in_progress { background:var(--accent-soft); color:var(--accent); }
  .pill.done,.pill.confirmed { background:var(--good-soft); color:var(--good); }
  .pill.cancelled,.pill.dismissed { background:var(--bad-soft); color:var(--bad); }
  .pill.callback,.pill.inbound { background:var(--surface2); color:var(--muted); }

  /* ---------- modal ---------- */
  .modal { position:fixed; inset:0; background:rgba(0,0,0,.6); display:none;
    align-items:center; justify-content:center; z-index:50; padding:20px; }
  .modal.on { display:flex; }
  .modal .box { background:var(--surface); border:1px solid var(--line); border-radius:14px;
    width:min(680px, 100%); max-height:86vh; display:flex; flex-direction:column; }
  .modal .head { display:flex; align-items:center; gap:10px; padding:16px 20px; border-bottom:1px solid var(--line); }
  .modal .head h3 { margin:0; font-size:15.5px; flex:1; }
  .modal .body { padding:18px 20px; overflow-y:auto; }
  .bub { max-width:82%; padding:8px 13px; border-radius:12px; font-size:14px; margin-bottom:10px; }
  .bub .w { font-size:10.5px; font-weight:700; color:var(--muted); text-transform:uppercase; margin-bottom:2px; }
  .bub.user { margin-left:auto; background:var(--accent-soft); border-bottom-right-radius:3px; }
  .bub.assistant { background:var(--surface2); border-bottom-left-radius:3px; }
  .bub.tool { margin:0 auto 10px; background:var(--warn-soft); color:var(--warn);
    font-family:Consolas,monospace; font-size:12px; max-width:95%; }

  /* ---------- test call ---------- */
  .test-status { display:flex; align-items:center; gap:10px; margin-bottom:14px; }
  .dot { width:10px; height:10px; border-radius:50%; background:var(--muted); }
  .dot.live { background:var(--good); box-shadow:0 0 0 4px rgba(52,211,153,.15); }
  .dot.mid { background:var(--warn); }
  #captions { min-height:150px; max-height:300px; overflow-y:auto; background:var(--bg);
    border:1px solid var(--line); border-radius:10px; padding:14px; }
  @media (max-width:900px) { .ovgrid { grid-template-columns:1fr !important; } }
  @media (max-width:760px) { aside { width:60px; } .logo,.nav .tx,aside .foot { display:none; }
    main { padding:18px 14px 60px; } }
</style>
</head>
<body>
<aside>
  <div class="logo">Sorsco <span>Voice</span></div>
  <div class="nav">
    <button data-v="overview" class="on"><span class="ic">◧</span><span class="tx">Overview</span></button>
    <button data-v="agents"><span class="ic">☻</span><span class="tx">Agents</span></button>
    <button data-v="calls"><span class="ic">✆</span><span class="tx">Calls</span></button>
    <button data-v="integrations"><span class="ic">⚡</span><span class="tx">Integrations</span></button>
  </div>
  <div class="foot">Full call page:<br><a href="/client/" target="_blank">/client/ ↗</a></div>
</aside>

<main>
  <!-- ============ OVERVIEW ============ -->
  <div class="view on" id="v-overview">
    <div class="topbar">
      <div class="grow"><h1>Overview</h1>
        <div class="sub">Live picture of your voice agents and order calls.</div></div>
      <button class="btn ghost" onclick="simulate('cod')">＋ Simulate COD order</button>
      <button class="btn" onclick="openTest()">▶ Test active agent</button>
    </div>
    <div class="tiles" id="tiles"></div>
    <div id="checklist" class="card" style="margin-bottom:16px"></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px" class="ovgrid">
      <div class="card">
        <div class="topbar" style="margin-bottom:8px">
          <div class="grow"><b>Calls waiting</b> <span class="hint">— queued by store events</span></div>
          <button class="btn ghost small" onclick="show('calls')">See all →</button>
        </div>
        <div class="tablewrap"><table id="queuePreview"><tbody></tbody></table></div>
      </div>
      <div class="card">
        <div class="topbar" style="margin-bottom:8px">
          <div class="grow"><b>Live call</b> <span class="dot" id="liveDot" style="display:inline-block"></span></div>
        </div>
        <div id="livePanel" style="max-height:280px;overflow-y:auto">
          <span class="hint">When a call is running, the conversation streams here in real time.</span>
        </div>
      </div>
    </div>
  </div>

  <!-- ============ AGENTS ============ -->
  <div class="view" id="v-agents">
    <div class="topbar">
      <div class="grow"><h1>Agents</h1>
        <div class="sub">Each agent is one business. The <b>active</b> agent answers the call page.</div></div>
      <button class="btn" onclick="editAgent(null)">＋ New agent</button>
    </div>
    <div class="agents" id="agentGrid"></div>
  </div>

  <!-- ============ EDITOR ============ -->
  <div class="view" id="v-editor">
    <div class="topbar">
      <div class="grow"><h1 id="edTitle">New agent</h1>
        <div class="sub">Everything your agent knows and does. No coding needed.</div></div>
      <button class="btn ghost" onclick="show('agents')">← Back</button>
      <button class="btn" onclick="saveAgent()">Save agent</button>
    </div>
    <div class="tabs">
      <button class="on" data-t="profile">Profile</button>
      <button data-t="knowledge">Business info</button>
      <button data-t="store">Store & triggers</button>
      <button data-t="chat">Chat test</button>
    </div>

    <div class="tabpane on" id="t-profile"><div class="card" style="max-width:640px">
      <div class="row2">
        <div><label>Agent name</label><input id="f_agent" placeholder="Priya"></div>
        <div><label>Agent ID</label><input id="f_id" placeholder="hotel_sunrise"></div>
      </div>
      <label>Business name</label><input id="f_biz" placeholder="Hotel Sunrise, Jaipur">
      <div class="row2">
        <div><label>Main language</label>
          <select id="f_lang">
            <option value="hi-IN">Hindi</option><option value="en-IN">English (India)</option>
            <option value="ta-IN">Tamil</option><option value="te-IN">Telugu</option>
            <option value="bn-IN">Bengali</option><option value="mr-IN">Marathi</option>
            <option value="kn-IN">Kannada</option><option value="gu-IN">Gujarati</option>
            <option value="pa-IN">Punjabi</option><option value="ml-IN">Malayalam</option>
          </select></div>
        <div><label>Voice</label>
          <div class="voice-row">
            <select id="f_voice">
              <option>priya</option><option>ritu</option><option>neha</option><option>pooja</option>
              <option>simran</option><option>kavya</option><option>ishita</option><option>shreya</option>
              <option>aditya</option><option>rahul</option><option>rohan</option><option>amit</option>
              <option>dev</option><option>varun</option><option>kabir</option>
            </select>
            <button class="btn ghost small" onclick="previewVoice()" title="Hear this voice">▶</button>
          </div></div>
      </div>
      <label>Personality <span style="text-transform:none">(who is the agent?)</span></label>
      <textarea id="f_persona" rows="3"
        placeholder="You are Priya, a warm and helpful front-desk agent at Hotel Sunrise in Jaipur..."></textarea>
    </div></div>

    <div class="tabpane" id="t-knowledge"><div class="card" style="max-width:720px">
      <p class="hint" style="margin-top:0">Fill what applies — the agent only states facts from here.</p>
      <label>About the business</label>
      <textarea id="k_about" rows="2" placeholder="A 30-room heritage hotel near Hawa Mahal..."></textarea>
      <label>Products / services & prices</label>
      <div id="prodRows"></div>
      <button class="btn ghost small" onclick="addProd()">＋ Add item</button>
      <div class="row2" style="margin-top:6px">
        <div><label>Timings</label><input id="k_timings" placeholder="Mon–Sat 9am–8pm"></div>
        <div><label>Location</label><input id="k_location" placeholder="42 MG Road, Jaipur"></div>
      </div>
      <label>Policies (cancellation, returns, payment...)</label>
      <textarea id="k_policies" rows="2"></textarea>
      <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
        <input type="checkbox" id="k_advanced" style="width:auto" onchange="toggleAdvanced()"> Advanced: edit raw JSON
      </label>
      <textarea id="k_json" rows="10" spellcheck="false" style="display:none;font-family:Consolas,monospace"></textarea>
    </div></div>

    <div class="tabpane" id="t-store"><div class="card" style="max-width:720px">
      <p class="hint" style="margin-top:0"><b style="color:var(--text)">Shopify (optional).</b>
        Connect a store and the agent calls customers automatically when these events happen.
        No store? The Simulate buttons demo everything.</p>
      <div class="row2">
        <div><label>Store domain</label><input id="s_domain" placeholder="yourstore.myshopify.com"></div>
        <div><label>Admin API token</label><input id="s_token" type="password" placeholder="shpat_..."></div>
      </div>
      <label>Webhook secret</label><input id="s_secret" type="password">
      <label>Paste this webhook URL in Shopify (Settings → Notifications → Webhooks, event "Order creation")</label>
      <div class="webhook"><span id="whUrl" style="flex:1"></span>
        <button class="btn ghost small" onclick="copyWh()">Copy</button></div>

      <label style="margin-top:22px">Call triggers</label>
      <div class="trig">
        <label class="switch"><input type="checkbox" id="tr_cod"><span class="sl"></span></label>
        <div class="tx"><b>COD confirmation</b><span>New Cash-on-Delivery order → call to confirm. Cuts courier returns.</span></div>
        <input type="number" id="tr_cod_min" min="0" placeholder="Min ₹">
      </div>
      <div class="trig">
        <label class="switch"><input type="checkbox" id="tr_pend"><span class="sl"></span></label>
        <div class="tx"><b>Pending payment</b><span>Order placed but not paid → call to close the sale.</span></div>
        <input type="number" id="tr_pend_min" min="0" placeholder="Min ₹">
      </div>
      <div class="trig">
        <label class="switch"><input type="checkbox" id="tr_cart"><span class="sl"></span></label>
        <div class="tx"><b>Abandoned checkout</b><span>Cart left behind → call to recover it.</span></div>
        <input type="number" id="tr_cart_min" min="0" placeholder="Min ₹">
      </div>
    </div></div>

    <div class="tabpane" id="t-chat"><div class="card" style="max-width:640px">
      <p class="hint" style="margin-top:0">Chat with this agent in text to check its knowledge —
        instant and free, no microphone needed. <b>Save the agent first</b> to test the latest edits.</p>
      <div id="chatLog" style="min-height:180px;max-height:340px;overflow-y:auto;background:var(--bg);
        border:1px solid var(--line);border-radius:10px;padding:14px;margin-bottom:10px">
        <span class="hint">Ask something a customer would — “deluxe room ka price kya hai?”</span>
      </div>
      <div style="display:flex;gap:8px">
        <input id="chatInput" placeholder="Type a customer message…"
          onkeydown="if(event.key==='Enter')sendChat()">
        <button class="btn" onclick="sendChat()">Send</button>
      </div>
    </div></div>
  </div>

  <!-- ============ CHAT TEST (editor tab) placed with editor panes ============ -->

  <!-- ============ CALLS ============ -->
  <div class="view" id="v-calls">
    <div class="topbar">
      <div class="grow"><h1>Calls</h1><div class="sub">Queued order calls and full history with transcripts.</div></div>
      <button class="btn ghost" onclick="simulate('cod')">＋ Simulate COD order</button>
      <button class="btn ghost" onclick="simulate('pending')">＋ Simulate pending payment</button>
      <button class="btn ghost" id="dialAllBtn" style="display:none" onclick="dialAll()">📞 Dial all queued</button>
      <button class="btn" onclick="openModal('mCampaign')">📢 New campaign</button>
    </div>
    <div class="card" style="margin-bottom:16px">
      <b>Queue</b>
      <div class="tablewrap"><table id="queueTable">
        <thead><tr><th>Time</th><th>Order</th><th>Customer</th><th>Why</th><th>Status</th><th></th></tr></thead>
        <tbody></tbody></table></div>
    </div>
    <div class="card">
      <div class="topbar" style="margin-bottom:8px">
        <div class="grow"><b>History</b></div>
        <input id="histSearch" placeholder="Search transcripts…" style="width:220px"
          oninput="renderHistory()">
        <button class="btn ghost small" onclick="exportCsv()">⬇ Export CSV</button>
      </div>
      <div class="tablewrap"><table id="histTable">
        <thead><tr><th>Started</th><th>Agent</th><th>Type</th><th>Outcome</th><th>Length</th><th></th></tr></thead>
        <tbody></tbody></table></div>
    </div>
  </div>

  <!-- ============ INTEGRATIONS ============ -->
  <div class="view" id="v-integrations">
    <div class="topbar">
      <div class="grow"><h1>Integrations</h1>
        <div class="sub">Connect the tools your business already uses — the agent reacts to their events.</div></div>
      <select id="integAgent" style="width:230px" onchange="renderIntegrations()"></select>
    </div>
    <div class="agents" id="integGrid"></div>
    <div class="card" id="integDetail" style="margin-top:16px;display:none"></div>
  </div>
</main>

<!-- transcript modal -->
<div class="modal" id="mTranscript">
  <div class="box">
    <div class="head"><h3 id="trTitle">Transcript</h3>
      <button class="btn ghost small" onclick="closeModal('mTranscript')">Close</button></div>
    <div class="body" id="trBody"></div>
  </div>
</div>

<!-- campaign modal -->
<div class="modal" id="mCampaign">
  <div class="box">
    <div class="head"><h3>New call campaign</h3>
      <button class="btn ghost small" onclick="closeModal('mCampaign')">Close</button></div>
    <div class="body">
      <label style="margin-top:0">Agent</label>
      <select id="campAgent"></select>
      <label>What should the agent do on each call?</label>
      <textarea id="campPurpose" rows="2"
        placeholder="Invite the customer to our Diwali sale — 20% off till Sunday. Answer questions about products."></textarea>
      <label>Contacts — one per line: Name, phone</label>
      <textarea id="campList" rows="6" placeholder="Rahul Sharma, +919876501234
Priya Patel, +919812345678"></textarea>
      <div class="btns"><button class="btn" onclick="startCampaign()">Queue calls</button></div>
      <p class="hint">Calls are queued instantly. With telephony connected they dial automatically;
        for now use ▶ Take call on each to test in the browser.</p>
    </div>
  </div>
</div>

<!-- test call modal -->
<div class="modal" id="mTest">
  <div class="box">
    <div class="head"><h3>Test call <span class="hint" id="testWho"></span></h3>
      <button class="btn ghost small" onclick="closeTest()">Close</button></div>
    <div class="body">
      <div class="test-status">
        <span class="dot" id="testDot"></span><span id="testState">Not connected</span>
        <span style="flex:1"></span>
        <button class="btn" id="testBtn" onclick="toggleCall()">Start call</button>
      </div>
      <div id="captions"><span class="hint">Click Start call, allow the microphone, and speak.
        The conversation appears here live.</span></div>
      <p class="hint" id="testFallback" style="display:none">Embedded call couldn't load on this
        browser — use the <a href="/client/" target="_blank" style="color:var(--accent)">full call
        page ↗</a> (pick <b>WebSocket</b> in its top-left dropdown, then Connect).</p>
    </div>
  </div>
</div>

<div id="toast"></div>

<script>
/* ---------------- utils ---------------- */
async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) { let d; try { d = (await r.json()).detail; } catch(e){} throw new Error(d || r.statusText); }
  return r.json();
}
function toast(msg, err) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.className = err ? 'err' : ''; t.style.opacity = 1;
  clearTimeout(t._h); t._h = setTimeout(() => t.style.opacity = 0, 2600);
}
function esc(s) { const d = document.createElement('div'); d.textContent = s ?? ''; return d.innerHTML; }

/* ---------------- navigation ---------------- */
const views = ['overview','agents','calls','editor','integrations'];
function show(v) {
  views.forEach(x => document.getElementById('v-'+x).classList.toggle('on', x === v));
  document.querySelectorAll('.nav button').forEach(b =>
    b.classList.toggle('on', b.dataset.v === v));
  if (v === 'overview') { loadStats(); pollQueue(); }
  if (v === 'agents') loadAgents();
  if (v === 'calls') { pollQueue(); loadHistory(); }
  if (v === 'integrations') initIntegrations();
}
function openModal(id) {
  if (id === 'mCampaign') {
    document.getElementById('campAgent').innerHTML = CLIENTS.map(c =>
      `<option value="${c.client_id}">${esc(c.business_name)}</option>`).join('');
    document.getElementById('campAgent').value = ACTIVE || (CLIENTS[0] && CLIENTS[0].client_id) || '';
  }
  document.getElementById(id).classList.add('on');
}
document.querySelectorAll('.nav button').forEach(b => b.onclick = () => show(b.dataset.v));
document.querySelectorAll('.tabs button').forEach(b => b.onclick = () => {
  document.querySelectorAll('.tabs button').forEach(x => x.classList.toggle('on', x === b));
  document.querySelectorAll('.tabpane').forEach(p =>
    p.classList.toggle('on', p.id === 't-' + b.dataset.t));
});
function closeModal(id) { document.getElementById(id).classList.remove('on'); }

/* ---------------- overview ---------------- */
async function loadStats() {
  try {
    const s = await api('/api/stats');
    document.getElementById('tiles').innerHTML = `
      <div class="tile"><div class="k">Total calls</div><div class="v">${s.calls_total}</div></div>
      <div class="tile"><div class="k">Order calls</div><div class="v">${s.order_calls}</div></div>
      <div class="tile"><div class="k">Orders confirmed</div><div class="v">${s.confirmed}</div></div>
      <div class="tile"><div class="k">Cancelled</div><div class="v">${s.cancelled}</div></div>
      <div class="tile"><div class="k">Revenue confirmed</div><div class="v">₹${s.revenue_confirmed.toLocaleString('en-IN')}</div></div>
      <div class="tile"><div class="k">Talk time</div><div class="v">${s.minutes}<small> min</small></div></div>`;
    renderChecklist(s);
  } catch(e) {}
}
async function renderChecklist(s) {
  if (!CLIENTS.length) { try { const d = await api('/api/clients'); CLIENTS = d.clients; ACTIVE = d.active; } catch(e){} }
  const anyShop = CLIENTS.some(c => c.shopify_connected);
  const steps = [
    ['Create your first agent', CLIENTS.length > 0, () => show('agents')],
    ['Make a test call', s.calls_total > 0, () => openTest()],
    ['Connect a store or webhook', anyShop, () => show('integrations')],
    ['Get an order call confirmed', s.confirmed > 0, () => show('calls')],
  ];
  const doneN = steps.filter(x => x[1]).length;
  if (doneN === steps.length) { document.getElementById('checklist').style.display = 'none'; return; }
  window._CHECK = steps;
  document.getElementById('checklist').innerHTML =
    `<b>Getting started</b> <span class="hint">${doneN}/${steps.length} done</span>
     <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:10px">` +
    steps.map((st, i) =>
      `<button class="btn ghost small" ${st[1] ? 'style="opacity:.55"' : ''}
        onclick="window._CHECK[${i}][2]()">${st[1] ? '✓' : (i+1) + '.'} ${st[0]}</button>`).join('')
    + '</div>';
}

/* ---------------- live call panel ---------------- */
let liveSeen = 0, liveOn = false;
async function pollLive() {
  if (!document.getElementById('v-overview').classList.contains('on')) return;
  try {
    const d = await api('/api/events?since=' + liveSeen);
    if (d.count < liveSeen) { liveSeen = 0; document.getElementById('livePanel').innerHTML = ''; return; }
    if (!d.events.length) return;
    liveSeen = d.count;
    const p = document.getElementById('livePanel');
    if (p.querySelector('.hint')) p.innerHTML = '';
    d.events.forEach(e => {
      if (e.type === 'call_started') { liveOn = true; p.innerHTML = ''; }
      if (e.type === 'call_ended') liveOn = false;
      if (e.type === 'user' || e.type === 'assistant') {
        const b = document.createElement('div');
        b.className = 'bub ' + e.type;
        b.innerHTML = `<div class="w">${e.type === 'user' ? 'Caller' : 'Agent'} · ${e.time}</div>${esc(e.text)}`;
        p.appendChild(b);
      } else if (e.type === 'tool') {
        const b = document.createElement('div');
        b.className = 'bub tool'; b.textContent = '⚙ ' + e.name;
        p.appendChild(b);
      }
    });
    while (p.children.length > 12) p.removeChild(p.firstChild);
    p.scrollTop = p.scrollHeight;
    document.getElementById('liveDot').className = 'dot' + (liveOn ? ' live' : '');
  } catch(e) {}
}
setInterval(pollLive, 2500);

/* ---------------- agents ---------------- */
let CLIENTS = [], ACTIVE = '';
const LANGS = {'hi-IN':'Hindi','en-IN':'English','ta-IN':'Tamil','te-IN':'Telugu','bn-IN':'Bengali',
  'mr-IN':'Marathi','kn-IN':'Kannada','gu-IN':'Gujarati','pa-IN':'Punjabi','ml-IN':'Malayalam'};
async function loadAgents() {
  const d = await api('/api/clients');
  CLIENTS = d.clients; ACTIVE = d.active;
  document.getElementById('agentGrid').innerHTML = CLIENTS.map(c => `
    <div class="agent">
      <div class="top">
        <div class="avatar">${esc((c.agent_name || c.business_name || '?')[0].toUpperCase())}</div>
        <div><h3>${esc(c.business_name)}</h3><div class="who">agent: ${esc(c.agent_name)}</div></div>
      </div>
      <div class="chips">
        ${c.client_id === ACTIVE ? '<span class="chip ok">● active</span>' : ''}
        <span class="chip">${LANGS[c.default_language] || c.default_language}</span>
        <span class="chip">${esc(c.tts_voice)}</span>
        ${c.shopify_connected ? '<span class="chip acc">shopify</span>' : ''}
      </div>
      <div class="acts">
        <button class="btn ghost small" onclick="editAgent('${c.client_id}')">Edit</button>
        ${c.client_id !== ACTIVE
          ? `<button class="btn ghost small" onclick="makeActive('${c.client_id}')">Set active</button>` : ''}
        <button class="btn small" onclick="testAgent('${c.client_id}')">▶ Test</button>
      </div>
    </div>`).join('') +
    `<div class="agent newcard" onclick="editAgent(null)">＋ New agent</div>`;
}
async function makeActive(id) {
  await api('/api/active-client/' + id, {method:'POST'});
  toast('Active agent: ' + id); loadAgents();
}

/* ---------------- editor ---------------- */
let EDITING = null, RAW = {};
function editAgent(id) {
  EDITING = id; RAW = {}; CHAT = [];
  const cl = document.getElementById('chatLog');
  if (cl) cl.innerHTML = '<span class="hint">Ask something a customer would — “deluxe room ka price kya hai?”</span>';
  show('editor');
  document.getElementById('edTitle').textContent = id ? 'Edit agent' : 'New agent';
  document.getElementById('f_id').disabled = !!id;
  if (!id) { fillForm({}); return; }
  api('/api/clients/' + id).then(fillForm);
}
function fillForm(c) {
  RAW = c;
  set('f_agent', c.agent_name); set('f_id', c.client_id); set('f_biz', c.business_name);
  set('f_lang', c.default_language || 'hi-IN'); set('f_voice', c.tts_voice || 'priya');
  set('f_persona', c.persona);
  const k = c.knowledge || {};
  const friendly = !Object.keys(k).some(key =>
    !['about','products','timings','location','policies'].includes(key));
  document.getElementById('k_advanced').checked = !friendly && Object.keys(k).length > 0;
  toggleAdvanced();
  set('k_about', k.about); set('k_timings', k.timings); set('k_location', k.location);
  set('k_policies', k.policies);
  document.getElementById('k_json').value = JSON.stringify(k, null, 2);
  document.getElementById('prodRows').innerHTML = '';
  (k.products || []).forEach(p => addProd(p));
  if (!(k.products || []).length) addProd();
  const s = c.shopify || {};
  set('s_domain', s.domain); set('s_token', s.access_token); set('s_secret', s.webhook_secret);
  const t = c.triggers || {};
  setTrig('tr_cod','tr_cod_min', t.cod_confirm ?? {enabled:true});
  setTrig('tr_pend','tr_pend_min', t.pending_payment ?? {enabled:true});
  setTrig('tr_cart','tr_cart_min', t.abandoned_checkout ?? {});
  updateWh();
}
function set(id, v) { document.getElementById(id).value = v ?? ''; }
function setTrig(box, min, r) {
  document.getElementById(box).checked = !!(r && r.enabled);
  document.getElementById(min).value = (r && r.min_value) || '';
}
function addProd(p) {
  const div = document.createElement('div'); div.className = 'prod';
  div.innerHTML = `<input placeholder="Item / service" value="${esc(p?.name || p?.type || '')}">
    <input placeholder="Price ₹" value="${esc(p?.price ?? p?.price_per_night_inr ?? '')}">
    <input placeholder="Details" value="${esc(p?.details || p?.description || '')}">
    <button title="Remove" onclick="this.parentElement.remove()">✕</button>`;
  document.getElementById('prodRows').appendChild(div);
}
function toggleAdvanced() {
  const adv = document.getElementById('k_advanced').checked;
  document.getElementById('k_json').style.display = adv ? 'block' : 'none';
  ['k_about','k_timings','k_location','k_policies','prodRows'].forEach(id =>
    document.getElementById(id).style.opacity = adv ? .35 : 1);
}
function updateWh() {
  const id = document.getElementById('f_id').value.trim() || '<agent-id>';
  document.getElementById('whUrl').textContent = location.origin + '/webhooks/shopify/' + id;
}
document.getElementById('f_id').addEventListener('input', updateWh);
function copyWh() {
  navigator.clipboard.writeText(document.getElementById('whUrl').textContent);
  toast('Webhook URL copied');
}
function getTrig(box, min) {
  return { enabled: document.getElementById(box).checked,
           min_value: Number(document.getElementById(min).value) || 0 };
}
async function saveAgent() {
  const id = document.getElementById('f_id').value.trim();
  if (!id) { toast('Agent ID is required', true); return; }
  let knowledge;
  if (document.getElementById('k_advanced').checked) {
    try { knowledge = JSON.parse(document.getElementById('k_json').value); }
    catch(e) { toast('Advanced JSON is invalid: ' + e.message, true); return; }
  } else {
    const products = [...document.querySelectorAll('#prodRows .prod')].map(r => {
      const [n, p, d2] = r.querySelectorAll('input');
      return { name: n.value.trim(), price: p.value.trim(), details: d2.value.trim() };
    }).filter(p => p.name);
    knowledge = {
      about: document.getElementById('k_about').value.trim(),
      products,
      timings: document.getElementById('k_timings').value.trim(),
      location: document.getElementById('k_location').value.trim(),
      policies: document.getElementById('k_policies').value.trim(),
    };
  }
  const lang = document.getElementById('f_lang').value;
  const body = { ...RAW,
    client_id: id,
    agent_name: document.getElementById('f_agent').value.trim(),
    business_name: document.getElementById('f_biz').value.trim(),
    default_language: lang,
    supported_languages: [...new Set([lang, 'hi-IN', 'en-IN'])],
    tts_voice: document.getElementById('f_voice').value,
    persona: document.getElementById('f_persona').value.trim(),
    knowledge,
    shopify: {
      domain: document.getElementById('s_domain').value.trim(),
      access_token: document.getElementById('s_token').value.trim(),
      webhook_secret: document.getElementById('s_secret').value.trim(),
    },
    triggers: {
      cod_confirm: getTrig('tr_cod','tr_cod_min'),
      pending_payment: getTrig('tr_pend','tr_pend_min'),
      abandoned_checkout: getTrig('tr_cart','tr_cart_min'),
    },
  };
  try {
    await api('/api/clients/' + encodeURIComponent(id),
      {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    toast('Agent saved'); show('agents');
  } catch(e) { toast(e.message, true); }
}
function previewVoice() {
  const v = document.getElementById('f_voice').value;
  const lang = document.getElementById('f_lang').value;
  const a = new Audio('/api/voice-preview/' + v + '?lang=' + lang);
  a.play().catch(() => toast('Preview failed', true));
  toast('Playing ' + v + '…');
}

/* ---------------- queue & history ---------------- */
async function simulate(type) {
  const id = EDITING || ACTIVE || 'hotel_sunrise';
  try {
    const r = await api('/api/simulate-order/' + id,
      {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({type})});
    toast(r.queued ? `Order ${r.order} received — call queued` : (r.note || 'No call queued'), !r.queued);
    pollQueue();
  } catch(e) { toast(e.message, true); }
}
function queueRow(t, compact) {
  return `<tr>
    <td>${t.created.slice(11,16)}</td>
    <td><b>#${String(t.order_id).slice(-4)}</b></td>
    <td>${esc(t.customer_name) || '—'}${compact ? '' : '<br><span class="hint">' + esc(t.customer_phone) + '</span>'}</td>
    <td>${t.flow.replace(/_/g,' ')}</td>
    <td><span class="pill ${t.status}">${t.status}</span>
        ${t.outcome ? '<br><span class="hint">' + esc(t.outcome) + '</span>' : ''}</td>
    <td style="white-space:nowrap">${t.status === 'queued'
      ? `${TEL.configured ? `<button class="btn small" onclick="dialTask('${t.task_id}')">📞 Dial</button> ` : ''}
         <button class="btn ${TEL.configured ? 'ghost ' : ''}small" onclick="takeAndTest('${t.task_id}')">▶ Take call</button>
         <button class="btn ghost small" onclick="dismissTask('${t.task_id}')">✕</button>`
      : (t.status === 'done' || t.status === 'callback')
      ? `<button class="btn ghost small" title="Queue this call again"
           onclick="requeueTask('${t.task_id}')">↺ Call again</button>` : ''}</td>
  </tr>`;
}
let TEL = {configured:false};
async function loadTelephony() {
  try {
    TEL = await api('/api/telephony/status');
    document.getElementById('dialAllBtn').style.display = TEL.configured ? '' : 'none';
  } catch(e) {}
}
async function dialTask(id) {
  try {
    const r = await api('/api/queue/' + id + '/dial', {method:'POST'});
    toast('Dialing… the customer\'s phone is ringing'); pollQueue();
  } catch(e) { toast(e.message, true); }
}
async function dialAll() {
  try {
    const r = await api('/api/queue/dial-all', {method:'POST'});
    toast(r.dialed + ' calls dialing' + (r.errors.length ? ` — ${r.errors.length} failed` : ''));
    if (r.errors.length) console.warn(r.errors);
    pollQueue();
  } catch(e) { toast(e.message, true); }
}
async function requeueTask(id) {
  await api('/api/queue/' + id + '/requeue', {method:'POST'});
  toast('Call queued again'); pollQueue();
}
async function pollQueue() {
  try {
    const d = await api('/api/queue');
    const open = d.tasks.filter(t => t.status === 'queued' || t.status === 'in_progress');
    document.querySelector('#queuePreview tbody').innerHTML =
      open.slice(0,5).map(t => queueRow(t, true)).join('')
      || '<tr><td class="hint">No calls waiting. Simulate an order or connect a store.</td></tr>';
    document.querySelector('#queueTable tbody').innerHTML =
      d.tasks.map(t => queueRow(t)).join('')
      || '<tr><td colspan="6" class="hint">Nothing yet.</td></tr>';
  } catch(e) {}
}
async function takeAndTest(id) {
  await api('/api/queue/' + id + '/take', {method:'POST'});
  toast('Call armed — you are the customer');
  openTest();
}
async function dismissTask(id) { await api('/api/queue/' + id + '/dismiss', {method:'POST'}); pollQueue(); }
async function loadHistory() {
  try {
    const d = await api('/api/history');
    window._HIST = d.calls;
    renderHistory();
  } catch(e) {}
}
function renderHistory() {
  const q = (document.getElementById('histSearch').value || '').toLowerCase();
  const calls = (window._HIST || []).filter(c => !q ||
    JSON.stringify(c).toLowerCase().includes(q));
  document.querySelector('#histTable tbody').innerHTML = calls.map(c => `
      <tr>
        <td>${esc(c.started || '')}</td>
        <td>${esc(c.agent)} <span class="hint">· ${esc(c.client)}</span></td>
        <td><span class="pill ${c.kind === 'inbound' ? 'inbound' : 'in_progress'}">${c.kind.replace(/_/g,' ')}</span></td>
        <td>${c.outcome ? `<span class="pill ${c.outcome}">${c.outcome}</span>` : '—'}</td>
        <td>${c.duration_s}s · ${c.turns} turns</td>
        <td><button class="btn ghost small"
          onclick="showTranscript(${window._HIST.indexOf(c)})">View</button></td>
      </tr>`).join('') || '<tr><td colspan="6" class="hint">No calls yet.</td></tr>';
}
function exportCsv() {
  const rows = [['started','agent','client','type','outcome','duration_s','turns']];
  (window._HIST || []).forEach(c => rows.push(
    [c.started, c.agent, c.client, c.kind, c.outcome || '', c.duration_s, c.turns]));
  const csv = rows.map(r => r.map(v => '"' + String(v ?? '').replace(/"/g,'""') + '"').join(',')).join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], {type:'text/csv'}));
  a.download = 'call-history.csv'; a.click();
}

/* ---------------- chat test ---------------- */
let CHAT = [];
async function sendChat() {
  const inp = document.getElementById('chatInput');
  const text = inp.value.trim();
  if (!text) return;
  const id = EDITING || document.getElementById('f_id').value.trim();
  if (!id) { toast('Save the agent first', true); return; }
  inp.value = '';
  const log = document.getElementById('chatLog');
  if (log.querySelector('.hint')) log.innerHTML = '';
  CHAT.push({role:'user', content:text});
  log.innerHTML += `<div class="bub user"><div class="w">You</div>${esc(text)}</div>`;
  log.scrollTop = log.scrollHeight;
  try {
    const r = await api('/api/chat-test/' + id, {method:'POST',
      headers:{'Content-Type':'application/json'}, body: JSON.stringify({messages: CHAT})});
    CHAT.push({role:'assistant', content:r.reply});
    log.innerHTML += `<div class="bub assistant"><div class="w">Agent</div>${esc(r.reply)}</div>`;
    log.scrollTop = log.scrollHeight;
  } catch(e) { toast(e.message, true); }
}

/* ---------------- campaigns ---------------- */
async function startCampaign() {
  const id = document.getElementById('campAgent').value;
  const purpose = document.getElementById('campPurpose').value.trim();
  const entries = document.getElementById('campList').value.split('\n')
    .map(l => l.trim()).filter(Boolean)
    .map(l => { const [name, ...rest] = l.split(','); return {name: name.trim(), phone: rest.join(',').trim()}; });
  if (!purpose || !entries.length) { toast('Purpose and at least one contact needed', true); return; }
  try {
    const r = await api('/api/campaign/' + id, {method:'POST',
      headers:{'Content-Type':'application/json'}, body: JSON.stringify({purpose, entries})});
    toast(r.queued + ' calls queued'); closeModal('mCampaign'); show('calls');
  } catch(e) { toast(e.message, true); }
}

/* ---------------- integrations ---------------- */
let INTEG_CFG = null;
async function initIntegrations() {
  if (!CLIENTS.length) { const d = await api('/api/clients'); CLIENTS = d.clients; ACTIVE = d.active; }
  const sel = document.getElementById('integAgent');
  sel.innerHTML = CLIENTS.map(c => `<option value="${c.client_id}">${esc(c.business_name)}</option>`).join('');
  sel.value = ACTIVE || (CLIENTS[0] && CLIENTS[0].client_id) || '';
  renderIntegrations();
}
async function renderIntegrations() {
  const id = document.getElementById('integAgent').value;
  if (!id) return;
  INTEG_CFG = await api('/api/clients/' + id);
  const shopOn = !!(INTEG_CFG.shopify && INTEG_CFG.shopify.access_token);
  const tiles = [
    ['shopify','🛍️','Shopify','Order & COD calls from your Shopify store', shopOn ? 'connected' : 'available'],
    ['woo','🧩','WooCommerce','Order calls from your WordPress store', 'available'],
    ['webhook','🔗','Universal webhook','Trigger a call from ANY system with one HTTP request', 'available'],
    ['sheets','📋','Google Sheets / Zapier','Queue calls from a sheet row or any Zap', 'available'],
    ['whatsapp','💬','WhatsApp follow-up','Send links & summaries after the call', 'soon'],
    ['telephony','📞','Phone number (Twilio)','Real calls to actual phones — free trial works',
      TEL.configured ? 'connected' : 'available'],
  ];
  document.getElementById('integGrid').innerHTML = tiles.map(t => `
    <div class="agent" style="cursor:${t[4] === 'soon' ? 'default' : 'pointer'}"
      ${t[4] !== 'soon' ? `onclick="integDetail('${t[0]}')"` : ''}>
      <div class="top"><div class="avatar">${t[1]}</div>
        <div><h3>${t[2]}</h3><div class="who">${t[3]}</div></div></div>
      <div class="chips">${
        t[4] === 'connected' ? '<span class="chip ok">● connected</span>' :
        t[4] === 'soon' ? '<span class="chip">coming soon</span>' :
        '<span class="chip acc">set up →</span>'}</div>
    </div>`).join('');
  document.getElementById('integDetail').style.display = 'none';
}
function integDetail(kind) {
  const id = document.getElementById('integAgent').value;
  const base = location.origin;
  const el = document.getElementById('integDetail');
  el.style.display = 'block';
  const s = (INTEG_CFG && INTEG_CFG.shopify) || {};
  if (kind === 'shopify') el.innerHTML = `
    <b>Shopify — ${esc(id)}</b>
    <p class="hint">1. In Shopify admin: Settings → Apps → Develop apps → create an app with
      <b>read_orders, write_orders</b> scope → install → copy the Admin API access token.<br>
      2. Settings → Notifications → Webhooks → add webhook, event <b>Order creation</b>, URL below.</p>
    <div class="row2">
      <div><label>Store domain</label><input id="ig_domain" value="${esc(s.domain || '')}" placeholder="yourstore.myshopify.com"></div>
      <div><label>Admin API token</label><input id="ig_token" type="password" value="${esc(s.access_token || '')}" placeholder="shpat_..."></div>
    </div>
    <label>Webhook secret (optional)</label><input id="ig_secret" type="password" value="${esc(s.webhook_secret || '')}">
    <label>Webhook URL</label>
    <div class="webhook"><span style="flex:1">${base}/webhooks/shopify/${esc(id)}</span>
      <button class="btn ghost small" onclick="copyText('${base}/webhooks/shopify/${esc(id)}')">Copy</button></div>
    <div class="btns">
      <button class="btn" onclick="saveIntegration()">Save</button>
      <button class="btn ghost" onclick="testShopify()">Test connection</button>
    </div><div class="msg" id="igMsg"></div>
    <label style="margin-top:18px">Pull existing orders & queue calls</label>
    <p class="hint" style="margin-top:0">Don't wait for new orders — scan the store now and queue
      calls for everyone matching:</p>
    <div class="btns" style="margin-top:0">
      <button class="btn ghost" onclick="shopifyPull('pending')">💳 All payment-pending orders</button>
      <span style="display:flex;gap:6px;align-items:center">
        <input id="ig_tag" placeholder="or a tag, e.g. call-me" style="width:170px">
        <button class="btn ghost" onclick="shopifyPull('tag')">🏷 Pull by tag</button>
      </span>
    </div>`;
  if (kind === 'telephony') el.innerHTML = `
    <b>Phone number — real calls (Twilio free trial works)</b>
    <p class="hint">
      1. Sign up free at <a href="https://www.twilio.com/try-twilio" target="_blank"
         style="color:var(--accent)">twilio.com/try-twilio</a> — no card, you get ~$15 trial credit
         and a phone number.<br>
      2. In the Twilio console, copy your <b>Account SID</b> and <b>Auth Token</b>
         and note your <b>Twilio phone number</b>.<br>
      3. <b>Verified Caller IDs</b> → add & OTP-verify every number you want to test-call
         (trial accounts can only call verified numbers — your own phone, your team).<br>
      4. Add these environment variables where the server runs (Dokploy → Environment → Deploy):</p>
    <div class="webhook" style="white-space:pre">TWILIO_ACCOUNT_SID=AC................
TWILIO_AUTH_TOKEN=................
TWILIO_FROM_NUMBER=+1..........
PUBLIC_HOST=${location.host}</div>
    <p class="hint">After redeploy this tile turns <b>connected</b>, and every queued call shows a
      <b>📞 Dial</b> button — the customer's actual phone rings and your agent talks to them.
      Trial calls play a short "trial account" notice first; upgrading removes it.</p>
    <div class="msg ${TEL.configured ? 'ok' : ''}">${TEL.configured
      ? 'Configured ✓ — calling from ' + esc(TEL.from_number)
      : 'Not configured yet — missing: ' + (TEL.missing || []).join(', ')}</div>`;
  if (kind === 'woo') el.innerHTML = `
    <b>WooCommerce — ${esc(id)}</b>
    <p class="hint">WordPress admin → WooCommerce → Settings → Advanced → Webhooks → Add:
      topic <b>Order created</b>, delivery URL below. Trigger rules (COD / pending) apply the same.</p>
    <div class="webhook"><span style="flex:1">${base}/webhooks/woocommerce/${esc(id)}</span>
      <button class="btn ghost small" onclick="copyText('${base}/webhooks/woocommerce/${esc(id)}')">Copy</button></div>`;
  if (kind === 'webhook') el.innerHTML = `
    <b>Universal webhook — ${esc(id)}</b>
    <p class="hint">Any system that can send an HTTP request can queue a call — your CRM, your
      website form, a cron job. One request = one queued call.</p>
    <div class="webhook"><span style="flex:1">POST ${base}/webhooks/generic/${esc(id)}</span>
      <button class="btn ghost small" onclick="copyText('${base}/webhooks/generic/${esc(id)}')">Copy</button></div>
    <label>Example</label>
    <div class="webhook" style="white-space:pre">curl -X POST ${base}/webhooks/generic/${esc(id)} \\
  -H "Content-Type: application/json" \\
  -d '{"name":"Rahul","phone":"+9198...","purpose":"Remind about tomorrow 5pm appointment"}'</div>`;
  if (kind === 'sheets') el.innerHTML = `
    <b>Google Sheets / Zapier / Make — ${esc(id)}</b>
    <p class="hint"><b>Zapier / Make:</b> use a "Webhooks → POST" action with the universal webhook URL
      and fields name, phone, purpose.<br>
      <b>Google Sheets:</b> Extensions → Apps Script → send each new row with UrlFetchApp:</p>
    <div class="webhook" style="white-space:pre">UrlFetchApp.fetch("${base}/webhooks/generic/${esc(id)}", {
  method: "post", contentType: "application/json",
  payload: JSON.stringify({name: row[0], phone: row[1], purpose: row[2]})
});</div>`;
  el.scrollIntoView({behavior:'smooth'});
}
function copyText(t) { navigator.clipboard.writeText(t); toast('Copied'); }
async function saveIntegration() {
  const id = document.getElementById('integAgent').value;
  INTEG_CFG.shopify = {
    domain: document.getElementById('ig_domain').value.trim(),
    access_token: document.getElementById('ig_token').value.trim(),
    webhook_secret: document.getElementById('ig_secret').value.trim(),
  };
  await api('/api/clients/' + id, {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify(INTEG_CFG)});
  toast('Integration saved'); renderIntegrations();
}
async function shopifyPull(kind) {
  const id = document.getElementById('integAgent').value;
  const tag = kind === 'tag' ? document.getElementById('ig_tag').value.trim() : '';
  if (kind === 'tag' && !tag) { toast('Enter a tag first', true); return; }
  try {
    const r = await api('/api/shopify/pull/' + id, {method:'POST',
      headers:{'Content-Type':'application/json'}, body: JSON.stringify({kind, tag})});
    toast(`${r.queued} calls queued (${r.scanned} orders scanned)`);
    if (r.queued) show('calls');
  } catch(e) { toast(e.message, true); }
}
async function testShopify() {
  const id = document.getElementById('integAgent').value;
  const m = document.getElementById('igMsg');
  m.className = 'msg'; m.textContent = 'Testing…';
  try {
    await saveIntegration();
    const r = await api('/api/shopify/test/' + id);
    m.className = 'msg ok'; m.textContent = `Connected to "${r.shop}" ✓`;
  } catch(e) { m.className = 'msg err'; m.textContent = e.message; }
}
function showTranscript(i) {
  const c = window._HIST[i];
  document.getElementById('trTitle').textContent =
    `${c.agent} · ${c.kind.replace(/_/g,' ')} · ${c.started}`;
  document.getElementById('trBody').innerHTML = (c.transcript || []).map(e => {
    if (e.type === 'tool') return `<div class="bub tool">⚙ ${esc(e.name)} ${esc(JSON.stringify(e.args || {}))}</div>`;
    return `<div class="bub ${e.type}"><div class="w">${e.type === 'user' ? 'Caller' : 'Agent'} · ${e.time}</div>${esc(e.text)}</div>`;
  }).join('') || '<span class="hint">Empty transcript.</span>';
  document.getElementById('mTranscript').classList.add('on');
}

/* ---------------- embedded test call ---------------- */
let PC = null, CONNECTED = false;
function openTest() {
  document.getElementById('mTest').classList.add('on');
  document.getElementById('testWho').textContent = '· agent: ' + (ACTIVE || '');
}
async function testAgent(id) { await makeActive(id); openTest(); }
function setTestState(txt, cls) {
  document.getElementById('testState').textContent = txt;
  document.getElementById('testDot').className = 'dot ' + (cls || '');
}
function caption(who, text) {
  const c = document.getElementById('captions');
  if (c.querySelector('.hint')) c.innerHTML = '';
  const d = document.createElement('div');
  d.className = 'bub ' + who;
  d.innerHTML = `<div class="w">${who === 'user' ? 'You' : 'Agent'}</div>${esc(text)}`;
  c.appendChild(d); c.scrollTop = c.scrollHeight;
}
async function toggleCall() {
  if (CONNECTED) { try { await PC.disconnect(); } catch(e){} return; }
  const btn = document.getElementById('testBtn');
  btn.disabled = true; setTestState('Connecting…', 'mid');
  try {
    const [cj, wt] = await Promise.all([
      import('https://esm.sh/@pipecat-ai/client-js@1'),
      import('https://esm.sh/@pipecat-ai/websocket-transport@1'),
    ]);
    PC = new cj.PipecatClient({
      transport: new wt.WebSocketTransport(),
      enableMic: true, enableCam: false,
      callbacks: {
        onBotReady: () => { CONNECTED = true; btn.disabled = false; btn.textContent = 'End call';
          btn.className = 'btn danger'; setTestState('Live — speak now', 'live'); },
        onUserTranscript: (d) => { if (d.final) caption('user', d.text); },
        onBotTranscript: (d) => caption('assistant', d.text),
        onDisconnected: () => { CONNECTED = false; btn.disabled = false; btn.textContent = 'Start call';
          btn.className = 'btn'; setTestState('Call ended', ''); },
        onError: (e) => { console.error(e); setTestState('Error — see console', ''); },
      },
    });
    if (PC.startBotAndConnect) {
      await PC.startBotAndConnect({ endpoint: location.origin + '/start',
        requestData: { transport: 'websocket' } });
    } else {
      const r = await api('/start', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({transport:'websocket'})});
      await PC.connect({ wsUrl: r.wsUrl });
    }
  } catch(e) {
    console.error('embedded call failed', e);
    btn.disabled = false; setTestState('Could not start', '');
    document.getElementById('testFallback').style.display = 'block';
  }
}
function closeTest() {
  if (CONNECTED && PC) { try { PC.disconnect(); } catch(e){} }
  closeModal('mTest');
}

/* ---------------- boot ---------------- */
loadStats(); loadAgents(); pollQueue(); loadTelephony();
setInterval(() => {
  if (document.getElementById('v-overview').classList.contains('on')
   || document.getElementById('v-calls').classList.contains('on')) pollQueue();
}, 4000);
</script>
</body>
</html>"""
