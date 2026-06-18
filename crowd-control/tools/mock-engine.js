// crowd-control/tools/mock-engine.js
import { WebSocket } from 'ws';
const port = process.env.PORT || 8080;
const secret = process.env.ENGINE_SECRET || 'dev-secret';
const ws = new WebSocket(`ws://127.0.0.1:${port}/engine?secret=${secret}`);
ws.on('open', () => console.log('mock-engine connected'));
ws.on('message', (d) => {
  const m = JSON.parse(d.toString());
  if (m.type === 'snapshot') console.log(`code=${m.code} master=${m.masterSlot} slots=${m.slots.length}`, JSON.stringify(m.slots));
  else if (m.type === 'signal') console.log('SIGNAL', m.id, 'slot', m.slot);
});
ws.on('close', () => { console.log('closed'); process.exit(0); });
