const DEFAULTS = {
  seizeLockMs: 15000,
  idleReleaseMs: 120000,
  hardCapMs: 1800000,
  codeRotateIdleMs: 60000,
};

export class Session {
  constructor(config, opts = {}) {
    this.config = config;
    this.opts = { ...DEFAULTS, ...opts };
    this.codeGen = opts.codeGen || (() => randomCode());
    this.clients = new Map();            // connId -> { connId, clientId, slot, role }
    this.slots = new Array(config.slotCap + 1).fill(null); // [0]=master slot, 1..slotCap guests
    this.master = null;                  // set in Task 5: { connId, since, lastActivity, seizeLockUntil }
    this.currentCode = this.codeGen();
    this.lastCodeRotate = 0;
    // clientId -> slot remembered briefly so reconnects keep their slot until reused
    this._stickySlots = new Map();
    this.values = {}; // slot -> { controlId: value }
    this.grid = {};   // slot -> { x, y }
    this._controlsById = new Map(config.controls.map((c) => [c.id, c]));
    this._signalsById = new Map((config.signals || []).map((s) => [s.id, s]));
  }

  _freeGuestSlot() {
    for (let i = 1; i <= this.config.slotCap; i++) if (this.slots[i] === null) return i;
    return null;
  }

  connect(connId, clientId, now) {
    // Reuse a remembered slot if still free.
    let slot = null;
    const remembered = this._stickySlots.get(clientId);
    if (remembered && this.slots[remembered] === null) slot = remembered;
    else slot = this._freeGuestSlot();

    if (slot === null) {
      const client = { connId, clientId, slot: null, role: 'spectator' };
      this.clients.set(connId, client);
      return { role: 'spectator', slot: null, masterPresent: !!this.master };
    }

    this.slots[slot] = connId;
    this._stickySlots.set(clientId, slot);
    const client = { connId, clientId, slot, role: 'guest' };
    this.clients.set(connId, client);
    return { role: 'guest', slot, masterPresent: !!this.master };
  }

  roleOf(connId) {
    const c = this.clients.get(connId);
    return c ? c.role : null;
  }

  _rotateCode(now) {
    this.currentCode = this.codeGen();
    this.lastCodeRotate = now;
  }

  pair(connId, code, now) {
    const client = this.clients.get(connId);
    if (!client) return { granted: false, error: { code: 'noclient', message: 'not connected' } };

    if (this.master && now < this.master.seizeLockUntil) {
      return { granted: false, error: { code: 'locked', message: 'master locked', retryInMs: this.master.seizeLockUntil - now } };
    }
    if (code !== this.currentCode) {
      return { granted: false, error: { code: 'badcode', message: 'wrong code' } };
    }

    let bumpedConnId;
    if (this.master && this.master.connId !== connId) {
      bumpedConnId = this.master.connId;
      const prev = this.clients.get(bumpedConnId);
      this.slots[0] = null;
      if (prev) {
        const g = this._freeGuestSlot();
        if (g !== null) { this._clearSlotData(prev.slot); this.slots[g] = bumpedConnId; prev.slot = g; prev.role = 'guest'; this._stickySlots.set(prev.clientId, g); }
        else { this._clearSlotData(prev.slot); prev.slot = null; prev.role = 'spectator'; }
      }
    }

    // free this client's old guest slot, move to master slot 0
    if (client.slot != null && this.slots[client.slot] === connId) { this._clearSlotData(client.slot); this.slots[client.slot] = null; }
    this.slots[0] = connId;
    client.slot = 0;
    client.role = 'master';
    this.master = { connId, since: now, lastActivity: now, seizeLockUntil: now + this.opts.seizeLockMs };
    this._rotateCode(now);
    return { granted: true, code: this.currentCode, bumpedConnId };
  }

  disconnect(connId, now) {
    const client = this.clients.get(connId);
    if (!client) return { wasMaster: false };
    let wasMaster = false;
    if (this.master && this.master.connId === connId) {
      wasMaster = true;
      this.master = null;
      this.slots[0] = null;
      this._rotateCode(now);
    } else if (client.slot != null && this.slots[client.slot] === connId) {
      this.slots[client.slot] = null;
    }
    this._clearSlotData(client.slot);
    this.clients.delete(connId);
    return { wasMaster };
  }

  guestCount() {
    let n = 0;
    for (let i = 1; i <= this.config.slotCap; i++) if (this.slots[i] !== null) n++;
    return n;
  }

  slotsUsed() {
    return this.guestCount() + (this.slots[0] ? 1 : 0);
  }

  _authorized(connId, role) {
    const c = this.clients.get(connId);
    if (!c || c.role === 'spectator' || c.slot == null) return false;
    if (role === 'master') return c.role === 'master';
    // public: master or guest
    return c.role === 'master' || c.role === 'guest';
  }

  _bumpIfMaster(connId, now) {
    if (this.master && this.master.connId === connId) this.master.lastActivity = now;
  }

  applyControl(connId, id, v, now) {
    const ctrl = this._controlsById.get(id);
    if (!ctrl) return { ok: false, error: { code: 'badcontrol', message: `unknown control ${id}` } };
    if (!this._authorized(connId, ctrl.role)) return { ok: false, error: { code: 'forbidden', message: 'not allowed' } };
    const slot = this.clients.get(connId).slot;
    (this.values[slot] ||= {})[id] = v;
    this._bumpIfMaster(connId, now);
    return { ok: true };
  }

  applyGrid(connId, x, y, now) {
    const g = this.config.grid;
    if (!g) return { ok: false, error: { code: 'badcontrol', message: 'no grid configured' } };
    if (!this._authorized(connId, g.role)) return { ok: false, error: { code: 'forbidden', message: 'not allowed' } };
    const slot = this.clients.get(connId).slot;
    this.grid[slot] = { x, y };
    this._bumpIfMaster(connId, now);
    return { ok: true };
  }

  applySignal(connId, id, now) {
    const sig = this._signalsById.get(id);
    if (!sig) return { ok: false, error: { code: 'badsignal', message: `unknown signal ${id}` } };
    if (!this._authorized(connId, sig.role)) return { ok: false, error: { code: 'forbidden', message: 'not allowed' } };
    const slot = this.clients.get(connId).slot;
    this._bumpIfMaster(connId, now);
    return { ok: true, slot };
  }

  _clearSlotData(slot) {
    if (slot == null) return;
    delete this.values[slot];
    delete this.grid[slot];
  }
}

export function randomCode() {
  const A = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  let s = '';
  for (let i = 0; i < 3; i++) s += A[Math.floor(Math.random() * 26)];
  return s;
}
