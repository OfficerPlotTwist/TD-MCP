# Shader Curation → TouchDesigner Implementation Pipeline

Turns the 502-shader OpenGLSL reference pile into a curated, prioritized, build-ready
queue with one terse command per review grid.

Corpus: `C:\Users\nik\Documents\AI\OpenGLSL_Code_Reference`
(502 `.frag` in `dailies/shaders/`; `manifest_in.json` + `findings.json`).

## Data flow

```
candidates.json ──(ranked, texture-free pool)──> build_shader_grid.py
        │                                              │
        │                                              ▼
        │                                    review_grids/sgr_NNNN.png   (3x3, tiles 1-9)
        │                                    review_grids.json (tile→shader map, verbose path)
        ▼                                              │
   /shadergrid  ◄────────────────────────────────────┘   (human views grid)
                                                           │
   /looksgood <numbers> <id##>  ──────────────────────────┘
        │
        ├─ human_selected_good_shaders.json   (+favorite tag on doubled digits)
        ├─ implementation_queue.json          (favorites at front)
        └─ TouchDesigner /project1/shader_queue  (Table DAT, via td_queue_sync.py)
```

## DBs (in this folder; checkpoints.js-style `{collection:[...]}`, pretty JSON)

| File | Collection | Role |
|------|-----------|------|
| `candidates.json` | `candidates` | Master pool. `in_pool` = scored ∧ texture-free ∧ has thumb. `reviewed` flips when a grid consumes it. |
| `review_grids.json` | `grids` | One record per grid: `id` (`sgr_NNNN`), verbose `png_path`, `status`, `tiles` (1–9 → shader). |
| `human_selected_good_shaders.json` | `shaders` | Approved shaders. Has the **`favorite`** tag, `td_status`, `td_path`. |
| `implementation_queue.json` | `queue` | Ordered build queue; favorites at the front; `rank` 1..N. |
| `rejected_shaders.json` | `rejected` | Audit trail of every shader passed over: `reason` is `not_selected` (un-approved tile on a resolved grid) or `grid_rejected_00` (whole grid rejected). Each record has `sid, src_id, src_name, composite_score, source_grid_id, reason, rejected_at`. Deduped by sid. |

## Concurrency

Safe for **parallel agents**. Every command (`/looksgood`, grid build, `regenerate`)
wraps its read-modify-write in a coarse cross-process mutex (`pipeline_lock()` in
`_db.py`, an exclusive-create lock at `shader_pipeline\.pipeline.lock`, 30 s wait,
120 s stale-reclaim), and `save_db` writes atomically (temp file + `os.replace`). Two
agents resolving different grids at the same time serialize cleanly — no lost approvals,
no partial reads.

## Commands

- **`/shadergrid [count]`** — build `count` grids (default 1) from the next ranked candidates and display them.
- **`/looksgood <numbers> <id##>`** — approve tiles, enqueue, favorite doubles, delete the grid, sync the TD DAT.
  - **Auto-replenish:** when `/looksgood` resolves the *last pending* grid, it automatically builds the next batch of up to **10** grids (capped by the remaining pool) so there's always more to review. Built into `looksgood.py` (no harness hook needed).
  - `<numbers>` digits 1–9 (`13357` or `1 3 3 5 7`); a digit **twice** → favorite + front; token **`00`** → reject all.
  - `<id##>` is the **last** token; its final 4 digits are the per-grid counter (`sgr_0007`, `0007`, or `7`).

## Scripts

- `scripts/shader_candidates.py` — (re)build `candidates.json`. Re-running resets `reviewed` to false (fresh start).
- `scripts/build_shader_grid.py` — Pillow grid composer.
- `scripts/looksgood.py` — approval resolver (no TD dependency).
- `scripts/td_queue_sync.py` — TD-side: materialize the queue Table DAT + gold-flag implemented favorites. `exec`'d inside TD via the MCP `execute_script` tool.

## Grid location, regeneration & boot watcher

Review-grid PNGs live under `C:\Users\nik\Documents\AI\Busdriver\review_grids\`, one
subdirectory per pipeline. This pipeline's folder is **`GLSL implement with agents\`**
(`GRID_IMG_DIR` in `_db.py`). Each pipeline subdir contains its own `regenerate.py`.

- **`<subdir>\regenerate.py`** — destroys this pipeline's currently *pending* grids and
  rebuilds a fresh batch. **Non-destructive:** it returns the destroyed grids' shaders to
  the candidate pool (`reviewed→false`) so they're valid targets again, but **never**
  returns a shader already in `human_selected_good_shaders.json` or `rejected_shaders.json`
  — your approve/reject decisions always stand. Safe to run manually with grids still present.
- **`review_grids\watcher.py`** — boot scanner. For every pipeline subdir that has a
  `regenerate.py` but **no grid PNGs** (empty), it runs that subdir's `regenerate.py`.
  Subdirs that still have pending grids are left untouched.

## Deferred: the build/drain step

Approval is **enqueue-only** by design. Building queued shaders into live TD GLSL-TOP
networks is a separate phase (a future `/buildqueue [n]`), because it needs a
ShaderToy/GLSLSandbox → TD-GLSL dialect adapter (wrap `mainImage`, map
`iTime/iResolution/iMouse` and `time/resolution/mouse` to TD uniforms, `gl_FragColor`
→ `TDOutputSwizzle`). The drainer will reuse the `shaders/cartoon/build_network.py`
recipe (textDAT → `glslTOP.par.pixeldat` → uniforms), pop from the front of
`implementation_queue.json`, set `td_status=implemented` + `td_path`, and place each
network clear of the existing node cluster.

v1 pool = the ~48 ShaderToy shaders that carry a `findings.json composite_score`. The
410 GLSLSandbox shaders have no score yet; a later pass can score them (the corpus's
Playwright `render_shaders.py` already computes the same metrics) to extend the pool.
