# crowd-control

Mobile crowd-control frontend for a live TouchDesigner projection.
Co-hosts on the Khadas with TD; exposed publicly via an outbound tunnel.
See the design spec: `../docs/superpowers/specs/2026-06-18-td-mobile-crowd-control-design.md`.

## Run (local)

```bash
npm install
ENGINE_SECRET=choose-a-secret PORT=8080 SHOW=shows/demo.json npm start
```

- `PORT` (default 8080), `SHOW` (default `shows/demo.json`), `ENGINE_SECRET` (default `dev-secret`).
- Phones open `http://<host>:8080`. TD connects to `ws://localhost:8080/engine?secret=<ENGINE_SECRET>`.

## Tests

```bash
npm test          # node --test across test/
```

## Public access via Cloudflare Tunnel (for QR / cellular phones)

1. Install `cloudflared` on the Khadas.
2. Quick tunnel (ephemeral URL):

   ```bash
   cloudflared tunnel --url http://localhost:8080
   ```

   It prints a public `https://<random>.trycloudflare.com` URL.
3. Generate a QR code pointing at that URL (any QR tool) and display it.
4. For a stable named hostname, use a named tunnel bound to a domain
   (`cloudflared tunnel create`, DNS route, `config.yml` → `service: http://localhost:8080`).

> Phones reach the server over the tunnel; TD ↔ server stays on localhost.
> The tunnel needs a reliable outbound uplink at the venue.

## TouchDesigner side

Paste `touchdesigner/crowd_ws_callbacks.py` into the callback DAT of a **new**
WebSocket DAT (NOT the 9980 MCP WebServer DAT). See that file's header for the
DAT wiring (crowd_slots / crowd_signals / crowd_code).

## Operator kill-switch

To clear master, freeze guest input, and blank the code: stop the server
(`Ctrl-C`) or restart it — session state is ephemeral and resets to NoMaster
with a fresh code. (A dedicated in-UI kill-switch endpoint is future work.)
