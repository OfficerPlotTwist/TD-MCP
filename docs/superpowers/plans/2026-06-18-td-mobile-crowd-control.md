# TD Mobile Crowd Control — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a mobile web frontend that lets a live crowd drive a TouchDesigner projection — one seizable "master" (3-letter projected code, last-wins, 15 s anti-thrash lock-out, 2-min/30-min release) plus a concurrent guest tier with per-slot channels — served by a featherweight Node control plane co-hosted on the Khadas with TD.

**Architecture:** A pure, IO-free **session state machine** (driven by explicit `now` timestamps) is the brain; a thin **ws server** wraps it with a real clock, routing, rate-limiting, and fanout. Phones connect over one WebSocket each and render their UI from a per-show config; TouchDesigner connects over **localhost** as a trusted `engine` client and writes per-slot snapshots into a Table DAT + the current code into a Text DAT. The existing MCP WebServer DAT on port 9980 is never touched.

**Tech Stack:** Node ≥ 20 (target v24), ESM, built-in `node:http` + `node:test` + `node:assert`, the `ws` library, vanilla-JS PWA (no framework), TouchDesigner WebSocket DAT (Python callbacks), Cloudflare Tunnel (ops only).

## Global Constraints

- **Spec of record:** `docs/superpowers/specs/2026-06-18-td-mobile-crowd-control-design.md`. Every task implements part of it.
- **Module system:** ESM only (`"type": "module"`); `import`/`export`, no `require`.
- **Node:** target v24.13 (installed); floor v20 (for stable built-in `node:test`).
- **Test runner:** built-in `node --test`; assertions via `node:assert/strict`. No Jest/Mocha/Vitest.
- **Runtime dependencies:** only `ws@^8`. No Express, no framework. Static files served by hand via `node:http`.
- **Purity rule:** `server/session.js`, `server/protocol.js`, `server/snapshot.js`, `server/ratelimit.js` MUST NOT call `Date.now()`, `Math.random()`, timers, or any IO. Time enters as a `now` (ms epoch) parameter; randomness enters via an injected `codeGen` function. This is what makes the timers testable.
- **Slot model:** index **0 is the reserved master slot**; guest slots are indices **1..slotCap**. `slotCap` (default **24**) is the max concurrent *guest* slots and does NOT include slot 0.
- **Timer defaults (ms):** `seizeLockMs=15000`, `idleReleaseMs=120000`, `hardCapMs=1800000`, `codeRotateIdleMs=60000`. Snapshot send rate `snapshotHz=60`; housekeeping tick `1` Hz.
- **Code format:** exactly 3 uppercase ASCII letters `A–Z`.
- **Message type names (verbatim):** inbound `hello`, `pair`, `control`, `grid`, `signal`, `ping`; outbound-to-phone `welcome`, `role`, `bumped`, `state`, `error`; engine `snapshot`, `signal`. Roles: `master` | `guest` | `spectator`.
- **Never** add endpoints to or otherwise modify `touchdesigner/webserver_callbacks.py` (the 9980 MCP bridge). TD ingestion is a *separate* WebSocket DAT.
- **Commit discipline:** one commit per completed task (TDD: test → fail → implement → pass → commit).

---

## File Structure

```
crowd-control/
├─ package.json                  ESM, ws dep, test/start scripts
├─ README.md                     run + tunnel ops
├─ server/
│  ├─ config.js                  load + validate a show config JSON (pure-ish: reads file at startup)
│  ├─ protocol.js                parse/validate inbound, build outbound (PURE)
│  ├─ session.js                 the state machine: slots, roles, code, timers (PURE)
│  ├─ snapshot.js                build the TD engine snapshot from session state (PURE)
│  ├─ ratelimit.js               per-connection token bucket (PURE)
│  ├─ static.js                  safe static file serving from public/
│  ├─ wsServer.js                ws glue: connect→session, route, fanout, tick, engine auth
│  └─ index.js                   entry: load config, start http+ws, wire tick loop
├─ public/
│  ├─ index.html                 PWA shell
│  ├─ ui-logic.js                PURE UI decisions (visible controls per role, lockout countdown)
│  ├─ app.js                     ws client + DOM wiring
│  ├─ styles.css                 minimal styling (frontend-design pass comes later)
│  └─ manifest.webmanifest       installable PWA metadata
├─ shows/
│  └─ demo.json                  example show config
├─ test/
│  ├─ protocol.test.js
│  ├─ session.test.js
│  ├─ snapshot.test.js
│  ├─ ratelimit.test.js
│  ├─ static.test.js
│  ├─ ui-logic.test.js
│  └─ wsServer.integration.test.js
├─ tools/
│  ├─ mock-engine.js             connect as engine, pretty-print snapshots (format lock)
│  └─ fake-phones.js             open N phone sockets, drive traffic (load test)
└─ touchdesigner/
   └─ crowd_ws_callbacks.py      WebSocket DAT callbacks: snapshot → Table DAT + code Text DAT
```

---

## Task 1: Project scaffold

**Files:**
- Create: `crowd-control/package.json`
- Create: `crowd-control/shows/demo.json`
- Create: `crowd-control/test/smoke.test.js`

**Interfaces:**
- Consumes: nothing.
- Produces: an installable package where `npm test` runs `node --test`; the example show config `shows/demo.json` consumed by Task 2.

- [ ] **Step 1: Write the smoke test**

```js
// crowd-control/test/smoke.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';

test('test runner works', () => {
  assert.equal(1 + 1, 2);
});
```

- [ ] **Step 2: Create package.json**

```json
{
  "name": "crowd-control",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "engines": { "node": ">=20" },
  "scripts": {
    "start": "node server/index.js",
    "test": "node --test",
    "mock-engine": "node tools/mock-engine.js",
    "fake-phones": "node tools/fake-phones.js"
  },
  "dependencies": {
    "ws": "^8.18.0"
  }
}
```

- [ ] **Step 3: Create the example show config**

```json
{
  "show": "demo",
  "slotCap": 24,
  "controls": [
    { "id": "speed", "type": "slider", "label": "Speed", "min": 0, "max": 1, "role": "master" },
    { "id": "glow",  "type": "toggle", "label": "Glow", "role": "master" },
    { "id": "hue",   "type": "slider", "label": "Color", "min": 0, "max": 1, "role": "public" }
  ],
  "grid": { "id": "xy", "perGuest": true, "role": "public" },
  "signals": [ { "id": "burst", "label": "✦", "role": "public" } ]
}
```

- [ ] **Step 4: Install deps and run the test**

Run: `cd crowd-control && npm install && npm test`
Expected: `ws` installed; test output shows `tests 1`, `pass 1`, `fail 0`.

- [ ] **Step 5: Commit**

```bash
git add crowd-control/package.json crowd-control/package-lock.json crowd-control/shows/demo.json crowd-control/test/smoke.test.js
git commit -m "feat(crowd-control): scaffold package + node:test runner"
```

---

## Task 2: Show config loader & validator

**Files:**
- Create: `crowd-control/server/config.js`
- Test: `crowd-control/test/config.test.js`

**Interfaces:**
- Consumes: a show JSON shaped like `shows/demo.json`.
- Produces:
  - `validateConfig(obj) -> { ok: true, config } | { ok: false, errors: string[] }` (PURE — no file IO).
  - `loadConfig(path) -> config` (reads file, throws `Error` with joined messages if invalid).
  - A normalized `config` has: `show:string`, `slotCap:number`, `controls:Array<{id,type,label,role,min?,max?}>`, `grid:{id,role,perGuest}|null`, `signals:Array<{id,label,role}>`. All `role` values are `"master"` or `"public"`. Control `type` is `"slider"` or `"toggle"`.

- [ ] **Step 1: Write failing tests**

```js
// crowd-control/test/config.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validateConfig } from '../server/config.js';

const good = {
  show: 'demo', slotCap: 24,
  controls: [{ id: 'speed', type: 'slider', label: 'Speed', min: 0, max: 1, role: 'master' }],
  grid: { id: 'xy', perGuest: true, role: 'public' },
  signals: [{ id: 'burst', label: '✦', role: 'public' }],
};

test('accepts a valid config', () => {
  const r = validateConfig(good);
  assert.equal(r.ok, true);
  assert.equal(r.config.controls[0].id, 'speed');
});

test('rejects duplicate control ids', () => {
  const bad = { ...good, controls: [good.controls[0], good.controls[0]] };
  const r = validateConfig(bad);
  assert.equal(r.ok, false);
  assert.match(r.errors.join(' '), /duplicate/i);
});

test('rejects an unknown role', () => {
  const bad = { ...good, controls: [{ ...good.controls[0], role: 'admin' }] };
  const r = validateConfig(bad);
  assert.equal(r.ok, false);
  assert.match(r.errors.join(' '), /role/i);
});

test('rejects non-positive slotCap', () => {
  const r = validateConfig({ ...good, slotCap: 0 });
  assert.equal(r.ok, false);
});

test('grid may be null', () => {
  const r = validateConfig({ ...good, grid: null });
  assert.equal(r.ok, true);
  assert.equal(r.config.grid, null);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd crowd-control && node --test test/config.test.js`
