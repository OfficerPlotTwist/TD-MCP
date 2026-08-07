# Mask Combiner v2 (`cont_mask_combiner`)

Visual replacement for the `cont_region_split` Submask-ID workflow. The container
serves a webapp at http://127.0.0.1:9981/ from `index.html` in this directory.

- `in1` — label field (R = pieceID/255), wired from `/project1/moviefilein3`.
- Click a piece to toggle select (animated stripes); last selected = active (green outline).
- Lasso toggles every piece ≥50% inside the loop.
- Toolbar edits the ACTIVE piece only: Fill Voids, Knife (closed loop removes interior),
  Add Loop (both stroke ends on the piece; enclosed region added), Outset/Inset (±1px).
  Ctrl+Z undoes the last edit.
- Send Mask unions all selected pieces into one white-on-black PNG, saved to
  `touchdesigner/assets/sent_masks/<name>_<ts>.png` (never overwritten), and creates
  `mfi_<name>` → `<name>` out TOP on the container.

Callbacks source of truth: `webserver_callbacks.py` (loaded into the
`webserver_mask_callbacks` textDAT). Tests: `node test_maskops.mjs`,
`python test_callbacks.py`. Spec:
`docs/superpowers/specs/2026-08-07-mask-combiner-webapp-design.md`.
