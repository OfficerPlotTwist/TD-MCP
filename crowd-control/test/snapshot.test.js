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