Expected: FAIL — `Cannot find module '../server/config.js'`.

- [ ] **Step 3: Implement config.js**

```js
// crowd-control/server/config.js
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
```

- [ ] **Step 4: Run to verify pass**

Run: `cd crowd-control && node --test test/config.test.js`
Expected: PASS — `tests 5`, `pass 5`.

- [ ] **Step 5: Commit**

```bash
git add crowd-control/server/config.js crowd-control/test/config.test.js
git commit -m "feat(crowd-control): show config loader + validator"
```

---

## Task 3: Wire protocol (parse + build)

**Files:**
- Create: `crowd-control/server/protocol.js`
- Test: `crowd-control/test/protocol.test.js`

**Interfaces:**
- Consumes: nothing.
- Produces (all PURE):
  - `parseInbound(raw: string) -> { ok:true, msg } | { ok:false, error:string }`. `msg.type` ∈ inbound set. Validates shapes: `hello{clientId:string}`, `pair{code:string}`, `control{id:string,v:number|boolean}`, `grid{x:number,y:number}` (x,y clamped to 0..1), `signal{id:string}`, `ping{}`.
  - Builders returning plain objects (caller JSON-stringifies): `welcome({clientId,role,slot,config,masterPresent})`, `roleMsg({role,slot})`, `bumped()`, `stateMsg({masterPresent,guestCount,slotsUsed})`, `errorMsg(code, message, extra?)`.

- [ ] **Step 1: Write failing tests**

```js
// crowd-control/test/protocol.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseInbound, welcome, errorMsg } from '../server/protocol.js';

test('parses a valid control message', () => {
  const r = parseInbound(JSON.stringify({ type: 'control', id: 'speed', v: 0.5 }));
  assert.equal(r.ok, true);
  assert.equal(r.msg.id, 'speed');
  assert.equal(r.msg.v, 0.5);
});

test('clamps grid coordinates to 0..1', () => {
  const r = parseInbound(JSON.stringify({ type: 'grid', x: 1.4, y: -0.2 }));
  assert.equal(r.ok, true);
  assert.equal(r.msg.x, 1);
  assert.equal(r.msg.y, 0);
});

test('rejects malformed JSON', () => {
  const r = parseInbound('{not json');
  assert.equal(r.ok, false);
});

test('rejects unknown message type', () => {
  const r = parseInbound(JSON.stringify({ type: 'nope' }));
  assert.equal(r.ok, false);
});

test('rejects control without numeric/boolean v', () => {
  const r = parseInbound(JSON.stringify({ type: 'control', id: 'x', v: 'hi' }));
  assert.equal(r.ok, false);
});

test('welcome builder shape', () => {
  const m = welcome({ clientId: 'c1', role: 'guest', slot: 3, config: {}, masterPresent: false });
  assert.equal(m.type, 'welcome');
  assert.equal(m.slot, 3);
});

test('error builder carries code + extra', () => {
  const m = errorMsg('locked', 'try later', { retryInMs: 9000 });
  assert.equal(m.type, 'error');
  assert.equal(m.code, 'locked');
  assert.equal(m.retryInMs, 9000);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd crowd-control && node --test test/protocol.test.js`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement protocol.js**

```js
// crowd-control/server/protocol.js
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
```

- [ ] **Step 4: Run to verify pass**

Run: `cd crowd-control && node --test test/protocol.test.js`
Expected: PASS — `tests 7`.

- [ ] **Step 5: Commit**

```bash
git add crowd-control/server/protocol.js crowd-control/test/protocol.test.js
git commit -m "feat(crowd-control): wire protocol parse + builders"
```

---

## Task 4: Session — connect, slots, recycling, overflow

**Files:**
- Create: `crowd-control/server/session.js`
- Test: `crowd-control/test/session.test.js`

**Interfaces:**
- Consumes: a validated `config` (Task 2).
- Produces a `Session` class. This task implements construction + connection lifecycle; later tasks extend the SAME class. Methods produced here:
  - `new Session(config, opts?)` where `opts = { seizeLockMs, idleReleaseMs, hardCapMs, codeRotateIdleMs, codeGen }`. `codeGen() -> 'ABC'` (injectable; default in Task 6). At construction, `currentCode` is `null` until first set in Task 6 — for THIS task tests don't read it.
  - `connect(connId, clientId, now) -> { role, slot, masterPresent }`. Assigns the lowest free guest slot (1..slotCap). If `clientId` already owns a live slot, returns that same slot. If all guest slots full → `role:'spectator'`, `slot:null`.
  - `disconnect(connId, now) -> { wasMaster: boolean }`. Frees the slot (recyclable). Master handling lands in Task 5; here just free the slot and report `wasMaster:false`.
  - `guestCount() -> number` (occupied guest slots). `slotsUsed() -> number`.
  - Internal state later tasks rely on: `this.clients` (Map connId→`{connId,clientId,slot,role}`), `this.slots` (Array index 0..slotCap; index 0 master, 1..slotCap guests; value = connId|null), `this.master` (null for now).

- [ ] **Step 1: Write failing tests**

```js
// crowd-control/test/session.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Session } from '../server/session.js';

const cfg = { show: 'demo', slotCap: 2, controls: [], grid: null, signals: [] };
const mk = () => new Session(cfg, { codeGen: () => 'ABC' });

test('assigns lowest free guest slot starting at 1', () => {
  const s = mk();
  assert.equal(s.connect('c1', 'u1', 0).slot, 1);
  assert.equal(s.connect('c2', 'u2', 0).slot, 2);
});

test('overflow connections become spectators', () => {
  const s = mk();
  s.connect('c1', 'u1', 0);
  s.connect('c2', 'u2', 0);
  const r = s.connect('c3', 'u3', 0);
  assert.equal(r.role, 'spectator');
  assert.equal(r.slot, null);
});

test('disconnect frees the slot for reuse', () => {
  const s = mk();
  s.connect('c1', 'u1', 0);
  s.connect('c2', 'u2', 0);
  s.disconnect('c1', 0);
  assert.equal(s.connect('c4', 'u4', 0).slot, 1);
});

test('same clientId reconnecting keeps its slot', () => {
  const s = mk();
  s.connect('c1', 'u1', 0);
  // c1 drops, reconnects as new connId but same clientId before slot reused
  s.disconnect('c1', 0);
  assert.equal(s.connect('c1b', 'u1', 0).slot, 1);
});

test('guestCount reflects occupied guest slots', () => {
  const s = mk();
  s.connect('c1', 'u1', 0);
  s.connect('c2', 'u2', 0);
  assert.equal(s.guestCount(), 2);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd crowd-control && node --test test/session.test.js`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement session.js (construction + slots)**

```js
// crowd-control/server/session.js

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
```

- [ ] **Step 4: Run to verify pass**

Run: `cd crowd-control && node --test test/session.test.js`
Expected: PASS — `tests 5`.

- [ ] **Step 5: Commit**

```bash
git add crowd-control/server/session.js crowd-control/test/session.test.js
git commit -m "feat(crowd-control): session slot assignment + recycling + overflow"
```

---

## Task 5: Session — pairing, last-wins, 15 s lock-out, code rotation on seizure

**Files:**
- Modify: `crowd-control/server/session.js`
- Test: `crowd-control/test/session.test.js` (append)

**Interfaces:**
- Consumes: the `Session` from Task 4.
- Produces (added to `Session`):
  - On construction, initialize `currentCode = this.codeGen()` and `lastCodeRotate = 0`. (Moves the `null` from Task 4.)
  - `pair(connId, code, now) -> { granted:boolean, code?:string, bumpedConnId?:string, error?:{code,message,retryInMs?} }`. Rules: if `now < master.seizeLockUntil` → `{granted:false, error:{code:'locked', message, retryInMs}}`. Else if `code !== currentCode` → `{granted:false, error:{code:'badcode', message}}`. Else grant: move this connId to slot 0, set its role `master`; if a different connId was master, free it back to a guest slot (or spectator) and report it as `bumpedConnId`; rotate `currentCode = codeGen()`; set `master = { connId, since:now, lastActivity:now, seizeLockUntil: now + seizeLockMs }`.
  - Override `disconnect(connId, now)`: if the leaving connId is the master, clear `this.master`, free slot 0, rotate code, return `{ wasMaster:true }`.
  - Helper `roleOf(connId) -> 'master'|'guest'|'spectator'|null`.

