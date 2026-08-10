# OptiTrack camera video → TouchDesigner (Spout)

**Date:** 2026-06-28
**Status:** TD receive side built; capture app (C++) not yet implemented.

## Goal

Get the **raw camera imagery** (grayscale pixels) from OptiTrack cameras into a live
TouchDesigner session as a TOP, on a single Windows PC, with lowest practical latency.

## Decisions (and why)

- **Source = Motive camera video → resolved to: raw camera frames via the OptiTrack Camera SDK.**
  The user wants the actual camera pixels, not NatNet tracking data.
- **Transport = Spout, NOT SpoutCam.** TouchDesigner reads Spout natively via the
  Syphon/Spout In TOP (GPU shared DirectX texture, zero-copy, full bit depth, no
  framerate cap). SpoutCam re-exposes a Spout sender as a DirectShow webcam, which would
  add a lossy 8-bit/YUV/latency hop through the Video Device In TOP for no benefit here.
- **Spout over NDI.** Same-PC, so the no-compression zero-copy local path wins. NDI would
  only be preferred if TD ran on a different machine than the cameras.
- **No Motive running (Path A).** Verified against OptiTrack docs: the Camera SDK / Motive
  API connect to the camera system **all-or-nothing at the host level** —
  `CanConnectToDevices` returns true only *"if there are no other instances of Motive
  running on the host PC."* Cameras cannot be partitioned between Motive and an SDK app on
  one PC, and disabling a camera in Motive does **not** release the device. So the capture
  app owns all cameras; Motive is not run.
  Sources: Motive API Function Reference; Camera SDK; Camera Video Types; Devices Pane
  (docs.optitrack.com).

## Architecture

```
OptiTrack cameras ── USB/PoE hub ──► [Capture app, C++]  (owns cameras, no Motive)
                                       CameraLibrary: grayscale frames
                                       SpoutDX:        sender "OptiTrackCam"
                                             │  GPU shared DX texture (same PC)
                                             ▼
                                    TouchDesigner
                                      spoutin_optitrack (Syphon/Spout In TOP)
                                             │   sendername = "OptiTrackCam"
                                             ▼
                                      null_optitrack_cam (Null TOP)  ← stable tap
```

Two units, one interface: the named Spout sender `OptiTrackCam`.

## Unit 1 — Capture app (C++, external to this repo; MCP bridge cannot build it)

- **SDKs:** OptiTrack Camera SDK (`CameraLibrary`) + Spout SDK (`SpoutDX`).
  Camera SDK version must match the installed Motive release line.
- **Init:** `CameraLibrary::CameraManager::X().WaitForInitialization()`; acquire camera handle(s).
- **Mode:** set camera to grayscale/raw video (`Camera::SetVideoType(...Grayscale...)`) so
  frames carry pixels rather than tracked centroids.
- **Frame loop:** `cam->GetFrame()` → `frame->Rasterize(w, h, stride, bpp, buffer)` into an
  8-bit grayscale buffer → `frame->Release()`.
- **Send:** SpoutDX `SendImage(buffer, w, h, ...)` under sender name **`OptiTrackCam`**.
  Mono is simplest packed to RGBA (R=G=B=gray); TD reads luminance from any channel.
- **MVP = one camera.** Multiple cameras later → one named sender each
  (`OptiTrackCam_0`, `OptiTrackCam_1`, …) or a composited grid in the app.

## Unit 2 — TouchDesigner (built 2026-06-28 via the live MCP bridge)

- `/project1/spoutin_optitrack` — Syphon/Spout In TOP (`syphonspoutin`):
  `sendername = "OptiTrackCam"`, `usespoutactivesender = False`.
- `/project1/null_optitrack_cam` — Null TOP, input from the Spout In TOP. Stable downstream tap.
- Parked at nodeX 1025 / 1275, nodeY 250 (clear of the existing cluster).

## Known constraints

- OptiTrack grayscale mode is *"not fully synchronized… lower frame rate"* and raw
  grayscale cannot be exported from Motive — irrelevant here because the Camera SDK app
  reads frames directly and we are showing one video feed, not reconstructing 3D.
- Resolution is camera-model dependent (e.g. Prime-series 1.3/2 MP). The Spout In TOP shows
  a 128×128 placeholder until a sender named `OptiTrackCam` broadcasts, then auto-adopts the
  real resolution.

## Error handling

- Capture app: no-camera-found, SDK init failure, Spout sender create failure → log + retry/backoff.
- TD: if the sender is absent, the Spout In TOP shows the placeholder/black — no error to
  clear; it auto-connects when the sender appears.

## Verification

- TD numerically: once frames flow, the Spout In TOP reports the incoming resolution and the
  Null TOP carries pixels; a TOP is screenshottable via the bridge, so `take_screenshot` on
  `null_optitrack_cam` confirms live pixels.

## Operational notes (this environment)

- The project is **untitled** (`NewProject.1.toe`). `project.save()` with no path pops a modal
  Save dialog that **freezes TD's main thread and hangs the MCP WebServer DAT** (all bridge
  calls time out until the dialog is dismissed). Use `save_checkpoint` on a COMP for restore
  points, or have the user save the project to a real `.toe` path once.
- Restore point for this build: checkpoint `pre_spout_in_build` on `/project1`.
