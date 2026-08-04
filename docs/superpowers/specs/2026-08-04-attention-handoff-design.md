# Attention Handoff — HITL tutorial-to-network skill

**Date:** 2026-08-04
**Status:** Approved design

## Purpose

Given a YouTube/tutorial video URL, reconstruct the TouchDesigner network the tutorial builds — with a human in the loop doing the visual attention work (finding the frames that matter, boxing the regions that matter) and the agent doing the reading, matching, and rebuilding.

Rationale: full-video automated scraping wastes tokens on dead frames and fails on small UI text. The human is fast and accurate at *finding and framing*; the agent is fast and accurate at *reading crops, reconciling duplicates, and driving the TD MCP bridge*. This skill splits the work along that line.

## Pipeline (5 stages)

```
download (yt-dlp) → capture (human, browser) → extract (agent vision)
                  → approve (human, browser) → rebuild (agent, TD MCP)
```

## Packaging

- Skill: `.claude/skills/attention-handoff/` — `SKILL.md` + `tools/`
  (capture server, static UI, matching library).
- Invocation: `/attention-handoff <youtube-url>`.
- Session dir per run: `tutorials/<video-id>/` in the repo, containing
  `video.mp4` (gitignored), `crops/*.png`, `captures.json`, `graph.json`,
  `approved.json`. Everything except the video is committable, so a session
  is reproducible and auditable.

## Stage 1 — Download

`yt-dlp -f "bv*[height<=1080]+ba/b" -o tutorials/<video-id>/video.mp4 <url>`.
If yt-dlp is missing or fails, stop and hand the user the exact command to run
themselves. No fallback scraping of the streaming page.

## Stage 2 — Capture app (human in the loop)

Python **stdlib-only** `http.server` serving one static page + JSON/PNG POST
endpoints. No npm, no pip deps.

UI:

- `<video>` element with the local file; canvas overlay for box drawing.
- Keys: `←/→` seek ±5 s, `,` / `.` single-frame step, `space` play/pause.
- Capture modes (keys `1`/`2`/`3`), applied to boxes dragged on the paused frame:
  - **1 — param window**: a parameter dialog whose values the tutorial has set.
  - **2 — network grab**: a screengrab showing network/op structure and wiring.
  - **3 — linked pair**: two boxes drawn back-to-back — the selected op node,
    then its param window. Used when string matching would be ambiguous.
    The human may pass on the op box and accept only the param window if
    necessary (pair degrades to a mode-1 capture).
- Each box: client crops the frozen frame via canvas → POSTs PNG +
  `{t, type, bbox, pairId}` → server writes `crops/<id>.png` and appends to
  `captures.json`.
- Sidebar lists captures with thumbnails and delete buttons.
- **Done** button finalizes `captures.json` and signals the agent
  (agent polls a `/status` endpoint).

## Stage 3 — Extract (agent vision)

The agent Reads each crop PNG and produces `graph.json`. No OCR dependency —
Claude vision reads the crops directly.

### Data model

`captures.json` (app-written):

```json
[{ "id": "c012", "t": 214.6, "type": "param|network|pair",
   "bbox": [x, y, w, h], "file": "crops/c012.png", "pairId": "p03" }]
```

`graph.json` (agent-written):

```json
{ "ops":   [{ "id": "noise1", "opType": "noiseTOP", "confidence": 0.9,
              "params": { "period": { "value": 4, "t": 214.6,
                          "history": [{ "value": 1, "t": 88.2 }] } },
              "sources": ["c012", "c031"] }],
  "wires": [{ "from": "noise1", "to": "level1", "toInlet": 0,
              "sources": ["c031"] }],
  "conflicts": [{ "kind": "ambiguous-name | unknown-optype | unreadable | param-changed",
                  "detail": "...", "captureIds": ["..."] }],
  "stats": { "opCount": 0, "wireCount": 0 } }
```

`approved.json` — same shape, written by the approval page. It is the **only**
input the rebuild stage reads.

### Matching & dedupe rules

1. **Primary — string matching.** The param dialog's title strings (op name +
   op-type line) matched against network-node bottom name labels. Normalize to
   lowercase. Node labels are treated as **prefixes** (TD truncates long
   names). A prefix matching multiple captured dialog names becomes an
   `ambiguous-name` conflict — never a silent guess.
2. **Secondary — linked pairs.** A mode-3 pair pins an op-node crop to a param
   window directly and **overrides** any string match for that op.
3. **Dedupe across network grabs.** Same resolved name = same op. Wiring
   observations merge as a union across grabs.
4. **Repeated param captures.** Later video timestamp wins; earlier values are
   kept in `history` and flagged `param-changed` for the approval view.
5. Nothing is dropped silently: every unresolved or low-confidence read lands
   in `conflicts`.

## Stage 4 — Approval (human in the loop)

Same local server, `/approve` page reading `graph.json`:

- Network diagram as **plain SVG** (left→right by wire depth; nodes show
  name + op type; wires as curves). No external JS libraries — works offline.
- Header shows **total op count** and wire count.
- Side table: all ops and params; conflict rows highlighted with explicit
  resolve controls.
- Edits supported: rename op, change op type (datalist of TD op types —
  queried from the live TD build at extract time when the bridge is up,
  otherwise a bundled static list),
  delete op, add/remove wire (click two nodes), edit param values inline.
- **Approve** writes `approved.json`; the polling agent proceeds to rebuild.

## Stage 5 — Rebuild (agent, TD MCP bridge)

1. `save_checkpoint` on `/project1` first — **not** `project.save()`
   (untitled-project save pops a modal that freezes the bridge).
2. Validate every `opType` in `approved.json` against the live TD build
   **before creating anything** — invalid types abort pre-flight, not halfway.
3. Create `/project1/tutorial_<video-id>` container; create ops inside it.
4. Every parameter set to a **non-default value** goes through the
   master-controls bus per repo convention: add a channel to
   `/project1/master_controls` carrying the value (channel named
   `tut_<videoid>_<opname>_<parname>`, truncated sanely if needed) and make
   the op's parameter reference it
   (`op('/project1/master_controls')['<chan>']`) — never hardcode the
   constant on the op. Default-valued params are left untouched. Verify each
   with `get_par_value`.
5. Wire per `approved.json`; lay out newly created ops left→right inside the
   container. User-placed operators are never moved.
6. `get_errors` on the container; report created/failed counts and every
   param TD rejected. Failures are reported, never silently skipped.

## Error handling

- **yt-dlp failure** → stop; give the user the exact command.
- **Unreadable crop** → `unreadable` conflict at approval; never a guessed value.
- **Unknown op type** → pre-flight abort with the list of unknowns (fix at
  approval, re-approve).
- **Bridge down mid-rebuild** → checkpoint from step 1 is the restore point.

## Testing

- Matching/dedupe is a **pure Python module** with unit tests on synthetic
  `captures.json` fixtures: truncated-name prefix cases, ambiguous prefixes,
  pair overrides, param history ordering.
- Capture and approval pages are testable against a local video file with no
  TD running.
- Rebuild supports `--dry-run`: prints the full op/param/wire plan instead of
  executing against the bridge.

## Decisions log

| Decision | Choice |
| --- | --- |
| Capture tool shape | Local web app on downloaded video (not a Chrome extension) |
| Wiring reconstruction | Agent infers from network grabs; human edits at approval |
| Repeated param sets | Latest wins; history kept and flagged |
| Param routing | All non-default values via `/project1/master_controls` channel references (`tut_<videoid>_<opname>_<parname>`) |
| Value reading | Claude vision on crops; no OCR dependency |
| Diagram rendering | Hand-rolled SVG; no external JS libs |
