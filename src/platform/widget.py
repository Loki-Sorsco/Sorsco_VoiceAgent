"""Embeddable voice widget: one script tag puts the agent on any website.

The business pastes this into their site / admin portal (the dashboard's
"Widget" tab generates it with their real key):

  <script src="https://voice.example.com/widget.js" data-key="pk_..." async></script>

widget.js (the loader) draws a floating call button and opens an iframe to
/embed — a white-label call page themed from the client's "widget" config:

  "widget": {"color": "#4f46e5", "position": "right", "button_text": "Talk to us",
             "greeting": "Hi! Ask me anything.", "hide_branding": false}

The pk_ (publishable) key only identifies which client's agent answers — it
grants no API access, so it is safe to expose in page source. Audio flows over
WebRTC to the Pipecat runner's /api/offer endpoint on this same server; the
live transcript comes from /api/events polling.
"""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response

from src.platform.auth import client_for_publishable_key
from src.platform.public_api import _load_client

router = APIRouter(tags=["widget"])


WIDGET_JS = """
(function () {
  var script = document.currentScript;
  var key = script.getAttribute('data-key') || '';
  var base = script.src.replace(/\\/widget\\.js.*$/, '');
  var color = script.getAttribute('data-color') || '';
  var position = script.getAttribute('data-position') || '';
  if (!key) { console.warn('[voice-widget] missing data-key'); return; }

  var open = false, frame = null;

  var btn = document.createElement('button');
  btn.id = 'sorsco-voice-btn';
  btn.setAttribute('aria-label', 'Talk to us');
  btn.innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round"><path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v1a7 7 0 0 1-14 0v-1"/><line x1="12" y1="18" x2="12" y2="22"/></svg>';
  var side = (position === 'left') ? 'left:24px;' : 'right:24px;';
  btn.style.cssText = 'position:fixed;bottom:24px;' + side +
    'width:60px;height:60px;border-radius:50%;border:none;cursor:pointer;' +
    'background:' + (color || '#4f46e5') + ';box-shadow:0 8px 24px rgba(0,0,0,.28);' +
    'display:flex;align-items:center;justify-content:center;z-index:2147483000;' +
    'transition:transform .15s ease;';
  btn.onmouseenter = function () { btn.style.transform = 'scale(1.07)'; };
  btn.onmouseleave = function () { btn.style.transform = 'scale(1)'; };

  btn.onclick = function () {
    if (open) { close(); return; }
    frame = document.createElement('iframe');
    frame.src = base + '/embed?key=' + encodeURIComponent(key);
    frame.allow = 'microphone; autoplay';
    frame.style.cssText = 'position:fixed;bottom:96px;' + side +
      'width:380px;height:560px;max-width:calc(100vw - 32px);max-height:calc(100vh - 120px);' +
      'border:none;border-radius:18px;box-shadow:0 16px 48px rgba(0,0,0,.35);' +
      'z-index:2147483000;background:#0b1020;';
    document.body.appendChild(frame);
    open = true;
    btn.style.background = '#374151';
  };

  function close() {
    if (frame) { frame.remove(); frame = null; }
    open = false;
    btn.style.background = color || '#4f46e5';
  }
  window.addEventListener('message', function (e) {
    if (e.data === 'sorsco-voice-close') close();
  });

  document.body.appendChild(btn);
})();
"""


@router.get("/widget.js")
def widget_js():
    return Response(
        content=WIDGET_JS,
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=3600",
                 "Access-Control-Allow-Origin": "*"},
    )


