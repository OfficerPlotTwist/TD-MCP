# Shader Grid Workflow

Use this workflow when the user asks to generate shader review grids from the ranked OpenGLSL candidate pool.

The optional count argument is the number of 3x3 grids to build. Default to `1`. Each grid consumes the next up-to-9 unreviewed, texture-free candidates ranked by `composite_score` descending.

If `shader_pipeline/candidates.json` does not exist, build the pool:

```powershell
python "C:\Users\nik\Documents\AI\MCP\TD MCP\scripts\shader_candidates.py"
```

Build the grid or grids:

```powershell
python "C:\Users\nik\Documents\AI\MCP\TD MCP\scripts\build_shader_grid.py" <count>
```

The script prints one line per grid:

```text
<grid_id>  (N tiles)  <absolute_png_path>
```

Open each printed PNG path with an image viewer tool available in the current Codex environment so the user can see the 9 numbered tiles and caption bar.

Tell the user how to approve:

```text
/looksgood 13 sgr_0003
```

This approves tiles 1 and 3. Doubling a digit, such as `133`, favorites that tile and pushes it to the front. Use:

```text
/looksgood 00 sgr_0003
```

to reject the whole grid.

If the script reports no unreviewed candidates remain, tell the user the pool is exhausted and that rerunning `shader_candidates.py` can reset or extend the pool.
