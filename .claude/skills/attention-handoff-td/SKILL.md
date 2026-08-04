---
name: attention-handoff-td
description: HITL TouchDesigner tutorial scraping — given a tutorial video URL, the human box-selects param windows and network grabs in a local browser app; the agent vision-reads the crops, builds a network graph for browser approval, then rebuilds the network in TD via the MCP bridge with all non-default params routed through /project1/master_controls.
---

# Attention Handoff

Spec: `docs/superpowers/specs/2026-08-04-attention-handoff-design.md`.
Session dir: `tutorials/<video-id>/` (video-id = YouTube ID, or a slug you
pick for non-YouTube URLs; the dir basename becomes the channel-name prefix
and container suffix).

## Stage 1 — Download

```
yt-dlp -f "bv*+ba/b" \
  --merge-output-format mp4 -o "tutorials/<video-id>/video.mp4" <url>
```

(`bv*+ba/b` = highest available resolution, no cap — param text legibility
scales with source res, and the file is deleted after the rebuild anyway.)

If yt-dlp is missing or fails: STOP and give the user this exact command to
run themselves. Do not scrape the streaming page.

Also save the video's metadata for the attribution DAT (Stage 4):

```
yt-dlp -J --skip-download <url> > tutorials/<video-id>/meta.json
```

The fields that matter: `uploader` / `channel`, `channel_url`, `uploader_url`,
`webpage_url`, `title`, and `description` (tutorial authors put their
IG/Patreon/website links in the description).

## Stage 2 — Capture (human)

Start the server in the background and tell the user the capture flow
(modes 1/2/3/4, frame-step keys, Done button). Mode 2 = PARTIAL network
(close-up, op names readable — used for name/type/wire extraction); mode
4 = WHOLE network (zoomed out, names NOT expected to be readable — used
for structure and op/wire-count cross-checks only):

```
python .claude/skills/attention-handoff-td/tools/server.py tutorials/<video-id> --open
```

Poll `GET http://127.0.0.1:8765/status` (curl or urllib via Bash) every
~30 s until `state` is `captured`. Do not proceed before then.

## Stage 3 — Extract (agent)

1. If the TD bridge is up, query valid op types and write
   `tutorials/<video-id>/optypes.json`:
   `execute_script`: `import td; print(sorted(n for n in dir(td) if not n.startswith('_') and n[0].islower() and n.endswith(('TOP','CHOP','SOP','DAT','COMP','MAT','POP'))))`
   If the bridge is down, copy `tools/static/optypes.json` there instead.
2. Read `captures.json`, then Read every crop PNG under `crops/` and build
   `readings.json` — `{captureId: reading}` with these reading kinds:
   - param-window crop → `{"kind":"param","opName":"<title-bar op name>",
     "opType":"<type from dialog>","params":{"<par>":"<value>"},
     "boxes":{"<par>":[x,y,w,h]}}`
     Record ONLY params visibly set to non-default values (bold/edited in
     the dialog). Values as strings exactly as displayed. `boxes` gives the
     crop-pixel bounding box of each param row you read — the `/evidence`
     page renders these as masks so the human can audit every read.
   - network crop → `{"kind":"network","nodes":[{"label":"<bottom title
     text, possibly truncated>","opType":"<type if visually identifiable>"}],
     "wires":[{"from":"<label>","to":"<label>","toInlet":0}]}`
   - pair op-node crop → `{"kind":"opnode","label":"<node label>"}`
   - whole-network crop (type `network-whole`) →
     `{"kind":"network-whole","opCount":<n>,"wireCount":<n>}` — count the
     op nodes and wires you can distinguish; do NOT attempt to read names
     at this zoom. Matching cross-checks these counts against the built
     graph and raises `opcount-mismatch`/`wirecount-mismatch` conflicts at
     approval when the graph is missing ops the tutorial shows.
   - anything illegible → `{"kind":"unreadable"}` — never guess.
3. Run `python .claude/skills/attention-handoff-td/tools/matching.py
   tutorials/<video-id>` → writes `graph.json`.
4. Tell the user to open `http://127.0.0.1:8765/approve` (network diagram +
   op count; the `param evidence` link shows every param crop with masks and
   the extracted values for auditing), then poll `/status` until `approved`.

## Stage 4 — Rebuild (agent, TD MCP bridge)

Run `python .claude/skills/attention-handoff-td/tools/rebuild_plan.py
tutorials/<video-id>` to get the plan. If the user asked for a dry run,
show the plan and stop. Otherwise:

1. `save_checkpoint` on `/project1`. NEVER `project.save()` (untitled
   projects pop a modal that freezes the bridge).
2. Check `plan.blockers` FIRST — if non-empty, STOP and send the user back
   to `/approve` (empty op types or unresolved conflicts must be fixed and
   re-approved). Then validate `plan.opTypes` via `execute_script`
   (`hasattr(td, t) for each`). Unknown types → STOP, report, ask the user
   to fix at `/approve` and re-approve.
3. Create the container: `create_operator` `containerCOMP` named
   `plan.container` in `/project1`. Then create a Text DAT named
   `attribution` INSIDE the container (place it above the op grid, e.g.
   nodeX 0 / nodeY 200) whose text credits the original author, built from
   `meta.json`: author name, video title + URL, channel URL, and every
   social/support link (YouTube/Instagram/Patreon/website/etc.) found in the
   video description — copy the URLs exactly, do not invent any. If
   `meta.json` is missing, build it from the Stage 1 command first.
4. Bus channels: inspect `/project1/master_controls` FIRST and follow its
   existing structure (per AGENTS.md). Constant CHOPs cap at 40 channels —
   if adding `plan.channels` would overflow, create a new Constant CHOP
   inside master_controls (named `tut_<video-id>`) and merge it into the
   bus output the same way existing sources are merged. Set each channel
   to its plan value.
5. Create ops per `plan.creates` inside the container with the given
   `nodeX`/`nodeY` (these are network coords for MY new ops only — never
   move user ops; layout.json pinning does not apply inside the new
   container).
6. `plan.channelParams`: set each `par.expr` to the plan expr and mode to
   EXPRESSION. Verify each with `get_par_value`.
7. `plan.directParams`: set values directly (menu tokens/strings). Verify.
8. Wire per `plan.wires` with `connect_operators` (respect `toInlet`).
9. `get_errors` on the container. Report: ops created/failed, channels
   added, params set/rejected (with reasons), wires made. Failures are
   reported, never silently skipped.
10. Cleanup — only AFTER the user confirms the rebuilt network is complete
    and correct: stop the capture server (kill its process), then delete
    `tutorials/<video-id>/video.mp4` to reclaim disk. Keep everything else
    (meta.json, crops/, captures.json, readings.json, graph.json,
    approved.json) — those are the committable audit trail. Never delete
    the video before the user has confirmed.

## Notes

- Server is 127.0.0.1-only; default port 8765 (`--port` to change).
- All non-numeric param values bypass the bus (CHOP channels are numbers);
  they are listed in `plan.directParams` with a note.
- Session artifacts except the video are committable; `tutorials/.gitignore`
  excludes video files.
