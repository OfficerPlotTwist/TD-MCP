---
description: Generate 3x3 shader-thumbnail review contact-sheet(s) from the ranked OpenGLSL candidate pool, then display them for approval via /looksgood.
argument-hint: [count]
allowed-tools: [Bash, Read]
---

Produce shader review grids and show them to the user.

`$ARGUMENTS` is an optional integer = how many grids to build (default 1). Each grid consumes the next ≤9 unreviewed, texture-free candidates ranked by `composite_score` descending.

Steps:

1. If `shader_pipeline/candidates.json` does not yet exist, first build the pool:
   `python "C:\Users\nik\Documents\AI\MCP\TD MCP\scripts\shader_candidates.py"`
2. Build the grid(s):
   `python "C:\Users\nik\Documents\AI\MCP\TD MCP\scripts\build_shader_grid.py" $ARGUMENTS`
   The script prints one line per grid: `<grid_id>  (N tiles)  <absolute_png_path>`.
3. For each printed PNG path, use the Read tool to display the image so the user can see the 9 numbered tiles and the caption bar.
4. Tell the user how to approve, e.g.:
   `/looksgood 13 sgr_0003`  → approve tiles 1 and 3; double a digit (e.g. `133`) to favorite + push to front; `/looksgood 00 sgr_0003` to reject the whole grid.

If the script reports no unreviewed candidates remain, tell the user the pool is exhausted (re-run `shader_candidates.py` to reset or extend the pool).
