# Color Mask Selection Webapp — Design Spec

**Date:** 2026-08-07
**Status:** Approved (brainstorm 2026-08-07)
**Related:** [Blob Tracker README](../../../touchdesigner/blobtrack/README.md) (JFA prior art, storage idiom), attention-handoff webapp (`.claude/skills/attention-handoff-td/tools/`) (local-server + static-page pattern)

---

## Purpose

A browser app for building a live color mask from any TOP in the running TouchDesigner project. Two selection tools:

- **Magic wand** — click samples the color under the cursor; dragging away from the click point grows the color tolerance live, so the connected region visibly grows until release commits it.
- **Select by color** — click samples a color; every pixel in the frame within tolerance is selected, **including disconnected regions**; drag grows tolerance the same way.

Gestures accumulate; **Ctrl+Z** removes the newest gesture; a bottom-right **SEND** button commits the combined mask to TD (live from then on) and clears the working set.

## Chosen approach (from brainstorm)

**Stencil + live color test.** Connectivity (the "connected region" part of the wand) is computed **in the browser at gesture time** on a frame snapshot. TD never flood-fills; it applies, per frame:

```
mask(px) = OR over rules r of:
  wand rule:    stencil(px) == 1  AND  dist(src(px).rgb, r.refColor) <= r.tol
  bycolor rule:                        dist(src(px).rgb, r.refColor) <= r.tol
```

- Wand regions are **anchored where drawn** (stencil), but stay color-live inside that area.
- By-color rules are **fully live frame-wide** — they follow disconnected regions anywhere.
- `dist` = Euclidean RGB distance, normalized 0–1 channels. The formula is defined once and mirrored **identically** in JS (preview) and GLSL (live mask) so the preview is truthful.

Trade-off accepted: an object selected with the wand that physically moves far from where it was selected leaves its stencil and drops out of the mask. Approach B (per-frame reflood in TD) and C (hybrid reseed) were considered and declined for complexity; A fits mostly-static scenes.

---

## TD side: `/project1/cont_colormask`

New container. Its network position is pinned via `touchdesigner/layout.json` per LAYOUT.md; no user-placed operators are moved.

| Op | Type | Role |
|----|------|------|
| `in1` | inTOP | User wires any source TOP here (the only way the source is chosen — no picker in the webapp). |
| `null_src` | nullTOP | Mirror of `in1`; snapshot target for the webapp. |
| `script_stencil` | scriptTOP | Emits the last-SENT combined wand stencil as a single-channel (R) texture. Reads `fetch('colormask_stencil')` from container storage — never another script op's cooked output (repo cook-loop rule). Emits 1×1 black when nothing has been sent. |
| `script_rules` | scriptTOP | Emits the rules as an **N×1 RGBA32F data texture** from `fetch('colormask_rules')`: rgb = reference color, `a = tol + 10×type` (type 1 = bycolor); a single texel with `a = -1` means "no rules". Data-driven — the shader never recompiles and no uniform plumbing is needed. |
| `glsl_rules` | glslTOP | Input 0 = `null_src`, input 1 = `script_stencil`, input 2 = `script_rules`. Loops over the rule texture (`textureSize` gives the count, capped at **32 rules** by the webapp/validator). Output resolution follows input 0. R = combined mask (1.0 selected), A = 1.0. |
| `out_mask` | outTOP | The deliverable mask. |
| `out_viz` | outTOP ← `glsl_viz` | Source tinted magenta where masked, for eyeballing inside TD. |

- **All TOPs nearest-filtered** (`inputfiltertype`/`filtertype = nearest`) — masks must not blur.
- Stencil is sampled with **normalized coordinates** in the shader, so its resolution need not match the source.
- Rules and stencil are stored on the container (`store`). The SEND script writes both, then force-cooks `script_stencil` and `script_rules` as its last act — one `/execute` script, so a half-uploaded state never renders. (Storage changes are not cook dependencies, hence the explicit cook.)
- Stencil transport format: browser sends raw uint8 grayscale bytes (width × height) → server zlib-compresses → base64 → TD script decodes with `zlib` + `numpy` (no PIL dependency).

## Webapp: `touchdesigner/colormask/webapp/`

Static page + small local Python server (attention-handoff pattern). The server is the only thing that talks to TD, exclusively through the existing MCP bridge on port 9980.

| Endpoint | Behavior |
|----------|----------|
| `GET /` | Serves the app (`static/index.html` + `app.js` + `style.css`). No-store cache headers (lesson from attention-handoff stale-HTML bug). |
| `GET /frame` | Grabs a snapshot of `null_src` via the bridge (`take_screenshot`, TOP-only — fine) and returns it as PNG. |
| `POST /send` | Body: `{rules: [{type, color:[r,g,b], tol}], stencil: {w, h, data: base64-raw}}`. Server zlib-compresses the stencil, builds one `/execute` script that stores stencil + rules + bumps generation, posts it to the bridge. Empty `rules` clears the mask to black (this is also the reset path). |

### Browser interaction

- Frame fills the view; slim toolbar (tool toggle: Wand / By-color); **SEND** pinned bottom-right; refresh button + `R` key re-grab the frame. No continuous streaming — snapshot on demand keeps the bridge quiet.
- **Wand:** mousedown samples seed color, flood-fills at tol 0; drag distance → tolerance; re-flood live (on a downscaled buffer if the frame is large); release commits `{type: wand, color, tol}` + its filled region into the working stencil canvas.
- **By-color:** same gesture, but the highlight is a frame-wide color test (no flood), and the committed rule carries no stencil region.
- Working selection = magenta overlay. Committed gestures = chips (tool icon + color swatch + tol value). **Ctrl+Z** pops the newest gesture and rebuilds overlay + stencil from the remaining ones.
- **SEND** posts rules + combined stencil, clears the working set on 200.
- Flood fill: scanline fill on the snapshot's pixel buffer with the shared color-distance predicate.

## Error handling

- Bridge unreachable / TD busy → server returns 503; UI shows a red banner with a retry; working set stays in the browser, nothing lost.
- SEND is atomic in TD (single script, generation counter last).
- Rule cap: the UI refuses to commit a 33rd rule with a visible message.
- Save discipline per CLAUDE.md applies around mutating bridge calls (checkpoint-first; note the untitled-save modal gotcha — use `save_checkpoint`, not `project.save()`, if the project is untitled).

## Testing

1. **Server unit tests** (pytest): rule JSON validation, stencil compress→decompress roundtrip byte-exactness.
2. **Bridge integration check:** wire a synthetic Constant/Ramp TOP into `in1`, POST known rules, read `out_mask` back via `numpyArray`, assert exact pixel values. Ground truth that JS and GLSL agree on the distance formula.
3. **Manual pass** on the real wired feed for gesture feel; the drag-distance→tolerance curve is a named tuning constant in `app.js`.

## Out of scope (deliberate)

- Subtract/exclude gestures (additive + Ctrl+Z only).
- Multiple named mask slots (one combined `out_mask`).
- Region tracking of moving objects (approach B/C — revisit only if the anchored-stencil limitation bites in practice).
- Source-TOP picker UI (wiring `in1` in TD is the picker).