- [ ] **Step 1: Append failing tests**

```js
// append to crowd-control/test/session.test.js
test('first valid pair grants master and rotates code', () => {
  const s = new Session(cfg, { codeGen: (() => { let i = 0; const codes = ['AAA', 'BBB']; return () => codes[i++] || 'ZZZ'; })() });
  s.connect('c1', 'u1', 0);
  const code = s.currentCode; // 'AAA'
  const r = s.pair('c1', code, 1000);
  assert.equal(r.granted, true);
  assert.equal(s.roleOf('c1'), 'master');
  assert.notEqual(s.currentCode, code); // rotated
  assert.equal(s.slots[0], 'c1');
});

test('pair within 15s lock-out is rejected as locked', () => {
  const s = mk();
  s.connect('c1', 'u1', 0);
  s.connect('c2', 'u2', 0);
  s.pair('c1', s.currentCode, 1000);
  const r = s.pair('c2', s.currentCode, 1000 + 14999);
  assert.equal(r.granted, false);
  assert.equal(r.error.code, 'locked');
  assert.ok(r.error.retryInMs > 0);
});

test('pair after lock-out with current code seizes and bumps previous master', () => {
  const s = mk();
  s.connect('c1', 'u1', 0);
  s.connect('c2', 'u2', 0);
  s.pair('c1', s.currentCode, 1000);
  const r = s.pair('c2', s.currentCode, 1000 + 15000);
  assert.equal(r.granted, true);
  assert.equal(r.bumpedConnId, 'c1');
  assert.equal(s.roleOf('c1'), 'guest');
  assert.equal(s.roleOf('c2'), 'master');
});

test('wrong code is rejected as badcode', () => {
  const s = mk();
  s.connect('c1', 'u1', 0);
  const r = s.pair('c1', 'ZZZ', 1000);
  assert.equal(r.granted, false);
  assert.equal(r.error.code, 'badcode');
});

test('master disconnect releases and rotates code', () => {
  const s = mk();
  s.connect('c1', 'u1', 0);
  s.pair('c1', s.currentCode, 1000);
  const before = s.currentCode;
  const r = s.disconnect('c1', 2000);
  assert.equal(r.wasMaster, true);
  assert.equal(s.master, null);
  assert.equal(s.slots[0], null);
  assert.notEqual(s.currentCode, before);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd crowd-control && node --test test/session.test.js`
Expected: FAIL — `s.pair is not a function` / `currentCode` is null.

- [ ] **Step 3: Implement pairing**

In the constructor, replace `this.currentCode = null;` with:

```js
    this.currentCode = this.codeGen();
```

Add these methods to the `Session` class (and replace the Task 4 `disconnect` with the version below):

```js
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
        if (g !== null) { this.slots[g] = bumpedConnId; prev.slot = g; prev.role = 'guest'; this._stickySlots.set(prev.clientId, g); }
        else { prev.slot = null; prev.role = 'spectator'; }
      }
    }

    // free this client's old guest slot, move to master slot 0
    if (client.slot != null && this.slots[client.slot] === connId) this.slots[client.slot] = null;
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
    this.clients.delete(connId);
    return { wasMaster };
  }
```

Delete the old `disconnect` method from Task 4 (the new one above replaces it).

- [ ] **Step 4: Run to verify pass**

Run: `cd crowd-control && node --test test/session.test.js`
Expected: PASS — all session tests (Task 4 + Task 5) green.

- [ ] **Step 5: Commit**

```bash
git add crowd-control/server/session.js crowd-control/test/session.test.js
git commit -m "feat(crowd-control): master pairing, last-wins, 15s lock-out, code rotation"
```

---

## Task 6: Session — inputs (control/grid/signal) with role gating

**Files:**
- Modify: `crowd-control/server/session.js`
- Test: `crowd-control/test/session.test.js` (append)

**Interfaces:**
- Consumes: `Session` + the validated `config` (controls/grid/signals carry `role`).
- Produces (added to `Session`):
  - `applyControl(connId, id, v, now) -> { ok:boolean, error?:{code,message} }`. Looks up the control by `id` in config. `role:'master'` controls require the caller be master; `role:'public'` controls allow master OR guest (not spectator). On success, store `this.values[slot][id] = v` (per-slot store) and, if caller is master, bump `master.lastActivity`. Unknown id → `{ok:false, error:{code:'badcontrol'}}`. Not authorized → `{ok:false, error:{code:'forbidden'}}`.
  - `applyGrid(connId, x, y, now)` — same gating using `config.grid.role`; stores `this.grid[slot] = {x,y}`; bumps master activity if master.
  - `applySignal(connId, id, now) -> { ok, slot?, error? }` — gating from the matching `config.signals[].role`; returns `{ok:true, slot}` so the server can forward a one-shot engine signal. Bumps master activity if master.
  - State later tasks rely on: `this.values` (Object slot→{id:value}), `this.grid` (Object slot→{x,y}).

- [ ] **Step 1: Append failing tests**

```js
// append to crowd-control/test/session.test.js
const cfg2 = {
  show: 'demo', slotCap: 4,
  controls: [
    { id: 'speed', type: 'slider', label: 'Speed', min: 0, max: 1, role: 'master' },
    { id: 'hue', type: 'slider', label: 'Color', min: 0, max: 1, role: 'public' },
  ],
  grid: { id: 'xy', role: 'public', perGuest: true },
  signals: [{ id: 'burst', label: '✦', role: 'public' }],
};
const mk2 = () => new Session(cfg2, { codeGen: () => 'ABC' });

test('guest can set a public control', () => {
  const s = mk2();
  s.connect('c1', 'u1', 0);
  const r = s.applyControl('c1', 'hue', 0.7, 0);
  assert.equal(r.ok, true);
  assert.equal(s.values[s.clients.get('c1').slot].hue, 0.7);
});

test('guest cannot set a master control', () => {
  const s = mk2();
  s.connect('c1', 'u1', 0);
  const r = s.applyControl('c1', 'speed', 0.7, 0);
  assert.equal(r.ok, false);
  assert.equal(r.error.code, 'forbidden');
});

test('master can set a master control and it bumps activity', () => {
  const s = mk2();
  s.connect('c1', 'u1', 0);
  s.pair('c1', s.currentCode, 1000);
  const r = s.applyControl('c1', 'speed', 0.4, 5000);
  assert.equal(r.ok, true);
  assert.equal(s.master.lastActivity, 5000);
});

test('grid stores per-slot xy for a guest', () => {
  const s = mk2();
  s.connect('c1', 'u1', 0);
  const slot = s.clients.get('c1').slot;
  s.applyGrid('c1', 0.25, 0.75, 0);
  assert.deepEqual(s.grid[slot], { x: 0.25, y: 0.75 });
});

test('spectator cannot send public input', () => {
  const s = new Session({ ...cfg2, slotCap: 1 }, { codeGen: () => 'ABC' });
  s.connect('c1', 'u1', 0);          // takes the only guest slot
  s.connect('c2', 'u2', 0);          // spectator
  const r = s.applyControl('c2', 'hue', 0.5, 0);
  assert.equal(r.ok, false);
  assert.equal(r.error.code, 'forbidden');
});

test('unknown control id is rejected', () => {
  const s = mk2();
  s.connect('c1', 'u1', 0);
  const r = s.applyControl('c1', 'nope', 1, 0);
  assert.equal(r.ok, false);
  assert.equal(r.error.code, 'badcontrol');
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd crowd-control && node --test test/session.test.js`
Expected: FAIL — `applyControl is not a function`.

- [ ] **Step 3: Implement inputs + gating**

In the constructor, add after `this._stickySlots = new Map();`:

```js
    this.values = {}; // slot -> { controlId: value }
    this.grid = {};   // slot -> { x, y }
    this._controlsById = new Map(config.controls.map((c) => [c.id, c]));
    this._signalsById = new Map((config.signals || []).map((s) => [s.id, s]));
```

Add these methods to the `Session` class:

```js
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
```

Also: when a slot is freed (in `disconnect` and in the bump-to-guest path of `pair`), clear stale per-slot data. Add a helper and call it. Add this method:

```js
  _clearSlotData(slot) {
    if (slot == null) return;
    delete this.values[slot];
    delete this.grid[slot];
  }
```

In `disconnect`, after computing the freed slot, call `this._clearSlotData(client.slot)` before `this.clients.delete(connId)`. In `pair`, when moving a client to slot 0, call `this._clearSlotData` on its old guest slot.

