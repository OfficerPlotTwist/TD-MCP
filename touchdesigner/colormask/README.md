# cont_colormask — Color Mask Selection Webapp

A browser app for building a live color mask from any TOP in the running TouchDesigner project, without leaving the browser to pick pixel colors by eye. Two selection tools — **magic wand** (connected-region flood fill) and **select by color** (frame-wide, disconnected regions included) — let you paint a combined mask; TD applies the result live, per frame, as a GPU color test. Connectivity (the "connected region" part of the wand) is computed once in the browser at gesture time; TD itself never flood-fills.

Cross-reference: [Color Mask Selection Webapp — Design Spec](../../docs/superpowers/specs/2026-08-07-color-mask-selection-webapp-design.md) (chosen approach, trade-offs, protocol). Prior art for the local-server + static-page pattern and the container-storage idiom: [GLSL Blob Tracker README](../blobtrack/README.md).

---

## Running the webapp

```
python touchdesigner/colormask/webapp/server.py --open
```

Starts a stdlib-only, `127.0.0.1`-only HTTP server on port **8902** (`--port` to override) and opens the browser tab. The server is the only thing that talks to TD, exclusively through the existing MCP bridge on `:9980` — the browser never calls TD directly.

| Endpoint | Behavior |
|----------|----------|
| `GET /` | Serves the static app (`static/index.html` + `app.js` + `floodfill.js` + `style.css`). No-store cache headers (lesson from the attention-handoff stale-HTML bug). |
| `GET /frame` | Snapshots `/project1/cont_colormask/null_src` via the bridge (`take_screenshot`) and returns it as PNG. |
| `POST /send` | Body `{rules: [{type, color:[r,g,b], tol}], stencil: {w, h, data: base64-raw}}`. Validates, zlib-compresses the stencil, builds one atomic `/execute` script against TD, and posts it to the bridge. |

---

## Wiring `in1`

`/project1/cont_colormask/in1` is an `inTOP` — wire any source TOP into the container's external input 0. This is the **only** way the source is chosen; there is no source picker in the webapp itself. `null_src` mirrors `in1` and is the snapshot target the webapp's `GET /frame` reads from.

---

## Tools and gestures

| Tool | Gesture | Effect |
|------|---------|--------|
| **Wand** | mousedown samples the seed color under the cursor; drag away from the click point grows tolerance live, re-flooding a downscaled buffer so the highlighted connected region visibly grows | Release commits a `wand` rule: reference color + tolerance + the flood-filled region, which is baked into the working **stencil**. |
| **Select by color** | Same click-and-drag gesture, but the live preview is a frame-wide color test (no flood) | Release commits a `bycolor` rule: reference color + tolerance, no stencil region — it stays live frame-wide, following disconnected regions anywhere. |
| **Ctrl+Z** (or Cmd+Z) | — | Pops the newest gesture and rebuilds the overlay + working stencil from the remaining gestures. |
| **SEND** (bottom-right) | — | Posts the combined rule list + stencil to TD in one atomic call, then clears the working set on success. The mask is live in TD from that point on. |
| **R** key / refresh button | — | Re-grabs the frame snapshot (no continuous streaming — snapshot-on-demand keeps the bridge quiet). |

The drag-distance-to-tolerance curve is a tuning constant, `TOL_PER_PIXEL` in `touchdesigner/colormask/webapp/static/app.js` (default `1/300`, capped at `MAX_TOL = 1.2`) — adjust there if the gesture feels too twitchy or too sluggish. The rule cap (`MAX_RULES = 32` in both `app.js` and `protocol.py`) is enforced client-side with a visible message before a 33rd gesture can commit.

---

## Stencil + live-color-test semantics

TD never flood-fills. Every frame it evaluates, per pixel:

```
mask(px) = OR over rules r of:
  wand rule:    stencil(px) == 1  AND  dist(src(px).rgb, r.refColor) <= r.tol
  bycolor rule:                        dist(src(px).rgb, r.refColor) <= r.tol
```

- `dist` is Euclidean RGB distance over normalized 0–1 channels — defined once and mirrored identically in `floodfill.js`'s `colorDist()` (browser preview) and `shaders/rules.frag`'s `distance()` (live GLSL mask), so the preview is truthful.
- **Wand regions are anchored where drawn.** The stencil freezes the connected region's *shape and position* at gesture time; only the *color test* inside that frozen area stays live. If a wand-selected object physically moves far from where it was selected, it leaves its stencil and drops out of the mask.
- **By-color rules are fully live, frame-wide** — no stencil, so they follow disconnected regions anywhere in the source, indefinitely.
- **Union stencil semantics:** there is exactly one stencil for the whole container, built as the union of every committed wand region's pixels. A wand rule's color test is evaluated across that *entire* union, not just the region it was drawn from — so adding a second wand region can only ever widen the mask, never narrow the first one, and a wand rule can pick up matching-color pixels inside a *different* wand's region too.
- **Known limitation (accepted trade-off, "approach A" in the spec):** because wand regions are anchored stencils rather than per-frame reflood, this fits mostly-static scenes. Approaches that re-flood per frame or reseed hybrid were considered and declined for complexity.

