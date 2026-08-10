# Mask Combiner v2 (`cont_mask_combiner`)

Visual replacement for the `cont_region_split` Submask-ID workflow. The container
serves a webapp at http://127.0.0.1:8899/ from `index.html` in this directory
(port kept far from the MCP bridge's 9980), and hosts it directly on its own
panel: the container's Background TOP is `webrender1`, with `panelexec1` /
`keyboardin1` forwarding mouse and keys (flattened from the palette webBrowser
component — its `parent.WebBrowser` binds were stripped to constants and their
`bindExpr` strings cleared; constants are required or CEF never starts, and a
leftover bindExpr string still errors in the param-dialog UI even in constant
mode). Open the container's viewer to use it inside TD,
or use any external browser.

- `in1` — label field (R = pieceID/255), wired from `/project1/moviefilein3`.
- Click a piece to toggle select (animated stripes); last selected = active (green outline).
- Lasso toggles every piece ≥50% inside the loop.
- Toolbar edits the ACTIVE piece only: Fill Voids, Knife (closed loop removes interior),
  Add Loop (both stroke ends on the piece; enclosed region added), Outset/Inset (±1px).
  The Undo toolbar button undoes the last edit (button, not Ctrl+Z — keystrokes
  don't forward reliably into panel-embedded browsers).
- Panel-only operation: the Reload toolbar button refetches the mask (discards
  edits/selection); the container's `Reload App` custom pulse par restarts the
  embedded browser. No workflow requires entering the container.
- Send Mask unions all selected pieces into one white-on-black PNG, saved to
  `touchdesigner/assets/sent_masks/<name>_<ts>.png` (never overwritten), and creates
  `mfi_<name>` → `<name>` out TOP on the container.

Callbacks source of truth: `webserver_callbacks.py` (loaded into the
`webserver_mask_callbacks` textDAT). Tests: `node test_maskops.mjs`,
`python test_callbacks.py`. Spec:
`docs/superpowers/specs/2026-08-07-mask-combiner-webapp-design.md`.
