# Reusable TouchDesigner session learnings

Consolidated on 2026-11-02 from repository guidance, existing bridge source, recent TouchDesigner work transcripts, and recovery summaries. These are historical observations and authoring conventions, not claims about every TD version or the current user's network. Inspect the installed build and live state before applying them. No private project path or device mapping is required by this repository.

## Bridge deployment and execution

- A live COMP may still embed an older callback after repository source changes. Inspect its Text DAT; changing a file on disk does not deploy it. Exported bridges should embed callbacks, use sibling-relative Error DAT references, and avoid external File In DAT dependencies.
- Prior `exec(script)` callbacks used different global/local scopes; nested functions could fail with `name ... is not defined` despite a variable/import being defined above them. The current callback uses one fresh namespace per request. Old installations still need iterative loops or explicit arguments until updated.
- `COMP.children` is a list. Calling `children()` produces `'list' object is not callable` (also confirmed in the read-only bridge review).
- Keep the bridge independent of creative networks. Screenshot paths, analysis CHOP paths, shared control Nulls, and project destinations must be supplied or discovered, not tied to a personal directory or saved network.
- Server-control pulses can disconnect the active MCP channel. Build and verify such controls structurally; activate/restart outside MCP. A port listener is weaker evidence than a responsive health request and a read-only operator query.
- A timeout is an unknown outcome, not a failed transaction. Inspect state before replaying a mutating request. Undo blocks do not roll back files or necessarily every operation.

## Durability and crash recovery

- Preserve a restore point before edits and checkpoint the parent COMP before destructive work. Never combine mass destruction and forced cooking in one script.
- `project.saveBackup()` was unavailable in the observed TD 2025.31310 build. Use a new unused explicit project path or scoped `.tox` checkpoint.
- Explicit `.toe` filenames were auto-incremented, including numeric date suffixes. Verify the actual `project.name` and file existence; do not infer the saved path from the requested string. Avoid overwriting existing paths or assuming a build-specific filename workaround is universal.
- Multiple agents can share the same TD process. Recheck project identity, bridge paths, and expected operators on resume; a plausible filename does not prove isolation.
- Search checkpoint indexes and inspect binary contents before opening an ambiguous project. `toeexpand` from the installed TD build can reveal operator names in an extracted copy. Discover the executable rather than hardcoding a version.
- Keep disk evidence separate from live evidence. A prepared script or saved checkpoint does not prove it ran, restored successfully, or matches the currently open project.

## Stable network construction

- Use named Nulls at branch boundaries and before expressions, exports, composites, lookups, and shared drivers. This makes refactoring possible without breaking consumers of transient upstream nodes.
- Keep component dependencies local where possible. When extracting a component, inspect expressions, exports, bindings, callbacks, composite input lists, and external files for references outside its subtree.
- For generated TOP networks, nearest viewer/input filtering is the retained authoring default unless interpolation is requested. It is not needed for the bridge to function.
- Runtime parameter menus, families, and sequence counts matter more than remembered API names. Sequence count parameters may show zero even with rows present; inspect `par.<sequence>.sequence.numBlocks` and row parameters.
- For native POP displacement, change `P`, not merely an instance scale attribute. Inspect actual `Color`/helper attributes and `P_0..2` ranges via POP-to-CHOP. A named brightness attribute may be all zero while color contains the signal. Use a `float3` offset; inspect the consumer's actual final POP connection.

## UI and input

- Use Basic Widgets from the running installation's palette. `loadTox` may wrap the native widget: load into a temporary holder, locate `widget` iteratively, and copy it out.
- Panel origin is bottom-left. Network `nodeX/nodeY` are different from panel coordinates. Alignment modes can override child positioning. `viewer` is an attribute; panel visibility requires a displayed viewer, window, or ancestor.
- A historical panel distortion came from a browser render displayed in a container with a different aspect ratio, despite reasonable CSS. Compare container/browser/Web Render dimensions, preserve aspect, and adjust pointer mapping for letterboxing. TOP screenshots alone cannot inspect arbitrary panels.
- Prefer menu/enum controls for constrained choices and display measured current values. Preserve calibrated projection/warp outputs while resizing surrounding previews.
- MIDI device names, numeric input indexes, controller IDs, note scopes, and output routing are separate settings. Verify actual incoming channels after mapping; device detection alone does not prove events reach the network. Avoid unintended MIDI echo. Never carry a prior machine's numeric device index forward.

## Visual and hardware evidence

- Source inspection and an error-free network do not establish correct visuals. Inspect actual output, including corners, borders, tile positions, repeated inputs, and uniform failure tiles.
- In multipass image workflows, save labeled input/output images for each stage with seeds and parameters. Dailies must remain viewable without rerunning processing. Keep manifests alongside review images.
- Offline render success is separate from live integration. Network transmission is separate from physical display output. Record which checks were actually performed.
- Human selections remain unresolved until answered. Do not choose a pending rendering tradeoff silently, treat background completion as approval, or invent an approval flow for routine authorized parameter changes.

## Source coverage and maintenance

The review covered existing repository `AGENTS.md`/skill references (UI, POP math, bridge safety, visual verification, approval, recovery), bridge implementation and live component structure, recent controller/projection/review-image transcripts, and earlier panel-repair and MIDI-recovery summaries. Raw transcripts, local paths, particular device settings, render choices, and project deliverables are deliberately excluded from this reusable guide.

Add future lessons here only when evidence supports them. Identify build-specific behavior, the symptom, the check that established the cause, and the smallest reusable fix. Keep project recipes and artifacts outside the bridge's tracked source.
