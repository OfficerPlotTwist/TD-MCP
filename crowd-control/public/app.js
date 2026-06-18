// crowd-control/public/app.js
import { visibleControls, gridVisible, lockoutSeconds } from '/ui-logic.js';

const $ = (id) => document.getElementById(id);
const clientId = (() => {
  let v = localStorage.getItem('cc-client-id');
  if (!v) { v = 'u' + Math.random().toString(36).slice(2, 10); localStorage.setItem('cc-client-id', v); }
  return v;
})();

let ws, config = null, role = 'guest';

function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/`);
  ws.onopen = () => { $('status').textContent = 'online'; ws.send(JSON.stringify({ type: 'hello', clientId })); };
  ws.onclose = () => { $('status').textContent = 'reconnecting…'; setTimeout(connect, 1000); };
  ws.onmessage = (e) => onMessage(JSON.parse(e.data));
}

function send(obj) { if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj)); }

function onMessage(m) {
  switch (m.type) {
    case 'welcome': config = m.config; setRole(m.role); break;
    case 'role': setRole(m.role); break;
    case 'bumped': flash('You lost master control'); break;
    case 'state': $('status').textContent = m.masterPresent ? 'online · master active' : 'online'; break;
    case 'error':
      if (m.code === 'locked') $('pair-msg').textContent = `Master locked — ${lockoutSeconds(m.retryInMs)}s`;
      else if (m.code === 'badcode') $('pair-msg').textContent = 'Wrong code';
      break;
  }
}

function setRole(r) { role = r; $('role-badge').textContent = r; render(); }

function render() {
  if (!config) return;
  // controls
  const host = $('controls'); host.innerHTML = '';
  for (const c of visibleControls(config, role)) host.appendChild(renderControl(c));
  // grid
  const canvas = $('grid');
  canvas.hidden = !gridVisible(config, role);
  if (!canvas.hidden) setupGrid(canvas);
  // signals (public to guests + master)
  const sigHost = $('signals'); sigHost.innerHTML = '';
  if (role !== 'spectator') for (const s of config.signals || []) {
    if (role === 'guest' && s.role !== 'public') continue;
    const b = document.createElement('button'); b.textContent = s.label; b.className = 'signal';
    b.onclick = () => send({ type: 'signal', id: s.id });
    sigHost.appendChild(b);
  }
}

function renderControl(c) {
  const wrap = document.createElement('label'); wrap.className = 'control';
  wrap.append(c.label);
  if (c.type === 'slider') {
    const input = document.createElement('input');
    input.type = 'range'; input.min = c.min; input.max = c.max; input.step = (c.max - c.min) / 1000;
    input.value = (c.min + c.max) / 2;
    input.oninput = throttle(() => send({ type: 'control', id: c.id, v: Number(input.value) }), 33);
    wrap.appendChild(input);
  } else {
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.onchange = () => send({ type: 'control', id: c.id, v: input.checked });
    wrap.appendChild(input);
  }
  return wrap;
}

function setupGrid(canvas) {
  const fit = () => { canvas.width = canvas.clientWidth; canvas.height = canvas.clientHeight; };
  fit(); window.onresize = fit;
  const sendXY = throttle((x, y) => send({ type: 'grid', x, y }), 33);
  const onMove = (ev) => {
    const t = ev.touches ? ev.touches[0] : ev;
    const r = canvas.getBoundingClientRect();
    const x = (t.clientX - r.left) / r.width;
    const y = 1 - (t.clientY - r.top) / r.height; // bottom-left origin to match TD
    sendXY(Math.min(1, Math.max(0, x)), Math.min(1, Math.max(0, y)));
    ev.preventDefault();
  };
  canvas.ontouchmove = onMove; canvas.ontouchstart = onMove;
  canvas.onpointermove = (e) => { if (e.pressure > 0 || e.buttons) onMove(e); };
}

function throttle(fn, ms) {
  let last = 0, pending = null;
  return (...a) => {
    const t = performance.now();
    if (t - last >= ms) { last = t; fn(...a); }
    else { clearTimeout(pending); pending = setTimeout(() => { last = performance.now(); fn(...a); }, ms - (t - last)); }
  };
}

function flash(msg) { $('pair-msg').textContent = msg; setTimeout(() => { if ($('pair-msg').textContent === msg) $('pair-msg').textContent = ''; }, 2000); }

$('seize').onclick = () => { $('pair-form').hidden = !$('pair-form').hidden; $('code').focus(); };
$('pair-form').onsubmit = (e) => {
  e.preventDefault();
  const code = $('code').value.toUpperCase().slice(0, 3);
  send({ type: 'pair', code });
};

connect();
