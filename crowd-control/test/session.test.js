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
  const s = new Session(cfg, { codeGen: (() => { let i = 0; const codes = ['AAA', 'BBB', 'CCC']; return () => codes[i++] || 'ZZZ'; })() });
  s.connect('c1', 'u1', 0);
  s.pair('c1', s.currentCode, 1000);
  const before = s.currentCode;
  const r = s.disconnect('c1', 2000);
  assert.equal(r.wasMaster, true);
  assert.equal(s.master, null);
  assert.equal(s.slots[0], null);
  assert.notEqual(s.currentCode, before);
});