- [ ] **Step 4: Run to verify pass**

Run: `cd crowd-control && node --test test/session.test.js`
Expected: PASS — all session tests green.

- [ ] **Step 5: Commit**

```bash
git add crowd-control/server/session.js crowd-control/test/session.test.js
git commit -m "feat(crowd-control): role-gated control/grid/signal inputs"
```

---

## Task 7: Session — housekeeping tick (idle release, hard cap, idle code rotation)

**Files:**
- Modify: `crowd-control/server/session.js`
- Test: `crowd-control/test/session.test.js` (append)

**Interfaces:**
- Consumes: `Session`.
- Produces:
  - `tick(now) -> { releasedMasterConnId?:string, codeRotated:boolean }`. Behavior, in order:
    1. If a master exists and (`now - master.lastActivity >= idleReleaseMs` OR `now - master.since >= hardCapMs`) → release: clear master, free slot 0, demote that connId to a guest slot/spectator, rotate code, set `releasedMasterConnId`.
    2. If no master and `now - lastCodeRotate >= codeRotateIdleMs` → rotate code, `codeRotated:true`. (When a master holds control the code only rotates on seizure, not idly.)

- [ ] **Step 1: Append failing tests**

```js
// append to crowd-control/test/session.test.js
test('tick releases master after 2 min inactivity', () => {
  const s = mk2();
  s.connect('c1', 'u1', 0);
  s.pair('c1', s.currentCode, 1000);
  const r = s.tick(1000 + 120000);
  assert.equal(r.releasedMasterConnId, 'c1');
  assert.equal(s.master, null);
  assert.equal(s.roleOf('c1'), 'guest');
});

test('tick keeps an active master below the inactivity threshold', () => {
  const s = mk2();
  s.connect('c1', 'u1', 0);
  s.pair('c1', s.currentCode, 1000);
  s.applyControl('c1', 'speed', 0.5, 100000); // activity
  const r = s.tick(100000 + 119999);
  assert.equal(r.releasedMasterConnId, undefined);
  assert.equal(s.master?.connId, 'c1');
});

test('tick releases master at the 30 min hard cap even if active', () => {
  const s = mk2();
  s.connect('c1', 'u1', 0);
  s.pair('c1', s.currentCode, 0);
  s.applyControl('c1', 'speed', 0.5, 1800000 - 1); // recent activity
  const r = s.tick(1800000);
  assert.equal(r.releasedMasterConnId, 'c1');
});

test('tick rotates the code after idle timeout when no master', () => {
  const s = mk2();
  const before = s.currentCode;
  const r = s.tick(60000);
  assert.equal(r.codeRotated, true);
  assert.notEqual(s.currentCode, before);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd crowd-control && node --test test/session.test.js`
Expected: FAIL — `s.tick is not a function`.

- [ ] **Step 3: Implement tick**

Add a `_releaseMaster(now)` helper and `tick`:

```js
  _releaseMaster(now) {
    if (!this.master) return undefined;
    const connId = this.master.connId;
    const prev = this.clients.get(connId);
    this.slots[0] = null;
    this.master = null;
    if (prev) {
      const g = this._freeGuestSlot();
      if (g !== null) { this.slots[g] = connId; prev.slot = g; prev.role = 'guest'; this._stickySlots.set(prev.clientId, g); }
      else { prev.slot = null; prev.role = 'spectator'; }
    }
    this._rotateCode(now);
    return connId;
  }

  tick(now) {
    let releasedMasterConnId;
    let codeRotated = false;
    if (this.master) {
      const idle = now - this.master.lastActivity >= this.opts.idleReleaseMs;
      const capped = now - this.master.since >= this.opts.hardCapMs;
      if (idle || capped) releasedMasterConnId = this._releaseMaster(now);
    }
    if (!this.master && now - this.lastCodeRotate >= this.opts.codeRotateIdleMs) {
      this._rotateCode(now);
      codeRotated = true;
    }
    return { releasedMasterConnId, codeRotated };
  }
```

Note: `_releaseMaster` already rotates the code, so a release implies a rotation; the separate idle-rotation branch only fires when no master is present.

- [ ] **Step 4: Run to verify pass**

Run: `cd crowd-control && node --test test/session.test.js`
Expected: PASS — all session tests green.

- [ ] **Step 5: Commit**

```bash
git add crowd-control/server/session.js crowd-control/test/session.test.js
git commit -m "feat(crowd-control): housekeeping tick — releases + idle code rotation"
```

---

## Task 8: Engine snapshot builder

**Files:**
- Create: `crowd-control/server/snapshot.js`
- Test: `crowd-control/test/snapshot.test.js`

**Interfaces:**
- Consumes: a `Session`.
- Produces (PURE):
  - `buildSnapshot(session) -> { type:'snapshot', code, masterSlot, slots: Array<{slot,role,active,x,y,vals}> }`. One entry per occupied slot (0 if master present, plus every occupied guest slot). `x,y` default to `0` when no grid point recorded; `vals` is the per-slot control values object (`{}` if none). `masterSlot` is `0` when a master holds control, else `null`.

- [ ] **Step 1: Write failing tests**

```js
// crowd-control/test/snapshot.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Session } from '../server/session.js';
import { buildSnapshot } from '../server/snapshot.js';

const cfg = {
  show: 'demo', slotCap: 4,
  controls: [{ id: 'hue', type: 'slider', label: 'Color', min: 0, max: 1, role: 'public' }],
  grid: { id: 'xy', role: 'public', perGuest: true },
  signals: [],
};

test('snapshot lists occupied guest slots with values and grid', () => {
  const s = new Session(cfg, { codeGen: () => 'ABC' });
  s.connect('c1', 'u1', 0);
  const slot = s.clients.get('c1').slot;
  s.applyControl('c1', 'hue', 0.6, 0);
  s.applyGrid('c1', 0.2, 0.8, 0);
  const snap = buildSnapshot(s);
  assert.equal(snap.type, 'snapshot');
  assert.equal(snap.code, 'ABC');
  assert.equal(snap.masterSlot, null);
  const e = snap.slots.find((x) => x.slot === slot);
  assert.deepEqual({ x: e.x, y: e.y, hue: e.vals.hue }, { x: 0.2, y: 0.8, hue: 0.6 });
});

test('snapshot includes the master slot 0 when held', () => {
  const s = new Session(cfg, { codeGen: () => 'ABC' });
  s.connect('c1', 'u1', 0);
  s.pair('c1', s.currentCode, 1000);
  const snap = buildSnapshot(s);
  assert.equal(snap.masterSlot, 0);
  assert.ok(snap.slots.find((x) => x.slot === 0 && x.role === 'master'));
});

test('absent grid point defaults to 0,0', () => {
  const s = new Session(cfg, { codeGen: () => 'ABC' });
  s.connect('c1', 'u1', 0);
  const e = buildSnapshot(s).slots.find((x) => x.slot === s.clients.get('c1').slot);
  assert.deepEqual({ x: e.x, y: e.y }, { x: 0, y: 0 });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd crowd-control && node --test test/snapshot.test.js`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement snapshot.js**

```js
// crowd-control/server/snapshot.js
export function buildSnapshot(session) {
  const slots = [];
  for (let i = 0; i <= session.config.slotCap; i++) {
    const connId = session.slots[i];
    if (!connId) continue;
    const client = session.clients.get(connId);
    const g = session.grid[i] || { x: 0, y: 0 };
    slots.push({
      slot: i,
      role: client ? client.role : (i === 0 ? 'master' : 'guest'),
      active: true,
      x: g.x,
      y: g.y,
      vals: session.values[i] || {},
    });
  }
  return {
    type: 'snapshot',
    code: session.currentCode,
    masterSlot: session.master ? 0 : null,
    slots,
  };
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd crowd-control && node --test test/snapshot.test.js`
Expected: PASS — `tests 3`.

- [ ] **Step 5: Commit**

```bash
git add crowd-control/server/snapshot.js crowd-control/test/snapshot.test.js
git commit -m "feat(crowd-control): TD engine snapshot builder"
```

---

## Task 9: Per-connection rate limiter

**Files:**
- Create: `crowd-control/server/ratelimit.js`
- Test: `crowd-control/test/ratelimit.test.js`

**Interfaces:**
- Consumes: nothing.
- Produces (PURE): `class TokenBucket { constructor(capacity, refillPerSec); take(now, n=1) -> boolean }`. Tokens refill continuously based on `now` (ms). `take` returns `false` (drop) when insufficient tokens.

- [ ] **Step 1: Write failing tests**

