# Mask Combiner v2 — webapp piece selection + modify tools

Date: 2026-08-07
Status: approved (design Q&A in session; knife = subtractive loop, TD-served webapp, no-overwrite named outs)

## Problem

`cont_region_split` selects mask pieces by typing label IDs into `Submask1–15` string params, one GLSL select per out. Picking IDs is blind (read them off the 4×4 grid viewer) and editing a piece's shape is impossible. Replace the ID-typing flow with a visual webapp: see the pieces, select them by click/lasso, optionally edit the active piece, and send the union back as a named out TOP.

`cont_region_split` is NOT modified or removed. The new container sits alongside it.

## Container: `/project1/cont_mask_combiner`

| Op | Type | Purpose |
|----|------|---------|
| `in1` | inTOP | Label field (pixel R = pieceID/255, 0 = background). Wired from `/project1/moviefilein3` (same source as `cont_region_split`). |
| `webserver_mask` | webserverDAT | Port **8899** (changed from 9981 on 2026-08-08 to sit far from the bridge's 9980), active. Never touches `/project1/MCP_Server`. |
| `webbrowser_panel` | containerCOMP (palette webBrowser) | Hosts the webapp on the container's panel (added 2026-08-08); fills the panel, points at http://127.0.0.1:8899/. |
| `webserver_mask_callbacks` | textDAT | Endpoint handlers (below). Must never raise. |
| `mfi_<name>` | moviefileinTOP | One per send. Loads the sent PNG. `inputfiltertype=nearest`, `filtertype=nearest`. |
| `<name>` | outTOP | One per send, named by the user in the webapp. |

New ops placed left→right along dataflow near existing region-split comps; no user-placed op is moved. Container gets pinned in `layout.json` only if the user asks.

## HTTP endpoints (webserver_mask_callbacks)

- `GET /` → `touchdesigner/maskcombiner/index.html` read from disk each request, `Cache-Control: no-store` (stale-HTML lesson from attention-handoff).
- `GET /maskops.mjs` → `touchdesigner/maskcombiner/maskops.mjs` from disk, `text/javascript`, no-store (same module the node tests import).
- `GET /mask` → PNG snapshot of `in1` at native resolution (`top.save` to temp file, return bytes, `image/png`, no-store).
- `POST /send` → JSON `{ "name": str, "png_base64": str }`.
  - `name` sanitized to a valid TD op name (`[A-Za-z][A-Za-z0-9_]*`); collision with an existing child → suffix `_2`, `_3`, …
  - Body capped at 32 MB. Dimension validation without PIL: the PNG is written, loaded into the `moviefilein`, and its cooked width/height compared to `in1`; on mismatch the ops and file are removed and a 400 returned.
  - Written to `touchdesigner/assets/sent_masks/<name>_<unixms>.png` — **never overwrites** any existing file.
  - Creates `mfi_<name>` (nearest filtering) → `<name>` outTOP, wired, positioned left→right below previous outs.
  - Response `{ "ok": true, "out_path": "/project1/cont_mask_combiner/<name>", "file": "<png path>" }`; errors `{ "ok": false, "error": str }`.
- All handlers wrapped so an exception returns a 500 JSON, never kills the callback DAT.

## Webapp (`touchdesigner/maskcombiner/index.html` + `maskops.mjs`)

Single-page canvas app. On load, fetches `/mask`, reads the R channel into a `Uint8Array` of piece IDs. A **piece** = all pixels sharing one ID (ID equality, matching TD label semantics — not connected components). Each piece gets an editable binary bitmap initialized from its ID.

### Selection
- **Click** on a piece toggles its selected state. Selecting a piece makes it the **active** piece; clicking a selected piece deselects it (the previously selected piece, if any, becomes active).
- **Lasso tool**: freehand polygon; on mouseup it closes and every piece with **≥ 50% of its pixels inside** toggles. Last piece toggled *on* becomes active.
- **Selected** pieces render with an **animated diagonal stripe** overlay (canvas pattern, offset advanced by `requestAnimationFrame`).
- **Active** (last-selected) piece renders a **green contour outline**.
- The mask renders as **one flat composite image exactly as received** — no per-piece tinting, no grid of pieces (the 4×4 ID grid is the old method). Piece boundaries stay invisible until interaction: hovering shows a faint highlight of the piece under the cursor; the stripe/outline overlays are the only persistent per-piece visuals.

### Toolbar (all modify tools act ONLY on the active piece)
- **Fill voids** — flood-fill background from the bitmap border; unreached non-piece pixels (interior holes) become piece.
- **Knife** (subtractive loop) — freehand stroke, auto-closed end→start on mouseup; interior pixels are removed from the active piece.
- **Additive loop** — freehand stroke; valid only if **both endpoints lie on the active piece** (≤ 3 px tolerance). Closed end→start; interior pixels are added to the piece. Invalid stroke → toast message, no change.
- **Outset / Inset** — 8-neighbor morphological dilate / erode by 1 px per click.
- **Undo button** (changed from Ctrl+Z on 2026-08-08 — keystrokes don't forward reliably into the panel-embedded browser) — undo stack (≤ 50 entries) of `{pieceId, bitmap copy}` snapshots taken before each modify-tool edit; pop restores. Selection changes are not history entries.

### Send
- Name field (required, live-validated to TD op-name rules) + **Send Mask** button.
- Union of all **selected** piece bitmaps → white-on-black PNG at source resolution → `POST /send`.
- Success shows the created out path; failure shows the server error. Sending never clears the working state, so variant sends are cheap.

## Error handling
- `/mask` fetch failure → retry button, app unusable until loaded.
- POST failures surfaced in UI; server-side validation as listed above.
- Callback DAT edits during build follow the compile-then-swap rule (it is a separate server from the bridge, but same hygiene).

## Testing
- `maskops.mjs` holds the pure bitmap ops (polygon rasterize + interior fill, flood fill voids, dilate, erode, union, ≥50% lasso test, undo stack) as plain functions; `touchdesigner/maskcombiner/test_maskops.mjs` runs them under `node` with small synthetic bitmaps.
- TD side verified over the bridge: build container, `GET /mask` returns PNG of correct size; `POST /send` with a synthetic mask creates the out TOP; `image_stats`/pixel checks confirm mask content; `get_errors` clean.
- Bridge save discipline: `save_checkpoint` on `/project1` before first mutation (project may be untitled — `project.save()` risks the modal freeze), verify, checkpoint after.

## Out of scope
- Modifying or removing `cont_region_split` / its outs.
- Live-updating masks after send (a send is a bake).
- Multi-user simultaneous editing; auth on port 8899 (localhost tool).
