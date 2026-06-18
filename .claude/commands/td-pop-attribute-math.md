# TD POP Attribute Math

Use this command note when the user asks Claude to adjust TouchDesigner POP point positions using native POP operators such as Attribute Combine POP and Math Combine POP.

Canonical instructions live at:

```text
.agents/skills/td-mcp/references/td-pop-attribute-math.md
```

Read that file before mutating the live TouchDesigner network.

Key reminder from the current `tile_chain_0_0` work:

- The current displacement is in the main POP chain, not inside `circle_point_render`.
- `attcombine1` copies `Color` to `height`.
- `mathcombine1` uses `height.rgb`, `compavg`, a `float3` `zaxis = (0, 0, 0.035)`, and writes the result back to `P`.
- `out1` is fed by `mathcombine1`.
- `circle_point_render/pop_attrs` points at `out1` and reads `P Color height brightness`.
- Do not recreate the old render-local `PointScale` or Script CHOP approach unless explicitly requested.
