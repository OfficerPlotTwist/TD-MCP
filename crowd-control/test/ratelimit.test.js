import { test } from 'node:test';
import assert from 'node:assert/strict';
import { TokenBucket } from '../server/ratelimit.js';

test('allows up to capacity immediately', () => {
  const b = new TokenBucket(5, 10);
  for (let i = 0; i < 5; i++) assert.equal(b.take(0), true);
  assert.equal(b.take(0), false); // exhausted
});

test('refills 1 token per 100ms at 10/s', () => {
  const b = new TokenBucket(5, 10);
  for (let i = 0; i < 5; i++) b.take(0); // drain
  assert.equal(b.take(100), true);       // +1 token at t=100ms
  assert.equal(b.take(100), false);      // none left
});

test('refill math: 1s restores full capacity', () => {
  const b = new TokenBucket(5, 5);
  for (let i = 0; i < 5; i++) b.take(0);
  assert.equal(b.take(1000), true);
});
