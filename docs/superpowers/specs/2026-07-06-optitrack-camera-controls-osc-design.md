# OptiTrack camera controls from TouchDesigner (OSC) — design

**Date:** 2026-07-06
**Status:** Approved (design)
**Repos:** `opti-hacking` (capture app) + TD-MCP live TD project

## Goal

Give in-TD-project control of the OptiTrack camera imaging settings — **exposure/shutter,
IR intensity, frame rate, and imager gain** — while the camera video streams to
TouchDesigner over Spout. The Spout link is video-only (one-way), so this adds a small
TD→app control channel.

## Decisions (locked)

1. **Controls:** full set — exposure, IR intensity, frame rate, imager gain.
2. **Scope:** all streaming cameras together (one set of controls → every camera). Not
   per-camera addressed (deferred).
3. **Channel:** OSC over UDP (TD `OSC Out CHOP` → app UDP receiver).
4. **Ranges:** one-way, no readback. TD sliders use fixed ranges; the **app clamps every
   value to the camera's true SDK min/max** before applying, so nothing invalid reaches
   hardware. Readback deferred.

## Architecture & data flow

```
TD panel  (Exposure, IR Intensity, Frame Rate sliders; Gain dropdown)
   → per-control Range CHOP (normalized 0–1 → real units)
   → one CHOP, channels: exposure / intensity / framerate / gain
   → OSC Out CHOP  (127.0.0.1 : <port>, prefix /cam, individual msgs, send-on-change)
        │  UDP (fire-and-forget, localhost)
        ▼
optitrack_spout.exe
   → non-blocking UDP socket on 127.0.0.1:<port>
   → each stream-loop iteration: drain datagrams, parse OSC, and ON CHANGE
     clamp to the camera's real min/max and apply to ALL streaming cameras
```

One-way, localhost. App not running → TD messages no-op. TD not running → app streams
exactly as today.

## OSC protocol

- Transport: UDP, `127.0.0.1`, default port **7400** (configurable).
- Messages (one arg each, `int32` or `float32` — app accepts either and rounds to int):
  - `/cam/exposure  <n>`
  - `/cam/intensity <n>`
  - `/cam/framerate <n>`
  - `/cam/gain      <n>`   (imager gain LEVEL index, 0-based)
- Parser tolerates a leading `#bundle` wrapper (TD may bundle) and ignores unknown
  addresses / malformed or oversized packets.

## App side (`opti-hacking`)

- **New flag** `--control-port <n>` (default `7400`; `0` disables). Controls are **on by
  default** — running the exe as today just works.
- **New module** `src/osc_control.h` / `src/osc_control.cpp` (keeps `main_camera.cpp`
  focused). Responsibilities:
  - `bool open(uint16_t port)` — `WSAStartup` (if needed), create UDP socket, bind
    `127.0.0.1:port`, set non-blocking. Returns false on failure (caller warns + continues).
  - `bool poll(ControlValues& out)` — drain all pending datagrams, parse OSC, update the
    latest desired value per control; returns true if any changed this poll.
  - Minimal OSC parse: address string (NUL-terminated, 4-byte padded), type tag
    (`,i`/`,f`), one big-endian arg. ~30 lines. No external deps.
  - `void close()`.
- `ControlValues` = `{ std::optional<int> exposure, intensity, framerate, gainLevel; }`
  (only present when received). A separate "current applied" cache avoids re-applying
  unchanged values every frame.
- **Apply (in the existing `while (g_run)` loop, single-threaded, between frames):**
  for each changed control, for each `cs->cam`:
  - exposure: `SetExposure(clamp(v, cam->MinimumExposureValue(), cam->MaximumExposureValue()))`
  - intensity: `SetIntensity(clamp(v, cam->MinimumIntensity(), cam->MaximumIntensity()))`
  - framerate: `SetFrameRate(clamp(v, cam->MinimumFrameRateValue(), cam->MaximumFrameRateValue()))`
  - gain: `SetImagerGain((Camera::eImagerGain)clamp(level, 0, cam->ImagerGainLevels()-1))`
- Single-threaded, non-blocking recv → no locks. Socket bind failure = warn + stream on.

## TD side (built programmatically; Basic Widgets per project convention)

- New container `/project1/cont_cam_controls`, **displayed** (`comp.viewer=True` and/or a
  floating window / nested in a displayed ancestor — panels only render when displayed).
- Controls:
  - **Exposure, IR Intensity, Frame Rate** — `sliderHorz.tox` Basic Widgets, labeled.
  - **Gain** — `dropDownMenu.tox` (enumerated gain levels, not continuous).
- Mapping: each slider's normalized `Value0` (0–1) → real units via a Range/Math CHOP;
  merge into one CHOP with channels `exposure/intensity/framerate/gain`.
- `OSC Out CHOP`: Network Address `127.0.0.1`, Port `7400`, address prefix `/cam`,
  **individual messages** (bundle off), send-on-change.
- Fixed initial ranges (editable; app clamp keeps them safe):

  | Control    | TD range   | Notes |
  |------------|-----------|-------|
  | exposure   | 1–500     | camera clamps to real max (frame-rate dependent) |
  | intensity  | 0–15      | IR LED level |
  | framerate  | 30–240    | Prime 13W range |
  | gain       | 0–(levels−1) | discrete dropdown; count from camera |

## Error handling

- App: bind failure → warn, continue streaming (controls disabled). Non-blocking recv
  `WSAEWOULDBLOCK` ignored. Malformed/oversized/unknown-address OSC ignored. Clamp
  guarantees hardware safety.
- TD: `OSC Out CHOP` to a dead port is harmless (UDP fire-and-forget).

## Testing / verification

- **App unit check:** send OSC to `127.0.0.1:7400` from a script and log `cam->Exposure()`
  before/after to prove the value landed and clamped.
- **End-to-end:** drag Exposure → `/project1/spoutin_optitrack` image brightens/darkens;
  drag IR Intensity → marker brightness changes; confirm stream never drops and the app
  does not crash; changing frame rate live is accepted.

## Files touched

- `opti-hacking/src/main_camera.cpp` — `--control-port`, wire the receiver into the loop.
- `opti-hacking/src/osc_control.h`, `osc_control.cpp` — new receiver + OSC parser.
- `opti-hacking/CMakeLists.txt` — add the new source to the `optitrack_spout` target.
- TD live project — new `/project1/cont_cam_controls` container + OSC Out CHOP, displayed.

## Out of scope (YAGNI / deferred)

- Value readback / auto-ranging sliders (add later via a return OSC path).
- Per-camera addressing and camera selector UI.
- Other camera settings (LED status, continuous IR, threshold, etc.).
- Persistence of slider positions across TD restarts.
