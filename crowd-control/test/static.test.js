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
