# TD network layout — SINGLE SOURCE OF TRUTH

This file + `layout.json` (same directory) are the **only** authority on network layout in this project. Every agent, hook, or script that positions, checks, or reorganizes operators MUST derive its behavior from here. If any other document, memory, or hook message conflicts with this file, **this file wins**.

## The rules

1. **User-placed operators are never moved** by agents or hooks unless the user explicitly requests it in the current task. No exceptions — not for layout checks, not for "cleanup while I'm here."
2. **`layout.json` pins the sanctioned layout.** Ops listed there are the *agreed* arrangement (currently: the `/project1` banded segmentation and the `cont_blobtrack_glsl` internals, both user-approved 2026-07-14). Pinned ops are restored to their pinned positions by the reorganize hook. **Ops not listed are user territory — hands off.**
3. **To change the layout, edit `layout.json`** (then the next Stop-hook pass applies it, or run the hook manually — see below). Never "fix" layout by ad-hoc node moves; that is how layout fights start.
4. **Wire direction ideal:** wires flow left→right (source `nodeX` strictly less than destination `nodeX`). This is *enforced* only among pinned ops. For unpinned (user) ops it is advisory — surface violations to the user, never auto-fix.
5. **New ops an agent creates** are placed sensibly on creation: left→right along the dataflow, near their function, without displacing neighbors. If a new op becomes permanent, pin it by adding it to `layout.json`.
6. **Never reposition anything inside `/project1/MCP_Server`** beyond ops you created — and never touch its server controls (see CLAUDE.md bridge rules).
7. Feedback loops are backward **references** (Feedback TOP target / `op()` expressions), not wires — they are exempt from rule 4 by construction.

## The sanctioned `/project1` layout (bands)

Seven horizontal bands, top→bottom in signal order, each with an `annotateCOMP` box (also pinned in `layout.json`):

| # | Band (annotate op) | Contents |
|---|--------------------|----------|
| 1 | `annotate_input` | Spout in → flip → cache/threshold → composite; camera control COMPs |
| 2 | `annotate_blobtrack` | `cont_blobtrack_glsl` + output monitors (null1–5, trail1, moviefileout1) |
| 3 | `annotate_blobdata` | blob table → top-blob CHOP → `blob_signal_processing` → null6; drop-detect chain |
| 4 | `annotate_resttrig` | `cont_rest_trigger` + monitors null8–10 |
| 5 | `annotate_triggers` | trigger1/2/3, trigger_blobdrop → merge1 → master_controls |
| 6 | `annotate_render` | spiderweb → out1 |
| 7 | `annotate_util` | error DAT, web/websocket servers, cont_nearestpixel |

## `cont_colormask`

A second pinned container, alongside `cont_blobtrack_glsl`, for the color-mask selection webapp. Pinned in `layout.json` under `/project1` (`cont_colormask: [1900, -300]`) and internally under `/project1/cont_colormask` (`parkDocked: true`), left→right: `in1`/`null_src` → `text_stencil_cb`+`script_stencil` / `text_rules_cb`+`script_rules` → `text_rules_frag`+`glsl_rules` → `text_viz_frag`+`glsl_viz` → `out_mask`/`out_viz`. See [`touchdesigner/colormask/README.md`](colormask/README.md) for op semantics.

## Who reads this

| Consumer | Behavior |
|----------|----------|
| `td-mcp-server/hooks/reorganize.mjs` (Stop hook) | Applies `layout.json` pinned positions **only**. Touches nothing unlisted. |
| `td-mcp-server/hooks/check-wires.mjs` (Stop hook) | Validates left→right **only** for wires whose both endpoints are pinned. Block message points here. |
| Agents (CLAUDE.md → this file) | Rules 1–7 above. |
| Memory `td-wires-left-to-right` / `td-dont-move-user-operators` | Pointers to this file, not independent authorities. |

Apply the layout manually any time with:

```
echo {} | node td-mcp-server/hooks/reorganize.mjs
```
