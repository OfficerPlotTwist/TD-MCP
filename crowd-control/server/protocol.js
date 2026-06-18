const clamp01 = (n) => (n < 0 ? 0 : n > 1 ? 1 : n);
const isNum = (n) => typeof n === 'number' && Number.isFinite(n);
const isStr = (s) => typeof s === 'string' && s.length > 0;

export function parseInbound(raw) {
  let m;
  try { m = JSON.parse(raw); } catch { return { ok: false, error: 'malformed json' }; }
  if (!m || typeof m !== 'object') return { ok: false, error: 'not an object' };

  switch (m.type) {
    case 'hello':
      if (!isStr(m.clientId)) return { ok: false, error: 'hello.clientId required' };
      return { ok: true, msg: { type: 'hello', clientId: m.clientId.slice(0, 64) } };
    case 'pair':
      if (!isStr(m.code)) return { ok: false, error: 'pair.code required' };
      return { ok: true, msg: { type: 'pair', code: m.code.toUpperCase().slice(0, 3) } };
    case 'control':
      if (!isStr(m.id)) return { ok: false, error: 'control.id required' };
      if (!(isNum(m.v) || typeof m.v === 'boolean')) return { ok: false, error: 'control.v must be number|boolean' };
      return { ok: true, msg: { type: 'control', id: m.id.slice(0, 64), v: m.v } };
    case 'grid':
      if (!isNum(m.x) || !isNum(m.y)) return { ok: false, error: 'grid.x/y must be numbers' };
      return { ok: true, msg: { type: 'grid', x: clamp01(m.x), y: clamp01(m.y) } };
    case 'signal':
      if (!isStr(m.id)) return { ok: false, error: 'signal.id required' };
      return { ok: true, msg: { type: 'signal', id: m.id.slice(0, 64) } };
    case 'ping':
      return { ok: true, msg: { type: 'ping' } };
    default:
      return { ok: false, error: `unknown type: ${m.type}` };
  }
}

export const welcome = ({ clientId, role, slot, config, masterPresent }) =>
  ({ type: 'welcome', clientId, role, slot, config, masterPresent });
export const roleMsg = ({ role, slot }) => ({ type: 'role', role, slot });
export const bumped = () => ({ type: 'bumped' });
export const stateMsg = ({ masterPresent, guestCount, slotsUsed }) =>
  ({ type: 'state', masterPresent, guestCount, slotsUsed });
export const errorMsg = (code, message, extra = {}) => ({ type: 'error', code, message, ...extra });