EMBED_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__BUSINESS__ — Voice Assistant</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:system-ui,-apple-system,'Segoe UI',sans-serif; background:#0b1020;
         color:#e5e7eb; height:100vh; display:flex; flex-direction:column; overflow:hidden; }
  header { padding:16px 18px; background:linear-gradient(135deg,__COLOR__,#1f2937);
           display:flex; align-items:center; gap:12px; }
  .avatar { width:42px; height:42px; border-radius:50%; background:rgba(255,255,255,.18);
            display:flex; align-items:center; justify-content:center; font-weight:700;
            font-size:19px; color:#fff; }
  header .who b { display:block; font-size:15px; color:#fff; }
  header .who span { font-size:12px; color:rgba(255,255,255,.75); }
  #close { margin-left:auto; background:none; border:none; color:rgba(255,255,255,.8);
           font-size:22px; cursor:pointer; line-height:1; }
  main { flex:1; display:flex; flex-direction:column; align-items:center;
         justify-content:center; gap:18px; padding:20px; text-align:center; }
  #status { font-size:14px; color:#9ca3af; min-height:20px; }
  #orb { width:120px; height:120px; border-radius:50%; cursor:pointer; border:none;
         background:radial-gradient(circle at 35% 30%, __COLOR__, #111827);
         box-shadow:0 0 0 0 rgba(99,102,241,.4); display:flex; align-items:center;
         justify-content:center; transition:box-shadow .3s; }
  #orb.live { animation:pulse 1.6s infinite; }
  @keyframes pulse {
    0% { box-shadow:0 0 0 0 rgba(99,102,241,.45); }
    70% { box-shadow:0 0 0 26px rgba(99,102,241,0); }
    100% { box-shadow:0 0 0 0 rgba(99,102,241,0); } }
  #orb svg { width:44px; height:44px; }
  #captions { min-height:72px; max-height:130px; overflow-y:auto; font-size:14px;
              line-height:1.5; width:100%; }
  .cap-user { color:#93c5fd; }
  .cap-agent { color:#e5e7eb; }
  footer { padding:8px; text-align:center; font-size:11px; color:#4b5563; }
  footer a { color:#6b7280; }
</style>
</head>
<body>
<header>
  <div class="avatar">__INITIAL__</div>
  <div class="who"><b>__AGENT__</b><span>__BUSINESS__</span></div>
  <button id="close" aria-label="Close">&times;</button>
</header>
<main>
  <div id="status">__GREETING__</div>
  <button id="orb" aria-label="Start call">
    <svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round">
      <path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/>
      <path d="M19 10v1a7 7 0 0 1-14 0v-1"/><line x1="12" y1="18" x2="12" y2="22"/>
    </svg>
  </button>
  <div id="captions"></div>
</main>
<footer>__BRANDING__</footer>
<audio id="remote" autoplay></audio>
<script>
var pc = null, live = false, evtSeen = 0, pollTimer = null;
var orb = document.getElementById('orb'), statusEl = document.getElementById('status');
var captions = document.getElementById('captions');

document.getElementById('close').onclick = function () {
  hangup(); parent.postMessage('sorsco-voice-close', '*');
};
orb.onclick = function () { live ? hangup() : connect(); };

async function connect() {
  statusEl.textContent = 'Asking for microphone...';
  try {
    var mic = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) { statusEl.textContent = 'Microphone blocked — allow it and retry.'; return; }
  statusEl.textContent = 'Connecting...';
  pc = new RTCPeerConnection();
  mic.getTracks().forEach(function (t) { pc.addTrack(t, mic); });
  pc.addTransceiver('audio', { direction: 'recvonly' });
  pc.ontrack = function (e) { document.getElementById('remote').srcObject = e.streams[0]; };
  pc.onconnectionstatechange = function () {
    if (pc && (pc.connectionState === 'failed' || pc.connectionState === 'disconnected')) hangup();
  };
  var offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  await new Promise(function (res) {
    if (pc.iceGatheringState === 'complete') return res();
    pc.onicegatheringstatechange = function () {
      if (pc.iceGatheringState === 'complete') res();
    };
    setTimeout(res, 2000);
  });
  try {
    var r = await fetch('/api/offer', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sdp: pc.localDescription.sdp, type: pc.localDescription.type })
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    var answer = await r.json();
    await pc.setRemoteDescription(answer);
  } catch (e) {
    statusEl.textContent = 'Could not connect — please try again shortly.';
    hangup(); return;
  }
  live = true;
  orb.classList.add('live');
  statusEl.textContent = 'Connected — start speaking';
  captions.innerHTML = '';
  fetch('/api/events').then(function (r) { return r.json(); })
    .then(function (d) { evtSeen = d.count || 0; startPolling(); });
}

function startPolling() {
  pollTimer = setInterval(async function () {
    if (!live) return;
    try {
      var d = await (await fetch('/api/events?since=' + evtSeen)).json();
      evtSeen = d.count;
      (d.events || []).forEach(function (e) {
        if (e.type !== 'user' && e.type !== 'assistant') return;
        var div = document.createElement('div');
        div.className = e.type === 'user' ? 'cap-user' : 'cap-agent';
        div.textContent = (e.type === 'user' ? 'You: ' : '__AGENT__: ') + e.text;
        captions.appendChild(div);
        captions.scrollTop = captions.scrollHeight;
      });
    } catch (e) { /* transient */ }
  }, 1200);
}

function hangup() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  if (pc) { try { pc.close(); } catch (e) {} pc = null; }
  live = false;
  orb.classList.remove('live');
  statusEl.textContent = 'Call ended. Tap to talk again.';
}
</script>
</body>
</html>"""


@router.get("/embed", response_class=HTMLResponse)
def embed(key: str = ""):
    client_id = client_for_publishable_key(key)
    if not client_id:
        raise HTTPException(403, "Invalid widget key")
    try:
        cfg = _load_client(client_id)
    except HTTPException:
        raise HTTPException(403, "Widget key points to a deleted agent")
    widget = cfg.get("widget") or {}
    agent = cfg.get("agent_name", "Assistant")
    business = cfg.get("business_name", "")
    branding = (
        "" if widget.get("hide_branding")
        else 'Powered by <a href="https://sorsco.in" target="_blank" rel="noopener">Sorsco Voice</a>'
    )
    page = (
        EMBED_PAGE
        .replace("__AGENT__", json.dumps(agent)[1:-1])
        .replace("__BUSINESS__", json.dumps(business)[1:-1])
        .replace("__INITIAL__", (agent[:1] or "A").upper())
        .replace("__COLOR__", widget.get("color") or "#4f46e5")
        .replace("__GREETING__", widget.get("greeting") or "Tap the mic and start talking")
        .replace("__BRANDING__", branding)
    )
    # Arm the runner so the next /api/offer session answers as THIS client.
    from src.admin import ACTIVE_FILE

    ACTIVE_FILE.parent.mkdir(exist_ok=True)
    ACTIVE_FILE.write_text(client_id, encoding="utf-8")
    return page
