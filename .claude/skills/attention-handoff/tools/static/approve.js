let graph = null;
let selected = null;    // op id
let wireMode = null;    // null | 'pick-src' | {from: opId}

const NW = 150, NH = 46, GX = 210, GY = 70;

async function load() {
  graph = await (await fetch('/graph')).json();
  graph.ops = graph.ops || [];
  graph.wires = graph.wires || [];
  graph.conflicts = graph.conflicts || [];
  const dl = document.getElementById('optypes');
  for (const t of graph.opTypes || []) {
    const o = document.createElement('option');
    o.value = t;
    dl.appendChild(o);
  }
  render();
}

function depths() {
  const d = {}, incoming = {};
  for (const o of graph.ops) { d[o.id] = 0; incoming[o.id] = []; }
  for (const w of graph.wires) {
    if (incoming[w.to] !== undefined && d[w.from] !== undefined) {
      incoming[w.to].push(w.from);
    }
  }
  for (let i = 0; i < graph.ops.length; i++) {   // relaxation, cycle-safe
    let changed = false;
    for (const o of graph.ops) {
      for (const src of incoming[o.id]) {
        if (d[src] + 1 > d[o.id]) { d[o.id] = d[src] + 1; changed = true; }
      }
    }
    if (!changed) break;
  }
  return d;
}

function layout() {
  const d = depths(), rows = {}, pos = {};
  for (const o of graph.ops) {
    const col = d[o.id];
    rows[col] = rows[col] || 0;
    pos[o.id] = {x: 30 + col * GX, y: 30 + rows[col] * GY};
    rows[col]++;
  }
  return pos;
}

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                  .replace(/"/g, '&quot;');
}

function hasConflict(opId) {
  return graph.conflicts.some(c => (c.detail || '').includes(opId));
}

function banner(msg) { document.getElementById('banner').textContent = msg; }

function render() {
  document.getElementById('counts').textContent =
    graph.ops.length + ' ops · ' + graph.wires.length + ' wires';
  renderSvg();
  renderInspector();
  renderConflicts();
  renderParams();
}

function renderSvg() {
  const pos = layout();
  const xs = Object.values(pos).map(p => p.x);
  const ys = Object.values(pos).map(p => p.y);
  const w = (xs.length ? Math.max(...xs) : 0) + NW + 40;
  const h = (ys.length ? Math.max(...ys) : 0) + NH + 40;
  let s = '<svg width="' + w + '" height="' + h +
          '" xmlns="http://www.w3.org/2000/svg">';
  graph.wires.forEach((wire, i) => {
    const a = pos[wire.from], b = pos[wire.to];
    if (!a || !b) return;
    const x1 = a.x + NW, y1 = a.y + NH / 2, x2 = b.x, y2 = b.y + NH / 2;
    s += '<path class="wire" data-wire="' + i + '" d="M' + x1 + ',' + y1 +
         ' C' + (x1 + 60) + ',' + y1 + ' ' + (x2 - 60) + ',' + y2 +
         ' ' + x2 + ',' + y2 + '"/>';
  });
  for (const o of graph.ops) {
    const p = pos[o.id];
    const cls = 'node' + (o.id === selected ? ' sel' : '') +
                (hasConflict(o.id) ? ' conflict' : '');
    s += '<g class="' + cls + '" data-op="' + esc(o.id) + '">' +
         '<rect x="' + p.x + '" y="' + p.y + '" width="' + NW +
         '" height="' + NH + '" rx="6"/>' +
         '<text x="' + (p.x + 8) + '" y="' + (p.y + 19) + '">' +
         esc(o.id) + '</text>' +
         '<text x="' + (p.x + 8) + '" y="' + (p.y + 37) + '" class="typ">' +
         esc(o.opType || '?') + '</text></g>';
  }
  s += '</svg>';
  const holder = document.getElementById('diagram');
  holder.innerHTML = s;
  holder.querySelectorAll('g.node').forEach(g => {
    g.onclick = () => clickNode(g.dataset.op);
  });
  holder.querySelectorAll('path.wire').forEach(p => {
    p.onclick = () => {
      if (confirm('Delete this wire?')) {
        graph.wires.splice(+p.dataset.wire, 1);
        render();
      }
    };
  });
}