```js
// crowd-control/test/ratelimit.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { TokenBucket } from '../server/ratelimit.js';

test('allows up to capacity immediately', () => {
  const b = new TokenBucket(5, 10);
  for (let i = 0; i < 5; i++) assert.equal(b.take(0), true);
  assert.equal(b.take(0), false); // exhausted
});

test('refills over time', () => {
  const b = new TokenBucket(5, 10); // 10 tokens/sec
  for (let i = 0; i < 5; i++) b.take(0);
  assert.equal(b.take(100), false);  // 0.1s -> 1 token? 10/s*0.1=1 -> true actually
  // 100ms => 1 token refilled
  assert.equal(b.take(0 + 100 + 0), false); // already consumed by line above? re-check below
});

test('refill math: 1s restores full capacity', () => {
  const b = new TokenBucket(5, 5);
  for (let i = 0; i < 5; i++) b.take(0);
  assert.equal(b.take(1000), true);
});
```

> Note: the middle test is intentionally simple; the authoritative refill behavior is the third test. Keep the first and third; delete the brittle middle test before implementing if it distracts — the third test pins the contract.

- [ ] **Step 2: Run to verify failure**

Run: `cd crowd-control && node --test test/ratelimit.test.js`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement ratelimit.js**

```js
// crowd-control/server/ratelimit.js
export class TokenBucket {
  constructor(capacity, refillPerSec) {
    this.capacity = capacity;
    this.refillPerSec = refillPerSec;
    this.tokens = capacity;
    this.last = null;
  }

  take(now, n = 1) {
    if (this.last === null) this.last = now;
    const elapsed = Math.max(0, now - this.last) / 1000;
    this.tokens = Math.min(this.capacity, this.tokens + elapsed * this.refillPerSec);
    this.last = now;
    if (this.tokens >= n) { this.tokens -= n; return true; }
    return false;
  }
}
```

- [ ] **Step 4: Adjust the brittle middle test, then run to verify pass**

Replace the middle test body with a concrete assertion:

```js
test('refills 1 token per 100ms at 10/s', () => {
  const b = new TokenBucket(5, 10);
  for (let i = 0; i < 5; i++) b.take(0); // drain
  assert.equal(b.take(100), true);       // +1 token at t=100ms
  assert.equal(b.take(100), false);      // none left
});
```

Run: `cd crowd-control && node --test test/ratelimit.test.js`
Expected: PASS — `tests 3`.

- [ ] **Step 5: Commit**

```bash
git add crowd-control/server/ratelimit.js crowd-control/test/ratelimit.test.js
git commit -m "feat(crowd-control): per-connection token-bucket rate limiter"
```

---

## Task 10: Static file server

**Files:**
- Create: `crowd-control/server/static.js`
- Create: `crowd-control/public/index.html` (minimal placeholder; fleshed out in Task 12)
- Test: `crowd-control/test/static.test.js`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `resolveStaticPath(rootDir, urlPath) -> string | null`. Maps a URL path to an absolute file path inside `rootDir`; returns `null` for traversal attempts (`..`) or paths escaping `rootDir`. `/` maps to `index.html`.
  - `serveStatic(rootDir, req, res) -> boolean` — writes the file with a correct `Content-Type` and returns `true` if served, else `false` (caller handles 404). (Tested indirectly; the pure `resolveStaticPath` carries the security test.)

- [ ] **Step 1: Write failing tests**

```js
// crowd-control/test/static.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolveStaticPath } from '../server/static.js';
import { sep } from 'node:path';

const root = process.cwd() + sep + 'public';

test('maps / to index.html', () => {
  const p = resolveStaticPath(root, '/');
  assert.ok(p.endsWith('index.html'));
});

test('maps a normal asset path', () => {
  const p = resolveStaticPath(root, '/app.js');
  assert.ok(p.endsWith('app.js'));
  assert.ok(p.startsWith(root));
});

test('blocks path traversal', () => {
  assert.equal(resolveStaticPath(root, '/../server/session.js'), null);
  assert.equal(resolveStaticPath(root, '/..%2f..%2fetc/passwd'), null);
});
```

- [ ] **Step 2: Create placeholder index.html and run to verify failure**

```html
<!-- crowd-control/public/index.html -->
<!doctype html><meta charset="utf-8"><title>crowd-control</title><p>placeholder</p>
```

Run: `cd crowd-control && node --test test/static.test.js`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement static.js**

```js
// crowd-control/server/static.js
import { resolve, normalize, extname, sep } from 'node:path';
import { createReadStream, existsSync, statSync } from 'node:fs';

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.webmanifest': 'application/manifest+json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
};

export function resolveStaticPath(rootDir, urlPath) {
  let p = decodeURIComponent(urlPath.split('?')[0]);
  if (p === '/' || p === '') p = '/index.html';
  const abs = resolve(rootDir, '.' + normalize(p));
  if (abs !== rootDir && !abs.startsWith(rootDir + sep)) return null;
  return abs;
}

export function serveStatic(rootDir, req, res) {
  const abs = resolveStaticPath(rootDir, req.url || '/');
  if (!abs || !existsSync(abs) || !statSync(abs).isFile()) return false;
  res.writeHead(200, { 'Content-Type': MIME[extname(abs)] || 'application/octet-stream' });
  createReadStream(abs).pipe(res);
  return true;
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd crowd-control && node --test test/static.test.js`
Expected: PASS — `tests 3`.

- [ ] **Step 5: Commit**

```bash
git add crowd-control/server/static.js crowd-control/public/index.html crowd-control/test/static.test.js
git commit -m "feat(crowd-control): safe static file server with traversal guard"
```

---

## Task 11: WebSocket server glue + entry point (integration)

**Files:**
- Create: `crowd-control/server/wsServer.js`
- Create: `crowd-control/server/index.js`
- Test: `crowd-control/test/wsServer.integration.test.js`

**Interfaces:**
- Consumes: `Session`, `parseInbound` + builders, `buildSnapshot`, `TokenBucket`, `serveStatic`, `loadConfig`.
- Produces:
  - `createServer({ config, port, publicDir, engineSecret, opts }) -> { httpServer, wss, session, stop() }`. Wires: HTTP (static) + `ws` upgrade; per-connection rate limiting; a 1 Hz housekeeping tick; a `snapshotHz` snapshot push to the engine connection; routing of inbound messages to session methods; fanout of `role`/`bumped`/`state`.
  - Engine handshake: a client connecting to path `/engine?secret=...` (matching `engineSecret`) is the trusted TD client — it receives `snapshot` frames + forwarded `signal` events and is NOT assigned a slot. A bad/missing secret closes the socket.
  - `index.js`: reads `SHOW` (path, default `shows/demo.json`), `PORT` (default 8080), `ENGINE_SECRET` (default `dev-secret`) from env; calls `createServer`; logs the listen URL.

- [ ] **Step 1: Write the failing integration test**

```js
// crowd-control/test/wsServer.integration.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { WebSocket } from 'ws';
import { createServer } from '../server/wsServer.js';

const config = {
  show: 'demo', slotCap: 4,
  controls: [
    { id: 'speed', type: 'slider', label: 'Speed', min: 0, max: 1, role: 'master' },
    { id: 'hue', type: 'slider', label: 'Color', min: 0, max: 1, role: 'public' },
  ],
  grid: { id: 'xy', role: 'public', perGuest: true },
  signals: [{ id: 'burst', label: '✦', role: 'public' }],
};

function open(url) {
  return new Promise((res, rej) => {
    const ws = new WebSocket(url);
    ws.once('open', () => res(ws));
    ws.once('error', rej);
  });
}
function next(ws) {
  return new Promise((res) => ws.once('message', (d) => res(JSON.parse(d.toString()))));
}

test('phone gets a welcome with config and guest role', async () => {
  const srv = createServer({ config, port: 0, publicDir: 'public', engineSecret: 's', opts: { codeGen: () => 'ABC' } });
  const port = srv.httpServer.address().port;
  const ws = await open(`ws://127.0.0.1:${port}/`);
  ws.send(JSON.stringify({ type: 'hello', clientId: 'u1' }));
  const msg = await next(ws);
  assert.equal(msg.type, 'welcome');
  assert.equal(msg.role, 'guest');
  assert.equal(msg.config.show, 'demo');
  ws.close();
  await srv.stop();
});

