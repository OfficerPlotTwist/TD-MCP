// crowd-control/server/wsServer.js
import { createServer as createHttp } from 'node:http';
import { WebSocketServer } from 'ws';
import { resolve } from 'node:path';
import { Session } from './session.js';
import { buildSnapshot } from './snapshot.js';
import { TokenBucket } from './ratelimit.js';
import { serveStatic } from './static.js';
import {
  parseInbound, welcome, roleMsg, bumped, stateMsg, errorMsg,
} from './protocol.js';

let _connSeq = 0;

export function createServer({ config, port, publicDir, engineSecret, opts = {} }) {
  const session = new Session(config, opts);
  const now = () => Date.now();
  const rootDir = resolve(process.cwd(), publicDir);

  const httpServer = createHttp((req, res) => {
    if (serveStatic(rootDir, req, res)) return;
    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('not found');
  });

  const wss = new WebSocketServer({ noServer: true });
  const phones = new Map(); // connId -> ws
  let engine = null;

  httpServer.on('upgrade', (req, socket, head) => {
    const url = new URL(req.url, 'http://x');
    if (url.pathname === '/engine') {
      if (url.searchParams.get('secret') !== engineSecret) { socket.destroy(); return; }
      wss.handleUpgrade(req, socket, head, (ws) => { ws._engine = true; wss.emit('connection', ws, req); });
      return;
    }
    wss.handleUpgrade(req, socket, head, (ws) => wss.emit('connection', ws, req));
  });

  const send = (ws, obj) => { if (ws.readyState === ws.OPEN) ws.send(JSON.stringify(obj)); };

  wss.on('connection', (ws) => {
    if (ws._engine) { engine = ws; ws.on('close', () => { if (engine === ws) engine = null; }); return; }

    const connId = `c${++_connSeq}`;
    ws._connId = connId;
    ws._bucket = new TokenBucket(60, 60); // 60 msgs burst, 60/s sustained
    phones.set(connId, ws);

    ws.on('message', (data) => {
      if (!ws._bucket.take(now())) return; // silently drop floods
      const r = parseInbound(data.toString());
      if (!r.ok) { send(ws, errorMsg('badmsg', r.error)); return; }
      handle(connId, ws, r.msg);
    });

    ws.on('close', () => {
      const res = session.disconnect(connId, now());
      phones.delete(connId);
      if (res.wasMaster) broadcastState();
    });
  });

  function handle(connId, ws, msg) {
    switch (msg.type) {
      case 'hello': {
        const r = session.connect(connId, msg.clientId, now());
        send(ws, welcome({ clientId: msg.clientId, role: r.role, slot: r.slot, config, masterPresent: r.masterPresent }));
        broadcastState();
        break;
      }
      case 'pair': {
        const r = session.pair(connId, msg.code, now());
        if (!r.granted) { send(ws, errorMsg(r.error.code, r.error.message, r.error.retryInMs != null ? { retryInMs: r.error.retryInMs } : {})); break; }
        send(ws, roleMsg({ role: 'master', slot: 0 }));
        if (r.bumpedConnId) {
          const bws = phones.get(r.bumpedConnId);
          const bc = session.clients.get(r.bumpedConnId);
          if (bws) { send(bws, bumped()); send(bws, roleMsg({ role: bc ? bc.role : 'spectator', slot: bc ? bc.slot : null })); }
        }
        broadcastState();
        break;
      }
      case 'control': { const r = session.applyControl(connId, msg.id, msg.v, now()); if (!r.ok) send(ws, errorMsg(r.error.code, r.error.message)); break; }
      case 'grid':    { const r = session.applyGrid(connId, msg.x, msg.y, now()); if (!r.ok) send(ws, errorMsg(r.error.code, r.error.message)); break; }
      case 'signal':  {
        const r = session.applySignal(connId, msg.id, now());
        if (!r.ok) { send(ws, errorMsg(r.error.code, r.error.message)); break; }
        if (engine) send(engine, { type: 'signal', id: msg.id, slot: r.slot });
        break;
      }
      case 'ping': break;
    }
  }

  function broadcastState() {
    const st = stateMsg({ masterPresent: !!session.master, guestCount: session.guestCount(), slotsUsed: session.slotsUsed() });
    for (const ws of phones.values()) send(ws, st);
  }

  // housekeeping tick (1 Hz)
  const tickTimer = setInterval(() => {
    const r = session.tick(now());
    if (r.releasedMasterConnId) {
      const ws = phones.get(r.releasedMasterConnId);
      const c = session.clients.get(r.releasedMasterConnId);
      if (ws) send(ws, roleMsg({ role: c ? c.role : 'spectator', slot: c ? c.slot : null }));
      broadcastState();
    }
  }, 1000);

  // snapshot push to engine
  const snapHz = opts.snapshotHz || 60;
  const snapTimer = setInterval(() => {
    if (engine) send(engine, buildSnapshot(session));
  }, Math.max(5, Math.round(1000 / snapHz)));

  httpServer.listen(port);

  return {
    httpServer, wss, session,
    stop() {
      clearInterval(tickTimer); clearInterval(snapTimer);
      for (const ws of phones.values()) ws.terminate();
      if (engine) engine.terminate();
      return new Promise((res) => { wss.close(() => httpServer.close(() => res())); });
    },
  };
}