function clickNode(id) {
  if (wireMode === 'pick-src') {
    wireMode = {from: id};
    banner('now click the target op');
    return;
  }
  if (wireMode && wireMode.from) {
    const inlet = parseInt(prompt('Target inlet index?', '0') || '0', 10);
    graph.wires.push({from: wireMode.from, to: id, toInlet: inlet,
                      sources: ['manual']});
    wireMode = null;
    banner('');
    render();
    return;
  }
  selected = id;
  render();
}

function renderInspector() {
  const el = document.getElementById('inspector');
  const op = graph.ops.find(o => o.id === selected);
  if (!op) { el.innerHTML = '<em>click a node</em>'; return; }
  el.innerHTML = '<b>' + esc(op.id) + '</b><br>' +
    'name <input id="i-name" value="' + esc(op.id) + '"><br>' +
    'type <input id="i-type" list="optypes" value="' + esc(op.opType) +
    '"><br><button id="i-del">delete op</button>';
  document.getElementById('i-name').onchange = e => {
    const old = op.id, next = e.target.value.trim();
    if (!next) return;
    op.id = next;
    for (const w of graph.wires) {
      if (w.from === old) w.from = next;
      if (w.to === old) w.to = next;
    }
    selected = next;
    render();
  };
  document.getElementById('i-type').onchange = e => {
    op.opType = e.target.value.trim();
    render();
  };
  document.getElementById('i-del').onclick = () => {
    graph.ops = graph.ops.filter(o => o !== op);
    graph.wires = graph.wires.filter(w => w.from !== op.id && w.to !== op.id);
    selected = null;
    render();
  };
}

function renderConflicts() {
  const el = document.getElementById('conflicts');
  if (!graph.conflicts.length) {
    el.innerHTML = '<em>no conflicts</em>';
    return;
  }
  el.innerHTML = graph.conflicts.map((c, i) =>
    '<div class="cf">[' + esc(c.kind) + '] ' + esc(c.detail) +
    ' <button data-i="' + i + '">resolved</button></div>').join('');
  el.querySelectorAll('button').forEach(b => {
    b.onclick = () => { graph.conflicts.splice(+b.dataset.i, 1); render(); };
  });
}

function renderParams() {
  const el = document.getElementById('params');
  let h = '<table><tr><th>op</th><th>param</th><th>value</th><th></th></tr>';
  for (const o of graph.ops) {
    for (const [p, slot] of Object.entries(o.params || {})) {
      const hist = (slot.history || [])
        .map(x => x.value + ' @' + x.t.toFixed(1) + 's').join(', ');
      h += '<tr class="' + (hist ? 'changed' : '') + '"><td>' + esc(o.id) +
           '</td><td>' + esc(p) + '</td><td><input data-op="' + esc(o.id) +
           '" data-par="' + esc(p) + '" value="' + esc(slot.value) +
           '"></td><td title="' + esc(hist) + '">' +
           (hist ? 'hist' : '') + '</td></tr>';
    }
  }
  el.innerHTML = h + '</table>';
  el.querySelectorAll('input').forEach(inp => {
    inp.onchange = e => {
      const o = graph.ops.find(x => x.id === inp.dataset.op);
      if (o) o.params[inp.dataset.par].value = e.target.value;
    };
  });
}

document.getElementById('addwire').onclick = () => {
  wireMode = 'pick-src';
  banner('click the source op');
};

document.getElementById('approve').onclick = async () => {
  graph.stats = {opCount: graph.ops.length, wireCount: graph.wires.length};
  await fetch('/approved', {method: 'POST', body: JSON.stringify(graph)});
  banner('Approved — agent is rebuilding.');
};

load();