test('engine receives snapshots and a guest grid update reaches it', async () => {
  const srv = createServer({ config, port: 0, publicDir: 'public', engineSecret: 's', opts: { codeGen: () => 'ABC', snapshotHz: 50 } });
  const port = srv.httpServer.address().port;
  const engine = await open(`ws://127.0.0.1:${port}/engine?secret=s`);
  const phone = await open(`ws://127.0.0.1:${port}/`);
  phone.send(JSON.stringify({ type: 'hello', clientId: 'u1' }));
  await next(phone); // welcome
  phone.send(JSON.stringify({ type: 'grid', x: 0.3, y: 0.9 }));
  // read engine snapshots until one shows the grid value
  let seen = null;
  for (let i = 0; i < 20 && !seen; i++) {
    const snap = await next(engine);
    if (snap.type === 'snapshot') {
      const e = snap.slots.find((x) => x.x === 0.3 && x.y === 0.9);
      if (e) seen = e;
    }
  }
  assert.ok(seen, 'engine snapshot reflected the guest grid point');
  phone.close(); engine.close();
  await srv.stop();
});

test('engine with wrong secret is rejected', async () => {
  const srv = createServer({ config, port: 0, publicDir: 'public', engineSecret: 's', opts: { codeGen: () => 'ABC' } });
  const port = srv.httpServer.address().port;
  await assert.rejects(open(`ws://127.0.0.1:${port}/engine?secret=WRONG`));
  await srv.stop();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd crowd-control && node --test test/wsServer.integration.test.js`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement wsServer.js**

```js
// crowd-control/server/wsServer.js
import { createServer as createHttp } from 'node:http';
import { WebSocketServer } from 'ws';
import { resolve } from 'node:path';
import { Session } from './session.js';
import { buildSnapshot } from './snapshot.js';
import { TokenBucket } from './ratelimit.js';
import { serveStatic } from './static.js';
import {
  parseInbound, welcome, roleMsg, bumped, stateMsg, errorMsg,
} from './protocol.js';

let _connSeq = 0;

export function createServer({ config, port, publicDir, engineSecret, opts = {} }) {
  const session = new Session(config, opts);
  const now = () => Date.now();
  const rootDir = resolve(process.cwd(), publicDir);

  const httpServer = createHttp((req, res) => {
    if (serveStatic(rootDir, req, res)) return;
    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('not found');
  });

  const wss = new WebSocketServer({ noServer: true });
  const phones = new Map(); // connId -> ws
  let engine = null;

  httpServer.on('upgrade', (req, socket, head) => {
    const url = new URL(req.url, 'http://x');
    if (url.pathname === '/engine') {
      if (url.searchParams.get('secret') !== engineSecret) { socket.destroy(); return; }
      wss.handleUpgrade(req, socket, head, (ws) => { ws._engine = true; wss.emit('connection', ws, req); });
      return;
    }
    wss.handleUpgrade(req, socket, head, (ws) => wss.emit('connection', ws, req));
  });

  const send = (ws, obj) => { if (ws.readyState === ws.OPEN) ws.send(JSON.stringify(obj)); };

  wss.on('connection', (ws) => {
    if (ws._engine) { engine = ws; ws.on('close', () => { if (engine === ws) engine = null; }); return; }

    const connId = `c${++_connSeq}`;
    ws._connId = connId;
    ws._bucket = new TokenBucket(60, 60); // 60 msgs burst, 60/s sustained
    phones.set(connId, ws);

    ws.on('message', (data) => {
      if (!ws._bucket.take(now())) return; // silently drop floods
      const r = parseInbound(data.toString());
      if (!r.ok) { send(ws, errorMsg('badmsg', r.error)); return; }
      handle(connId, ws, r.msg);
    });

    ws.on('close', () => {
      const res = session.disconnect(connId, now());
      phones.delete(connId);
      if (res.wasMaster) broadcastState();
    });
  });

  function handle(connId, ws, msg) {
    switch (msg.type) {
      case 'hello': {
        const r = session.connect(connId, msg.clientId, now());
        send(ws, welcome({ clientId: msg.clientId, role: r.role, slot: r.slot, config, masterPresent: r.masterPresent }));
        broadcastState();
        break;
      }
      case 'pair': {
        const r = session.pair(connId, msg.code, now());
        if (!r.granted) { send(ws, errorMsg(r.error.code, r.error.message, r.error.retryInMs != null ? { retryInMs: r.error.retryInMs } : {})); break; }
        send(ws, roleMsg({ role: 'master', slot: 0 }));
        if (r.bumpedConnId) {
          const bws = phones.get(r.bumpedConnId);
          const bc = session.clients.get(r.bumpedConnId);
          if (bws) { send(bws, bumped()); send(bws, roleMsg({ role: bc ? bc.role : 'spectator', slot: bc ? bc.slot : null })); }
        }
        broadcastState();
        break;
      }
      case 'control': { const r = session.applyControl(connId, msg.id, msg.v, now()); if (!r.ok) send(ws, errorMsg(r.error.code, r.error.message)); break; }
      case 'grid':    { const r = session.applyGrid(connId, msg.x, msg.y, now()); if (!r.ok) send(ws, errorMsg(r.error.code, r.error.message)); break; }
      case 'signal':  {
        const r = session.applySignal(connId, msg.id, now());
        if (!r.ok) { send(ws, errorMsg(r.error.code, r.error.message)); break; }
        if (engine) send(engine, { type: 'signal', id: msg.id, slot: r.slot });
        break;
      }
      case 'ping': break;
    }
  }

  function broadcastState() {
    const st = stateMsg({ masterPresent: !!session.master, guestCount: session.guestCount(), slotsUsed: session.slotsUsed() });
    for (const ws of phones.values()) send(ws, st);
  }

  // housekeeping tick (1 Hz)
  const tickTimer = setInterval(() => {
    const r = session.tick(now());
    if (r.releasedMasterConnId) {
      const ws = phones.get(r.releasedMasterConnId);
      const c = session.clients.get(r.releasedMasterConnId);
      if (ws) send(ws, roleMsg({ role: c ? c.role : 'spectator', slot: c ? c.slot : null }));
      broadcastState();
    }
  }, 1000);

  // snapshot push to engine
  const snapHz = opts.snapshotHz || 60;
  const snapTimer = setInterval(() => {
    if (engine) send(engine, buildSnapshot(session));
  }, Math.max(5, Math.round(1000 / snapHz)));

  httpServer.listen(port);

  return {
    httpServer, wss, session,
    stop() {
      clearInterval(tickTimer); clearInterval(snapTimer);
      for (const ws of phones.values()) ws.terminate();
      if (engine) engine.terminate();
      return new Promise((res) => { wss.close(() => httpServer.close(() => res())); });
    },
  };
}
```

- [ ] **Step 4: Implement index.js**

```js
// crowd-control/server/index.js
import { resolve } from 'node:path';
import { loadConfig } from './config.js';
import { createServer } from './wsServer.js';

const showPath = process.env.SHOW || 'shows/demo.json';
const port = Number(process.env.PORT || 8080);
const engineSecret = process.env.ENGINE_SECRET || 'dev-secret';

const config = loadConfig(resolve(process.cwd(), showPath));
const srv = createServer({ config, port, publicDir: 'public', engineSecret });
console.log(`crowd-control "${config.show}" listening on http://0.0.0.0:${port}  (engine secret: ${engineSecret})`);

process.on('SIGINT', async () => { await srv.stop(); process.exit(0); });
```

- [ ] **Step 5: Run the integration test, then commit**

Run: `cd crowd-control && node --test test/wsServer.integration.test.js`
Expected: PASS — `tests 3`.

```bash
git add crowd-control/server/wsServer.js crowd-control/server/index.js crowd-control/test/wsServer.integration.test.js
git commit -m "feat(crowd-control): ws server glue, engine channel, tick + snapshot loops"
```

---

## Task 12: Phone PWA — pure UI logic

**Files:**
- Create: `crowd-control/public/ui-logic.js`
- Test: `crowd-control/test/ui-logic.test.js`

**Interfaces:**
- Consumes: the `config` shape + a `role`.
- Produces (PURE, importable in Node tests):
  - `visibleControls(config, role) -> Array<control>`: master sees all; guest sees only `role:'public'` controls; spectator sees none.
  - `gridVisible(config, role) -> boolean`: true when a grid exists and (role master, or grid.role public and role guest).
  - `lockoutSeconds(retryInMs) -> number`: `Math.ceil(retryInMs/1000)`.

- [ ] **Step 1: Write failing tests**

```js
// crowd-control/test/ui-logic.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { visibleControls, gridVisible, lockoutSeconds } from '../public/ui-logic.js';

const config = {
  controls: [
    { id: 'speed', role: 'master', type: 'slider', label: 'Speed', min: 0, max: 1 },
    { id: 'hue', role: 'public', type: 'slider', label: 'Color', min: 0, max: 1 },
  ],
  grid: { id: 'xy', role: 'public', perGuest: true },
  signals: [],
};

test('master sees all controls', () => {
  assert.equal(visibleControls(config, 'master').length, 2);
});
test('guest sees only public controls', () => {
  const v = visibleControls(config, 'guest');
  assert.deepEqual(v.map((c) => c.id), ['hue']);
});
test('spectator sees no controls', () => {
  assert.equal(visibleControls(config, 'spectator').length, 0);
});
test('grid visible to guest when public', () => {
  assert.equal(gridVisible(config, 'guest'), true);
  assert.equal(gridVisible(config, 'spectator'), false);
});
test('lockoutSeconds rounds up', () => {
  assert.equal(lockoutSeconds(14001), 15);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd crowd-control && node --test test/ui-logic.test.js`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement ui-logic.js**

```js
// crowd-control/public/ui-logic.js
export function visibleControls(config, role) {
  if (role === 'master') return config.controls.slice();
  if (role === 'guest') return config.controls.filter((c) => c.role === 'public');
  return [];
}

export function gridVisible(config, role) {
  if (!config.grid) return false;
  if (role === 'master') return true;
  if (role === 'guest') return config.grid.role === 'public';
  return false;
}

export function lockoutSeconds(retryInMs) {
  return Math.ceil(retryInMs / 1000);
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd crowd-control && node --test test/ui-logic.test.js`
Expected: PASS — `tests 5`.

- [ ] **Step 5: Commit**

```bash
git add crowd-control/public/ui-logic.js crowd-control/test/ui-logic.test.js
git commit -m "feat(crowd-control): pure PWA UI-logic (visible controls, grid, lockout)"
```

---

## Task 13: Phone PWA — shell, client, DOM wiring

**Files:**
- Modify: `crowd-control/public/index.html`
- Create: `crowd-control/public/app.js`
- Create: `crowd-control/public/styles.css`
- Create: `crowd-control/public/manifest.webmanifest`

**Interfaces:**
- Consumes: `ui-logic.js`; the wire protocol; the server at the same origin.
- Produces: a working installable page that connects, renders controls/grid from config + role, sends throttled input, exposes a **Seize Master** button + 3-letter code entry, and reflects `bumped`/`role`/`error{locked}`.

> This task is verified manually (browser) — no unit test. Keep `app.js` thin by delegating all decisions to `ui-logic.js`.

- [ ] **Step 1: Write index.html**

```html
<!-- crowd-control/public/index.html -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, user-scalable=no" />
  <link rel="manifest" href="/manifest.webmanifest" />
  <title>Crowd Control</title>
  <link rel="stylesheet" href="/styles.css" />
</head>
<body>
  <header>
    <span id="status">connecting…</span>
    <span id="role-badge">guest</span>
  </header>
  <main>
    <section id="controls"></section>
    <canvas id="grid" hidden></canvas>
    <section id="signals"></section>
  </main>
  <footer>
    <button id="seize">Seize Master</button>
    <form id="pair-form" hidden>
      <input id="code" inputmode="latin" autocapitalize="characters" maxlength="3" placeholder="ABC" />
      <button type="submit">Enter</button>
      <span id="pair-msg"></span>
    </form>
  </footer>
  <script type="module" src="/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write app.js**

```js
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
```

- [ ] **Step 3: Write styles.css (minimal — design pass comes later)**

```css
/* crowd-control/public/styles.css */
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; font: 16px system-ui, sans-serif; background: #0b0b10; color: #eee;
  min-height: 100dvh; display: flex; flex-direction: column; }
header { display: flex; justify-content: space-between; padding: 12px 16px; background: #15151c; }
#role-badge { padding: 2px 10px; border-radius: 999px; background: #2a2a40; font-size: 13px; }
main { flex: 1; padding: 16px; display: flex; flex-direction: column; gap: 16px; }
.control { display: flex; flex-direction: column; gap: 6px; font-size: 14px; }
.control input[type=range] { width: 100%; height: 44px; }
#grid { flex: 1; min-height: 240px; width: 100%; background: #14141d; border: 1px solid #2a2a40; border-radius: 12px; touch-action: none; }
#signals { display: flex; gap: 10px; flex-wrap: wrap; }
.signal { font-size: 24px; padding: 12px 18px; border-radius: 12px; border: 0; background: #2a2a40; color: #fff; }
footer { padding: 12px 16px; background: #15151c; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
button { font: inherit; }
#seize { padding: 12px 18px; border: 0; border-radius: 10px; background: #4a4ae0; color: #fff; }
#code { width: 96px; text-transform: uppercase; letter-spacing: 6px; font-size: 22px; text-align: center; padding: 8px; }
#pair-msg { font-size: 13px; opacity: .8; }
```

- [ ] **Step 4: Write the manifest**

```json
{
  "name": "Crowd Control",
  "short_name": "Control",
  "display": "standalone",
  "background_color": "#0b0b10",
  "theme_color": "#0b0b10",
  "start_url": "/",
  "icons": []
}
```

- [ ] **Step 5: Manual smoke test, then commit**

Run: `cd crowd-control && PORT=8080 npm start` then open `http://localhost:8080` in a browser; open a second tab. Verify: status shows "online"; a slider for the public "Color" control appears; the grid canvas responds to drag; tapping **Seize Master**, typing the code from the server log's session (use the mock-engine in Task 14 to see the code, or temporarily log `session.currentCode`) grants master and reveals the master-only "Speed" slider.

```bash
git add crowd-control/public/index.html crowd-control/public/app.js crowd-control/public/styles.css crowd-control/public/manifest.webmanifest
git commit -m "feat(crowd-control): phone PWA shell, ws client, DOM wiring"
```

---

## Task 14: Tools — mock engine + fake phones

**Files:**
- Create: `crowd-control/tools/mock-engine.js`
- Create: `crowd-control/tools/fake-phones.js`

**Interfaces:**
- Consumes: a running server (Task 11) + `ENGINE_SECRET`.
- Produces two CLI tools: `mock-engine.js` prints each snapshot's code + slot count (locks the TD-facing format); `fake-phones.js` opens N guest sockets and drives grid/control traffic for load testing.

- [ ] **Step 1: Write mock-engine.js**

```js
// crowd-control/tools/mock-engine.js
import { WebSocket } from 'ws';
const port = process.env.PORT || 8080;
const secret = process.env.ENGINE_SECRET || 'dev-secret';
const ws = new WebSocket(`ws://127.0.0.1:${port}/engine?secret=${secret}`);
ws.on('open', () => console.log('mock-engine connected'));
ws.on('message', (d) => {
  const m = JSON.parse(d.toString());
  if (m.type === 'snapshot') console.log(`code=${m.code} master=${m.masterSlot} slots=${m.slots.length}`, JSON.stringify(m.slots));
  else if (m.type === 'signal') console.log('SIGNAL', m.id, 'slot', m.slot);
});
ws.on('close', () => { console.log('closed'); process.exit(0); });
```

- [ ] **Step 2: Write fake-phones.js**

```js
// crowd-control/tools/fake-phones.js
import { WebSocket } from 'ws';
const port = process.env.PORT || 8080;
const N = Number(process.argv[2] || 10);
for (let i = 0; i < N; i++) {
  const ws = new WebSocket(`ws://127.0.0.1:${port}/`);
  ws.on('open', () => {
    ws.send(JSON.stringify({ type: 'hello', clientId: `fake-${i}` }));
    setInterval(() => {
      const x = Math.random(), y = Math.random();
      ws.send(JSON.stringify({ type: 'grid', x, y }));
      if (Math.random() < 0.05) ws.send(JSON.stringify({ type: 'control', id: 'hue', v: Math.random() }));
    }, 50);
  });
  ws.on('error', () => {});
}
console.log(`spawned ${N} fake phones against :${port}`);
```

- [ ] **Step 3: Manual verification**

Run in three terminals:
1. `cd crowd-control && ENGINE_SECRET=s PORT=8080 npm start`
2. `cd crowd-control && ENGINE_SECRET=s npm run mock-engine`
3. `cd crowd-control && npm run fake-phones 20`

Expected: mock-engine prints snapshots whose `slots.length` climbs toward the slotCap (24), then plateaus (overflow → spectators), with grid `x/y` changing each frame.

- [ ] **Step 4: Commit**

```bash
git add crowd-control/tools/mock-engine.js crowd-control/tools/fake-phones.js
git commit -m "feat(crowd-control): mock-engine + fake-phones dev tools"
```

---

## Task 15: TouchDesigner WebSocket DAT ingestion

**Files:**
- Create: `crowd-control/touchdesigner/crowd_ws_callbacks.py`

**Interfaces:**
- Consumes: the engine `snapshot`/`signal` messages from Task 11.
- Produces: WebSocket DAT callbacks that, on each snapshot, (a) write one row per slot into a Table DAT `crowd_slots` (columns: `slot role active x y` + one column per control id seen) and (b) write the current code into a Text DAT `crowd_code`. On `signal`, append to a `crowd_signals` Table DAT (slot, id, frame). Designed to be pasted into a WebSocket DAT's callback DAT — a SEPARATE WebSocket DAT from the 9980 MCP WebServer.

> TD-side code is verified manually against the live project + the mock-engine; there is no headless unit test (no TD runtime in CI). The message format was already locked by Tasks 8/11/14.

- [ ] **Step 1: Write crowd_ws_callbacks.py**

```python
# crowd-control/touchdesigner/crowd_ws_callbacks.py
"""
Crowd-Control WebSocket DAT callbacks (TouchDesigner side).

Setup (SEPARATE from the 9980 MCP WebServer DAT — do not reuse it):
  1. Create a WebSocket DAT (e.g. /project1/crowd_ws).
  2. Network Address = the Khadas localhost or tunnel host; Port = 8080;
     Path/Request = /engine?secret=<ENGINE_SECRET>; Active = On.
  3. Point its Callbacks DAT at a Text DAT holding this script.
  4. Create three Table DATs as siblings: 'crowd_slots', 'crowd_signals', and a Text DAT 'crowd_code'.
  5. Feed crowd_slots into a DAT-to-CHOP (+ Lag CHOP) for your channel logic;
     composite crowd_code into a Text TOP on the projection.
"""

import json

BASE_COLS = ['slot', 'role', 'active', 'x', 'y']


def onConnect(webSocketDAT):
    op('crowd_code')[0, 0] = '...'
    return


def onDisconnect(webSocketDAT):
    return


def onReceiveText(webSocketDAT, contents):
    try:
        msg = json.loads(contents)
    except Exception:
        return

    mtype = msg.get('type')
    if mtype == 'snapshot':
        _apply_snapshot(msg)
    elif mtype == 'signal':
        _apply_signal(msg)
    return


def _apply_snapshot(msg):
    # code → Text DAT
    code_dat = op('crowd_code')
    if code_dat is not None:
        code_dat.clear()
        code_dat.text = str(msg.get('code') or '')

    slots = msg.get('slots', [])

    # discover the union of control-value columns present this frame
    val_cols = []
    for s in slots:
        for k in (s.get('vals') or {}).keys():
            if k not in val_cols:
                val_cols.append(k)

    table = op('crowd_slots')
    if table is None:
        return
    table.clear()
    table.appendRow(BASE_COLS + val_cols)
    for s in slots:
        vals = s.get('vals') or {}
        row = [
            s.get('slot'), s.get('role'), 1 if s.get('active') else 0,
            s.get('x', 0), s.get('y', 0),
        ]
        for c in val_cols:
            v = vals.get(c, '')
            # booleans → 0/1 so downstream CHOP conversion is numeric
            if isinstance(v, bool):
                v = 1 if v else 0
            row.append(v)
        table.appendRow(row)


def _apply_signal(msg):
    sig = op('crowd_signals')
    if sig is None:
        return
    if sig.numRows == 0:
        sig.appendRow(['slot', 'id', 'frame'])
    sig.appendRow([msg.get('slot'), msg.get('id'), absTime.frame])
    # keep the table bounded
    while sig.numRows > 200:
        sig.deleteRow(1)
```

- [ ] **Step 2: Manual verification against the live project**

With the server + mock-engine running, point a real WebSocket DAT at `/engine?secret=<secret>`. In TD confirm: `crowd_code` updates as the code rotates; `crowd_slots` gains a row per connected phone with live `x/y`; firing a guest "burst" appends to `crowd_signals`. Confirm the 9980 MCP WebServer DAT is untouched and the MCP bridge still responds to `get_errors`.

- [ ] **Step 3: Commit**

```bash
git add crowd-control/touchdesigner/crowd_ws_callbacks.py
git commit -m "feat(crowd-control): TD WebSocket DAT ingestion (snapshot/signal)"
```

---

## Task 16: README + tunnel ops

**Files:**
- Create: `crowd-control/README.md`

**Interfaces:**
- Consumes: everything above.
- Produces: run instructions, env vars, and the Cloudflare Tunnel recipe that exposes the local server publicly for QR-code access.

- [ ] **Step 1: Write README.md**

````markdown
# crowd-control

Mobile crowd-control frontend for a live TouchDesigner projection.
Co-hosts on the Khadas with TD; exposed publicly via an outbound tunnel.
See the design spec: `../docs/superpowers/specs/2026-06-18-td-mobile-crowd-control-design.md`.

## Run (local)

```bash
npm install
ENGINE_SECRET=choose-a-secret PORT=8080 SHOW=shows/demo.json npm start
```

- `PORT` (default 8080), `SHOW` (default `shows/demo.json`), `ENGINE_SECRET` (default `dev-secret`).
- Phones open `http://<host>:8080`. TD connects to `ws://localhost:8080/engine?secret=<ENGINE_SECRET>`.

## Tests

```bash
npm test          # node --test across test/
```

## Public access via Cloudflare Tunnel (for QR / cellular phones)

1. Install `cloudflared` on the Khadas.
2. Quick tunnel (ephemeral URL):

   ```bash
   cloudflared tunnel --url http://localhost:8080
   ```

   It prints a public `https://<random>.trycloudflare.com` URL.
3. Generate a QR code pointing at that URL (any QR tool) and display it.
4. For a stable named hostname, use a named tunnel bound to a domain
   (`cloudflared tunnel create`, DNS route, `config.yml` → `service: http://localhost:8080`).

> Phones reach the server over the tunnel; TD ↔ server stays on localhost.
> The tunnel needs a reliable outbound uplink at the venue.

## TouchDesigner side

Paste `touchdesigner/crowd_ws_callbacks.py` into the callback DAT of a **new**
WebSocket DAT (NOT the 9980 MCP WebServer DAT). See that file's header for the
DAT wiring (crowd_slots / crowd_signals / crowd_code).

## Operator kill-switch

To clear master, freeze guest input, and blank the code: stop the server
(`Ctrl-C`) or restart it — session state is ephemeral and resets to NoMaster
with a fresh code. (A dedicated in-UI kill-switch endpoint is future work.)
````

- [ ] **Step 2: Verify the doc commands**

Run: `cd crowd-control && npm test` and confirm the command in the README matches reality (all suites pass).

- [ ] **Step 3: Commit**

```bash
git add crowd-control/README.md
git commit -m "docs(crowd-control): README + Cloudflare Tunnel ops"
```

---

## Self-Review

**Spec coverage:**
- §1 two tiers / per-guest channels → Tasks 4–8 (slots, roles, snapshot).
- §2 topology / Khadas + tunnel → Task 16 (ops), Task 11 (localhost engine channel).
- §3 four components → config (T2), control plane (T3–11), TD ingress (T15), PWA (T12–13).
- §4 wire protocol → Task 3 (parse/build) + Task 11 (engine snapshot/signal).
- §5 roles/slots/pairing/15s lock-out/2-min/30-min/code rotation → Tasks 4,5,7.
- §6 per-show config → Tasks 1,2.
- §7 TD ingestion + smoothing → Task 15 (Lag CHOP noted in the file header).
- §8 reconnect/abuse/rate-limit/kill-switch → Task 4 (sticky slots), Task 9 + Task 11 (rate limit), Task 16 (kill-switch via restart).
- §9 testing → Tasks 4–12 unit tests + Task 11 integration + Task 14 load tools.
- §10 defaults → Global Constraints (verbatim values).

**Operator kill-switch nuance:** the spec describes an in-session kill-switch (clear master, freeze guests, blank code). This plan delivers it via server restart (ephemeral state) and documents that; a dedicated runtime control is explicitly flagged as future work in Task 16. If you want it in-band, add a Task 17 (an authenticated `admin` ws/HTTP command toggling a `frozen` flag the session checks in `_authorized`).

**Placeholder scan:** no TBD/TODO/"add error handling" — every code step is complete. The one deliberately-simplified test (Task 9 middle test) is replaced with a concrete assertion in the same task.

**Type consistency:** `Session` methods (`connect/disconnect/pair/applyControl/applyGrid/applySignal/tick/guestCount/slotsUsed/roleOf`) are named identically across Tasks 4–8, the snapshot builder (Task 8), and the ws glue (Task 11). Protocol builders (`welcome/roleMsg/bumped/stateMsg/errorMsg`) match between Task 3 and Task 11. `buildSnapshot` shape matches the TD parser in Task 15.
