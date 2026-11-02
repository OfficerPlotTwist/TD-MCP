import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { buildSaveScript, buildRestoreScript } from '../checkpoints.js';

function runPython(source) {
  const result = spawnSync('python', ['-c', source], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  return result.stdout;
}

test('checkpoint paths with quotes remain data in Python', () => {
  const source = buildSaveScript("/project1/quoted'name", "C:/temporary/quoted'name.tox");
  runPython(`import ast\nsource = ${JSON.stringify(source)}\nast.parse(source)\n`);
});

test('restore validates parent and loads snapshot before destroying', () => {
  const source = buildRestoreScript('/project1/example', '/tmp/example.tox');
  const prefix = `import os\nos.path.isfile = lambda path: True\nevents = []\nclass Existing:\n    def destroy(self): events.append('destroy')\nclass Parent:\n    def loadTox(self, path):\n        events.append('load')\n        raise ValueError('unreadable snapshot')\nexisting = Existing()\nparent = Parent()\ndef op(path): return parent if path == '/project1' else existing\n`;
  const indented = source.split('\n').map(line => '    ' + line).join('\n');
  runPython(`${prefix}\ntry:\n${indented}\nexcept ValueError: pass\nassert events == ['load'], events`);
  assert.throws(() => buildRestoreScript('/', '/tmp/x.tox'), /non-root/);
});
