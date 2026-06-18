// crowd-control/tools/fake-phones.js
import { WebSocket } from 'ws';
const port = process.env.PORT || 8080;
const N = Number(process.argv[2] || 10);
for (let i = 0; i < N; i++) {
  const ws = new WebSocket(`ws://127.0.0.1:${port}/`);
  ws.on('open', () => {
    ws.send(JSON.stringify({ type: 'hello', clientId: `fake-${i}` }));
    setInterval(() => {
      const x = Math.random(), y = Math.random();
      ws.send(JSON.stringify({ type: 'grid', x, y }));
      if (Math.random() < 0.05) ws.send(JSON.stringify({ type: 'control', id: 'hue', v: Math.random() }));
    }, 50);
  });
  ws.on('error', () => {});
}
console.log(`spawned ${N} fake phones against :${port}`);