---

## Op table

| Op | Type | Role |
|----|------|------|
| `in1` | inTOP | External input 0 — user wires any source TOP here. |
| `null_src` | nullTOP | Mirror of `in1`; snapshot target for `GET /frame`. |
| `text_stencil_cb` | textDAT | Callbacks for `script_stencil`. |
| `script_stencil` | scriptTOP | Emits the last-SENT combined wand stencil as a single-channel (R) texture, from `fetch('colormask_stencil')` on container storage. Never reads another script op's cooked output (repo cook-loop rule). Emits 1×1 black when nothing has been sent. |
| `text_rules_cb` | textDAT | Callbacks for `script_rules`. |
| `script_rules` | scriptTOP | Emits the rules as an N×1 RGBA32F data texture from `fetch('colormask_rules')` on container storage. A single texel with `a = -1` means "no rules". |
| `text_rules_frag` | textDAT | GLSL source for `glsl_rules` (`shaders/rules.frag`). |
| `glsl_rules` | glslTOP | Input 0 = `null_src`, input 1 = `script_stencil`, input 2 = `script_rules`. Loops over the rule texture (`textureSize` gives the count, capped at 32 rules) and evaluates the mask formula above. Output resolution follows input 0. R = combined mask (1.0 selected), A = 1.0. |
| `text_viz_frag` | textDAT | GLSL source for `glsl_viz` (`shaders/viz.frag`). |
| `glsl_viz` | glslTOP | Input 0 = `null_src`, input 1 = `out_mask`. Tints the source magenta (60% blend) where masked, for eyeballing inside TD. |
| `out_mask` | outTOP ← `glsl_rules` | The deliverable mask. |
| `out_viz` | outTOP ← `glsl_viz` | Source tinted magenta where masked. |

All TOPs are nearest-filtered (`inputfiltertype`/`filtertype = nearest`) so mask edges never blur. The stencil is sampled with normalized coordinates, so its resolution need not match the source.

---

## Storage keys + rule texture encoding

Rules and the stencil live on **container storage** (`op('/project1/cont_colormask').store(...)`), not as parameters — `script_stencil` / `script_rules` read storage via `fetch`, never another script op's cooked output.

| Key | Written by | Shape | Contents |
|-----|-----------|-------|----------|
| `colormask_stencil` | SEND script | `{w, h, data: np.ndarray}` | Combined wand-region stencil, `uint8`, one byte per pixel, **TD (bottom-up) row order** — see orientation note below. |
| `colormask_rules` | SEND script | `list[(type_int, r, g, b, tol)]` | Validated rule tuples. `type_int`: 0 = wand (stencil-gated), 1 = bycolor (frame-wide). `r`, `g`, `b`, `tol` are floats normalized 0–1 (tol up to 2.0). |

`script_rules`' output texel encodes each rule as `rgb = reference color`, **`a = tol + 10 × type`** (`type` 1 = bycolor), so a texel's alpha alone tells the shader both the tolerance and the rule kind without a second lookup. A single texel with `a = -1` is the sentinel for "no rules" (empty mask).

The SEND script is one `/execute` call that stores stencil + rules and then force-cooks both `script_stencil` and `script_rules` as its last act, so a half-uploaded state never renders (storage writes are not cook dependencies, hence the explicit `cook(force=True)`).

### Orientation: `flipud` on SEND

The browser canvas is **top-down** (row 0 = top of the image, standard `<canvas>`/image convention); TD textures are **bottom-up** (row 0 = bottom, like every other TOP in this repo). The SEND script applies `np.flipud()` to the decoded stencil bytes before storing them, so `colormask_stencil` is already in TD's row order by the time `script_stencil` reads it — no orientation math is needed downstream in the shader.

---

## Tests

```
python -m pytest touchdesigner/colormask/tests -v
```
27 tests — rule validation (`protocol.validate_rules`), stencil compress/decompress round-trip byte-exactness, SEND script building, and the server's HTTP handling (`test_protocol.py`, `test_server.py`).

```
node --test touchdesigner/colormask/tests/floodfill.test.js
```
4 tests — `colorDist`, `floodFill` (4-connectivity, tolerance gating), and `byColorMask` against known pixel buffers. This is the shared selection math also used live in the browser (`static/floodfill.js`); its `colorDist` must stay identical to `distance()` in `shaders/rules.frag`.

```
python touchdesigner/colormask/tests/integration_td.py
```
Requires a live TD session with the MCP bridge up and `/project1/cont_colormask` built. Wires a temporary red Constant TOP into `in1`, sends known rules through the real `/send` path, reads `out_mask` back via `numpyArray`, and asserts exact pixel values — including a stencil-orientation check (top-half stencil selects only the top half of `out_mask`). Cleans up the temporary Constant TOP on exit. Prints `ALL INTEGRATION CHECKS PASSED` on success.
