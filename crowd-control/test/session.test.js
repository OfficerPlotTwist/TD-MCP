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
