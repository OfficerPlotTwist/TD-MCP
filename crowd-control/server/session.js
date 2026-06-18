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
    this.currentCode = null;             // set in Task 6
    this.lastCodeRotate = 0;
    // clientId -> slot remembered briefly so reconnects keep their slot until reused
    this._stickySlots = new Map();
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

  disconnect(connId, now) {
    const client = this.clients.get(connId);
    if (!client) return { wasMaster: false };
    let wasMaster = false;
    if (client.slot != null && this.slots[client.slot] === connId) this.slots[client.slot] = null;
    // master release handled in Task 5 override of this method
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
}

export function randomCode() {
  const A = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  let s = '';
  for (let i = 0; i < 3; i++) s += A[Math.floor(Math.random() * 26)];
  return s;
}
