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
