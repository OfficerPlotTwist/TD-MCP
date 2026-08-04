const vid = document.getElementById('vid');
const stage = document.getElementById('stage');
const overlay = document.getElementById('overlay');
const ctx = overlay.getContext('2d');
let mode = 'param';          // param | network | pair
let pendingPair = null;      // {pairId, opCaptureId} while awaiting param box
let drag = null;

function fps() {
  return parseFloat(document.getElementById('fps').value) || 30;
}

function fitOverlay() {
  const sw = stage.clientWidth, sh = stage.clientHeight;
  const aspect = (vid.videoWidth / vid.videoHeight) || (16 / 9);
  let w = sw, h = sw / aspect;
  if (h > sh) { h = sh; w = sh * aspect; }
  overlay.width = w;
  overlay.height = h;
  overlay.style.width = w + 'px';
  overlay.style.height = h + 'px';
  overlay.style.left = ((sw - w) / 2) + 'px';
  overlay.style.top = ((sh - h) / 2) + 'px';
}
vid.addEventListener('loadedmetadata', fitOverlay);
window.addEventListener('resize', fitOverlay);

setInterval(() => {
  document.getElementById('time').textContent =
    vid.currentTime.toFixed(2) + 's / ' + (vid.duration || 0).toFixed(1) + 's';
}, 200);

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT') return;
  if (e.code === 'Space') {
    e.preventDefault();
    if (vid.paused) vid.play(); else vid.pause();
  } else if (e.key === 'ArrowLeft') vid.currentTime -= 5;
  else if (e.key === 'ArrowRight') vid.currentTime += 5;
  else if (e.key === ',') { vid.pause(); vid.currentTime -= 1 / fps(); }
  else if (e.key === '.') { vid.pause(); vid.currentTime += 1 / fps(); }
  else if (e.key === '1') setMode('param');
  else if (e.key === '2') setMode('network');
  else if (e.key === '3') setMode('pair');
  else if (e.key === '4') setMode('network-whole');
  else if (e.key === 'Escape') cancelPair();
});

function setMode(m) { mode = m; pendingPair = null; updateModeLabel(); }

function updateModeLabel() {
  document.querySelectorAll('#legend button').forEach(b => {
    b.classList.toggle('active', b.dataset.mode === mode);
  });
  document.getElementById('pairhint').textContent =
    pendingPair ? 'now box the PARAM window' :
    (mode === 'pair' ? 'box the OP node first' : '');
}

document.querySelectorAll('#legend button').forEach(b => {
  b.onclick = () => setMode(b.dataset.mode);
});
updateModeLabel();

async function cancelPair() {
  if (!pendingPair) return;
  await fetch('/delete', {
    method: 'POST',
    body: JSON.stringify({id: pendingPair.opCaptureId})
  });
  pendingPair = null;
  updateModeLabel();
  refresh();
}

overlay.addEventListener('mousedown', e => {
  vid.pause();
  drag = {x: e.offsetX, y: e.offsetY};
});

function overlayPoint(e) {
  const r = overlay.getBoundingClientRect();
  return {
    x: Math.min(Math.max(e.clientX - r.left, 0), overlay.width),
    y: Math.min(Math.max(e.clientY - r.top, 0), overlay.height)
  };
}

document.addEventListener('mousemove', e => {
  if (!drag) return;
  const p = overlayPoint(e);
  ctx.clearRect(0, 0, overlay.width, overlay.height);
  ctx.strokeStyle = '#0f0';
  ctx.lineWidth = 2;
  ctx.strokeRect(drag.x, drag.y, p.x - drag.x, p.y - drag.y);
});

document.addEventListener('mouseup', async e => {
  if (!drag) return;
  const p = overlayPoint(e);
  const box = normBox(drag.x, drag.y, p.x, p.y);
  drag = null;
  ctx.clearRect(0, 0, overlay.width, overlay.height);
  if (box.w < 8 || box.h < 8) return;
  await capture(box);
});

function normBox(x0, y0, x1, y1) {
  return {x: Math.min(x0, x1), y: Math.min(y0, y1),
          w: Math.abs(x1 - x0), h: Math.abs(y1 - y0)};
}

async function capture(box) {
  const sx = vid.videoWidth / overlay.width;
  const sy = vid.videoHeight / overlay.height;
  const bbox = [Math.round(box.x * sx), Math.round(box.y * sy),
                Math.round(box.w * sx), Math.round(box.h * sy)];
  const full = document.createElement('canvas');
  full.width = vid.videoWidth;
  full.height = vid.videoHeight;
  full.getContext('2d').drawImage(vid, 0, 0);
  const crop = document.createElement('canvas');
  crop.width = bbox[2];
  crop.height = bbox[3];
  crop.getContext('2d').drawImage(full, bbox[0], bbox[1], bbox[2], bbox[3],
                                  0, 0, bbox[2], bbox[3]);
  let type = mode, role = null, pairId = null;
  if (mode === 'pair') {
    if (!pendingPair) { pairId = 'p' + Date.now(); role = 'op'; }
    else { pairId = pendingPair.pairId; role = 'param'; }
  }
  const res = await fetch('/capture', {method: 'POST', body: JSON.stringify({
    t: vid.currentTime, type, bbox, pairId, role,
    image: crop.toDataURL('image/png')})});
  const saved = await res.json();
  if (mode === 'pair') {
    pendingPair = pendingPair ? null : {pairId, opCaptureId: saved.id};
  }
  updateModeLabel();
  refresh();
}

async function refresh() {
  const caps = await (await fetch('/captures')).json();
  document.getElementById('count').textContent = caps.length;
  const list = document.getElementById('list');
  list.innerHTML = '';
  const TAGS = ['param', 'network', 'network-whole'];
  for (const c of caps.slice().reverse()) {
    const div = document.createElement('div');
    div.className = 'cap';
    const opts = TAGS.map(t =>
      '<option value="' + t + '"' + (c.type === t ? ' selected' : '') + '>' +
      t + '</option>').join('') +
      (c.type === 'pair'
        ? '<option value="pair" selected disabled>pair' +
          (c.role ? '/' + c.role : '') + '</option>' : '');
    div.innerHTML = '<img src="/crops/' + c.id + '.png"><div>' + c.id +
      ' @' + c.t.toFixed(1) + 's <select>' + opts +
      '</select> <button>x</button></div>';
    div.querySelector('select').onchange = async e => {
      await fetch('/retag', {method: 'POST',
                             body: JSON.stringify({id: c.id, type: e.target.value})});
      refresh();
    };
    div.querySelector('button').onclick = async () => {
      await fetch('/delete', {method: 'POST',
                              body: JSON.stringify({id: c.id})});
      refresh();
    };
    list.appendChild(div);
  }
}

document.getElementById('done').onclick = async () => {
  await fetch('/done', {method: 'POST', body: '{}'});
  document.getElementById('done').textContent = 'Done ✓ (agent notified)';
};

refresh();
