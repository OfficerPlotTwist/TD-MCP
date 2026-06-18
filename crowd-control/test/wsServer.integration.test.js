// crowd-control/test/wsServer.integration.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { WebSocket } from 'ws';
import { createServer } from '../server/wsServer.js';

const config = {
  show: 'demo', slotCap: 4,
  controls: [
    { id: 'speed', type: 'slider', label: 'Speed', min: 0, max: 1, role: 'master' },
    { id: 'hue', type: 'slider', label: 'Color', min: 0, max: 1, role: 'public' },
  ],
  grid: { id: 'xy', role: 'public', perGuest: true },
  signals: [{ id: 'burst', label: '✦', role: 'public' }],
};

function open(url) {
  return new Promise((res, rej) => {
    const ws = new WebSocket(url);
    ws.once('open', () => res(ws));
    ws.once('error', rej);
  });
}
function next(ws) {
  return new Promise((res) => ws.once('message', (d) => res(JSON.parse(d.toString()))));
}

test('phone gets a welcome with config and guest role', async () => {
  const srv = createServer({ config, port: 0, publicDir: 'public', engineSecret: 's', opts: { codeGen: () => 'ABC' } });
  const port = srv.httpServer.address().port;
  const ws = await open(`ws://127.0.0.1:${port}/`);
  ws.send(JSON.stringify({ type: 'hello', clientId: 'u1' }));
  const msg = await next(ws);
  assert.equal(msg.type, 'welcome');
  assert.equal(msg.role, 'guest');
  assert.equal(msg.config.show, 'demo');
  ws.close();
  await srv.stop();
});

test('engine receives snapshots and a guest grid update reaches it', async () => {
  const srv = createServer({ config, port: 0, publicDir: 'public', engineSecret: 's', opts: { codeGen: () => 'ABC', snapshotHz: 50 } });
  const port = srv.httpServer.address().port;
  const engine = await open(`ws://127.0.0.1:${port}/engine?secret=s`);
  const phone = await open(`ws://127.0.0.1:${port}/`);
  phone.send(JSON.stringify({ type: 'hello', clientId: 'u1' }));
  await next(phone); // welcome
  phone.send(JSON.stringify({ type: 'grid', x: 0.3, y: 0.9 }));
  // read engine snapshots until one shows the grid value
  let seen = null;
  for (let i = 0; i < 20 && !seen; i++) {
    const snap = await next(engine);
    if (snap.type === 'snapshot') {
      const e = snap.slots.find((x) => x.x === 0.3 && x.y === 0.9);
      if (e) seen = e;
    }
  }
  assert.ok(seen, 'engine snapshot reflected the guest grid point');
  phone.close(); engine.close();
  await srv.stop();
});

test('engine with wrong secret is rejected', async () => {
  const srv = createServer({ config, port: 0, publicDir: 'public', engineSecret: 's', opts: { codeGen: () => 'ABC' } });
  const port = srv.httpServer.address().port;
  await assert.rejects(open(`ws://127.0.0.1:${port}/engine?secret=WRONG`));
  await srv.stop();
});
