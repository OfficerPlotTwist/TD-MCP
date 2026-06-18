// crowd-control/server/index.js
import { resolve } from 'node:path';
import { loadConfig } from './config.js';
import { createServer } from './wsServer.js';

const showPath = process.env.SHOW || 'shows/demo.json';
const port = Number(process.env.PORT || 8080);
const engineSecret = process.env.ENGINE_SECRET || 'dev-secret';

const config = loadConfig(resolve(process.cwd(), showPath));
const srv = createServer({ config, port, publicDir: 'public', engineSecret });
console.log(`crowd-control "${config.show}" listening on http://0.0.0.0:${port}`);

process.on('SIGINT', async () => { await srv.stop(); process.exit(0); });
