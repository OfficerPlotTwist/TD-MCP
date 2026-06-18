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
