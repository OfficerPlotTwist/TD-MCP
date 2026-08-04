function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
}

async function load() {
  const caps = await (await fetch('/captures')).json();
  const readings = await (await fetch('/readings')).json();
  const holder = document.getElementById('items');
  let shown = 0;
  for (const c of caps) {
    const r = readings[c.id];
    if (!r || r.kind !== 'param') continue;
    shown++;
    const boxes = r.boxes || {};
    let rows = '';
    for (const [p, v] of Object.entries(r.params || {})) {
      rows += '<tr><td>' + esc(p) + '</td><td>' + esc(v) + '</td><td>' +
              (boxes[p] ? 'masked' : '—') + '</td></tr>';
    }
    const item = document.createElement('div');
    item.className = 'item';
    item.innerHTML = '<h4>' + esc(r.opName) + ' <small>' +
      esc(r.opType || '?') + ' — ' + c.id + ' @' + c.t.toFixed(1) +
      's</small></h4><div class="shot"><img src="/crops/' + c.id +
      '.png"></div><table><tr><th>param</th><th>OCR value</th><th>mask</th>' +
      '</tr>' + rows + '</table>';
    holder.appendChild(item);
    const img = item.querySelector('img');
    img.onload = () => {
      const shot = item.querySelector('.shot');
      const sx = img.clientWidth / img.naturalWidth;
      const sy = img.clientHeight / img.naturalHeight;
      for (const [p, b] of Object.entries(boxes)) {
        const m = document.createElement('div');
        m.className = 'mask';
        m.style.left = (b[0] * sx) + 'px';
        m.style.top = (b[1] * sy) + 'px';
        m.style.width = (b[2] * sx) + 'px';
        m.style.height = (b[3] * sy) + 'px';
        m.title = p + ' = ' + r.params[p];
        shot.appendChild(m);
      }
    };
  }
  if (!shown) {
    holder.innerHTML = '<em>no param-window readings yet</em>';
  }
}

load();
