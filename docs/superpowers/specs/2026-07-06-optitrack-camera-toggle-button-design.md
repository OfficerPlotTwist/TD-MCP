# OptiTrack camera toggle button (TouchDesigner UI)

**Date:** 2026-07-06
**Status:** Approved, building via live MCP bridge.

## Goal

A single styled toggle in a small floating TD panel that **spawns**
`optitrack_spout.exe` (grayscale, all cameras) when ON and **kills** it when OFF.
Killing the process drops the Camera SDK connection, so the cameras revert to
their default state and the Spout senders vanish (the receive-side
`spoutin_optitrack` TOP falls back to its placeholder).

## Decisions (from brainstorming)

- **Mechanism = process spawn/kill**, not OSC. The capture app has OSC control
  (`:7400`, exposure/intensity/framerate/gain) but **no on/off** — on/off is a
  process-lifecycle concern. See [[optitrack-camera-controls-osc]],
  [[optitrack-spout-off-holder]].
- **Launch command = `optitrack_spout.exe` with no args** — uncompressed
  grayscale, max fidelity (bandwidth caps ~3 concurrent cams on the 7× rig; that
  is the user's accepted default). Path is a hardcoded constant.
- **Button host = a new standalone `cont_optitrack` container**, shown as a
  floating window via `openViewer`.
- **OFF = terminate the process; cameras revert.** No `--off` darkening holder.

## Components

New `containerCOMP` **`/project1/cont_optitrack`** (parked nodeX ~1500 /
nodeY ~600, well clear of the cluster), displayed via
`openViewer(unique=True, borders=True)`.

Children:
1. **`btn_cams`** — `buttonToggle` widget lifted from the Basic Widgets palette
   (`buttonToggle.tox`), per CLAUDE.md UI rules. Exposes `Value0` (0/1). Label
   "OPTITRACK CAMS".
2. **`txt_status`** — Text TOP showing `stopped` / `running (pid N)` for numeric
   verification through the bridge (control panels are not screenshottable).
3. **`btn_cams_callbacks`** — Parameter Execute DAT watching
   `btn_cams.par.Value0`; `onValueChange` runs the spawn/kill logic.

## Behavior

- **ON (Value0 → 1):** `subprocess.Popen([EXE], cwd=<exe dir>,
  creationflags=CREATE_NEW_PROCESS_GROUP)`. `cwd` = the exe's folder so it finds
  `CameraLibrary*.dll`. Store the `Popen` in `cont_optitrack.store['proc']`.
  Guard: if a stored proc is still alive (`poll() is None`), do not double-spawn.
  Set `txt_status` → `running (pid …)`.
- **OFF (Value0 → 0):** fetch stored proc, `.terminate()`, clear the store.
  Set `txt_status` → `stopped`.
- **Path constant:**
  `C:\Users\NICKESCHEN\dev\opti-hacking\build\Release\optitrack_spout.exe`,
  launched with **no args**.

## Error handling / edge cases

- **Stale ON after TD restart:** the store holds a live `Popen` that does not
  survive a TD restart. The container's `onStart` resets `btn_cams.par.Value0=0`
  and clears the store so a stale ON never lies.
- **Motive interlock is out of scope** — if Motive owns the cameras the app
  errors out on its own; the button only launches it. (A future status line could
  surface that stderr.)
- **Double-toggle / already-running:** the alive-proc guard prevents spawning a
  second instance; terminate on an already-dead proc is a no-op.

## Verification

- Numeric only (panels aren't screenshottable via the bridge):
  `get_par_value` on `btn_cams.par.Value0`, `txt_status` text, and confirm a
  child process exists after ON / is gone after OFF. Optionally screenshot
  `null_optitrack_cam` (a TOP) to confirm live pixels appear when ON.

## Save discipline

`save_checkpoint` on `/project1` before building; verify numerically; only then
`project.save()` (or `save_checkpoint`, since the project is untitled — see
[[td-untitled-save-freezes-bridge]]).
