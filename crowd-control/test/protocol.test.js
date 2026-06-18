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
