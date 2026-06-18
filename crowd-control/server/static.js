import { resolve, normalize, extname, sep } from 'node:path';
import { createReadStream, existsSync, statSync } from 'node:fs';

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.webmanifest': 'application/manifest+json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
};

export function resolveStaticPath(rootDir, urlPath) {
  let p = decodeURIComponent(urlPath.split('?')[0]);
  if (p === '/' || p === '') p = '/index.html';
  // Remove leading slash for safe joining; normalize to collapse .. and .
  const normalized = normalize(p.startsWith('/') ? p.slice(1) : p);
  // Block any remaining .. or absolute paths
  if (normalized.includes('..') || normalized.startsWith(sep)) return null;
  const abs = resolve(rootDir, normalized);
  // Ensure result is within rootDir
  if (!abs.startsWith(rootDir + sep) && abs !== rootDir) return null;
  return abs;
}

export function serveStatic(rootDir, req, res) {
  const abs = resolveStaticPath(rootDir, req.url || '/');
  if (!abs || !existsSync(abs) || !statSync(abs).isFile()) return false;
  res.writeHead(200, { 'Content-Type': MIME[extname(abs)] || 'application/octet-stream' });
  createReadStream(abs).pipe(res);
  return true;
}
