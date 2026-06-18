import { readFileSync } from 'node:fs';

const ROLES = new Set(['master', 'public']);
const TYPES = new Set(['slider', 'toggle']);

export function validateConfig(obj) {
  const errors = [];
  if (!obj || typeof obj !== 'object') return { ok: false, errors: ['config must be an object'] };

  if (typeof obj.show !== 'string' || !obj.show) errors.push('show must be a non-empty string');
  if (!Number.isInteger(obj.slotCap) || obj.slotCap < 1) errors.push('slotCap must be a positive integer');

  const controls = Array.isArray(obj.controls) ? obj.controls : null;
  if (!controls) errors.push('controls must be an array');

  const ids = new Set();
  for (const c of controls || []) {
    if (!c || typeof c.id !== 'string') { errors.push('each control needs a string id'); continue; }
    if (ids.has(c.id)) errors.push(`duplicate control id: ${c.id}`);
    ids.add(c.id);
    if (!TYPES.has(c.type)) errors.push(`control ${c.id}: type must be slider|toggle`);
    if (!ROLES.has(c.role)) errors.push(`control ${c.id}: role must be master|public`);
    if (typeof c.label !== 'string') errors.push(`control ${c.id}: label must be a string`);
    if (c.type === 'slider') {
      if (typeof c.min !== 'number' || typeof c.max !== 'number' || c.max <= c.min)
        errors.push(`control ${c.id}: slider needs numeric min < max`);
    }
  }

  let grid = null;
  if (obj.grid != null) {
    const g = obj.grid;
    if (typeof g.id !== 'string') errors.push('grid.id must be a string');
    if (!ROLES.has(g.role)) errors.push('grid.role must be master|public');
    grid = { id: g.id, role: g.role, perGuest: g.perGuest !== false };
    if (ids.has(g.id)) errors.push(`grid id collides with a control id: ${g.id}`);
    ids.add(g.id);
  }

  const signals = Array.isArray(obj.signals) ? obj.signals : [];
  for (const s of signals) {
    if (!s || typeof s.id !== 'string') { errors.push('each signal needs a string id'); continue; }
    if (ids.has(s.id)) errors.push(`duplicate id (signal): ${s.id}`);
    ids.add(s.id);
    if (!ROLES.has(s.role)) errors.push(`signal ${s.id}: role must be master|public`);
  }

  if (errors.length) return { ok: false, errors };
  return {
    ok: true,
    config: {
      show: obj.show,
      slotCap: obj.slotCap,
      controls: controls.map((c) => ({
        id: c.id, type: c.type, label: c.label, role: c.role,
        ...(c.type === 'slider' ? { min: c.min, max: c.max } : {}),
      })),
      grid,
      signals: signals.map((s) => ({ id: s.id, label: s.label ?? s.id, role: s.role })),
    },
  };
}

export function loadConfig(path) {
  const raw = JSON.parse(readFileSync(path, 'utf8'));
  const r = validateConfig(raw);
  if (!r.ok) throw new Error(`Invalid show config (${path}):\n  - ${r.errors.join('\n  - ')}`);
  return r.config;
}
