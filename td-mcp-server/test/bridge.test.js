import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

test('MCP startup from another cwd and HTTP forwarding', async () => {
  const requests = [];
  const server = http.createServer(async (req, res) => {
    let body = '';
    for await (const chunk of req) body += chunk;
    requests.push({ url: req.url, body: body ? JSON.parse(body) : null });
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify(req.url === '/execute' ? { output: 'mock TD output', errors: [] } : { status: 'ok', errors: [] }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const temp = mkdtempSync(join(tmpdir(), 'td-mcp-test-'));
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [fileURLToPath(new URL('../index.js', import.meta.url))],
    cwd: temp,
    env: { ...process.env, TD_HOST: '127.0.0.1', TD_PORT: String(server.address().port), TD_CHECKPOINTS_DIR: temp },
    stderr: 'pipe',
  });
  const client = new Client({ name: 'test-client', version: '1' });
  try {
    await client.connect(transport);
    const listed = await client.listTools();
    assert.ok(listed.tools.some(tool => tool.name === 'execute_script'));
    assert.ok(listed.tools.some(tool => tool.name === 'restore_checkpoint'));
    assert.ok(listed.tools.some(tool => tool.name === 'take_screenshot'));
    const instruction = client.getInstructions();
    assert.match(instruction, /new unused/);
    assert.doesNotMatch(instruction, /execute_script\("project.save\(\)"\)/);
    const validated = await client.callTool({ name: 'validate_script', arguments: { script: 'print(1)' } });
    assert.ok(validated.content[0].text);
    const result = await client.callTool({ name: 'execute_script', arguments: { script: 'print(123)' } });
    assert.equal(JSON.parse(result.content[0].text).output, 'mock TD output');
    assert.ok(requests.some(r => r.body?.script === 'print(123)'));
    const quoted = "/project1/quoted'name";
    await client.callTool({ name: 'get_par_value', arguments: { path: quoted, par_name: 'period' } });
    const getScript = requests.at(-1).body.script;
    const readResult = spawnSync('python', ['-c', `from types import SimpleNamespace\ndef op(path):\n    assert path == ${JSON.stringify(quoted)}\n    return SimpleNamespace(par=SimpleNamespace(period=SimpleNamespace(val=0.5)))\n${getScript}`], { encoding: 'utf8' });
    assert.equal(readResult.status, 0, readResult.stderr);
    assert.equal(readResult.stdout.trim(), '0.5');
    await client.callTool({ name: 'set_par_value', arguments: { path: quoted, par_name: 'period', value: '0.75' } });
    const setScript = requests.at(-1).body.script;
    const writeResult = spawnSync('python', ['-c', `from types import SimpleNamespace\nparameter = SimpleNamespace(val=0)\ndef op(path): return SimpleNamespace(par=SimpleNamespace(period=parameter))\n${setScript}\nassert parameter.val == 0.75`], { encoding: 'utf8' });
    assert.equal(writeResult.status, 0, writeResult.stderr);
    const checkpoints = await client.callTool({ name: 'list_checkpoints', arguments: {} });
    assert.equal(JSON.parse(checkpoints.content[0].text).count, 0);
  } finally {
    await client.close();
    await new Promise(resolve => server.close(resolve));
    rmSync(temp, { recursive: true, force: true });
  }
});

test('HTTP failures and timeouts preserve uncertainty', async () => {
  const original = globalThis.fetch;
  const bridge = await import('../td-bridge.js');
  try {
    globalThis.fetch = async () => ({ ok: false, status: 503, text: async () => 'unavailable' });
    await assert.rejects(bridge.executeScript('pass'), /503.*unavailable/);
    globalThis.fetch = async () => { throw new DOMException('timeout', 'TimeoutError'); };
    await assert.rejects(bridge.executeScript('pass'), /may still have completed/);
    assert.equal(await bridge.isConnected(), false);
  } finally { globalThis.fetch = original; }
});
