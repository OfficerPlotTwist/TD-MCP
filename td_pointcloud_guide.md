# TouchDesigner Point Cloud Network — Step-by-Step Build Guide

Derived from: https://www.youtube.com/watch?v=4VuzQMZy0ow  
Sampled at 0.5 fps (1 frame / 2 seconds). Fast interactions may have been missed.

---

## SECTION 1 — Image Processing (TOP Network)

### Step 1 — `moviefilein1` (Movie File In TOP)
- Load your first source image (AI-generated recommended, clear shapes)
- Output Resolution: Custom Resolution → **1280 × 720**
- Use Global Res Multiplier: **On**

### Step 2 — `moviefilein2` (Movie File In TOP)
- Load your second source image
- Same resolution settings as `moviefilein1`

### Step 3 — `switch1` (Switch TOP)
- Connect: `moviefilein1` → input 0, `moviefilein2` → input 1
- Wire `lfo1` output → **Index** parameter

### Step 4 — `lfo1` (LFO CHOP)
- Type: **Sine**
- Play: **On**
- Frequency: **1**
- Offset: **0**
- Amplitude: **1**
- Phase: **0**
- Connect output → `switch1` Index

### Step 5 — `level1` (Level TOP)
- Connect: `switch1` → `level1`
- Tab: **Pre**
  - Clamp Input: **Clamp [0-1]**
  - Invert: **0.67**
  - Black Level: **0.5**
  - Brightness 1: **2**
  - Gamma 1: **2.6**
  - Contrast: **3**

### Step 6 — `constant1` (Constant TOP)
- Color: **black (0, 0, 0)**
- Connect to `comp1` as second input

### Step 7 — `comp1` (Composite TOP) — first comp
- Connect: `noise1` → input 0, `level2` → input 1
- Operation: **Add**
- Input OP list: noise1 (0), level2 (1)

### Step 8 — `noise1` (Noise TOP)
- Connect: `null1` → `noise1`
- Default params (generates paper-like texture overlay)

### Step 9 — `null1` (Null TOP)
- Connect: `level1` → `null1`
- Acts as reference point for the image chain

### Step 10 — `feedback1` (Feedback TOP)
- Connect: `comp1` → `feedback1`
- Target TOP: `comp1` *(drag comp1 into the Target TOP field)*
- Reset: **Off**

### Step 11 — `level2` (Level TOP)
- Connect: `feedback1` → `level2`
- Tab: **Pre**
  - Clamp Input: **Clamp [0-1]** (Automatic)
  - Invert: **0**
  - Black Level: **0.33**
  - Brightness 1: **1**
  - Gamma 1: **1**
  - Contrast: **1**
- *(During setup post gamma is briefly set to 2 to crush blacks, then dialed back)*

### Step 12 — `null2` (Null TOP)
- Connect: `comp1` → `null2`

### Step 13 — `res1` (Resolution TOP)
- Connect: `null2` → `res1`
- Resolution: **600 × 600**
- High Quality Resize: **On**

---

## SECTION 2 — TOP→CHOP Conversion

### Step 14 — `toptol1` (TOP to CHOP)
- Connect: `res1` → `toptol1`
- Tab: **Image**
  - Red: `r`, Green: `g`, Blue: `b`, Alpha: `a`
  - Download Type: **Next frame (Fast)**
- Tab: **Crop**
  - Crop: **Full Image**
- Channel tab: luma → **Red** channel (input luma to r field)
- Output as Single Channel Set: **Off**

### Step 15 — `shuffle1` (Shuffle CHOP)
- Connect: `toptol1` → `shuffle1`
- Method: **Sequence All Channels**
- Use First Sample Only: **Off**

### Step 16 — `math1` (Math CHOP)
- Connect: `shuffle1` → `math1`
- Tab: **Range**
  - From Range: **0** → **1**
  - To Range: **0** → **1**
- Input OP: `shuffle1`

---

## SECTION 3 — Info CHOP (Resolution Values)

### Step 17 — `info1` (Info CHOP)
- Connect: `res1` → `info1` (Operator field: `res1`)
- Info Type: **General**
- Scope: **`res*`** *(type literally `res*` — exposes `resx` and `resy`)*
- Values: **All**

---

## SECTION 4 — SOP Network (Point Grid)

### Step 18 — `grid1` (Grid SOP)
- Primitive Type: **Mesh**
- Connectivity: **Quadrilaterals**
- Orientation: **XY Plane**
- Size X: `op('info1')['resx']` → evaluates to **600** → then `/40` appended → effective size **15**
- Size Y: `op('info1')['resy']` → evaluates to **600** → `/40` → effective size **15**
  *(Drag-drop resx/resy from info1 panel into X/Y size fields, then type `/40` at end of expression)*
- Rows: **20**, Columns: **20**
- Anchor U: **0.5**, Anchor V: **0.5**
- Texture Coordinates: **Row & Columns**
- Compute Normals: **On**

### Step 19 — `noise2` (Noise SOP)
- Connect: `grid1` → `noise2`
- Attribute: **Point Position**
- Type: **Sparse**
- Seed: **1**, Period: **1**, Harmonics: **1**
- Roughness: **0.5**, Exponent: **1**
- Amplitude: **1**, Offset: **0**
- Keep Computed Normals: **On**

### Step 20 — `null13` (Null SOP)
- Connect: `noise2` → `null13`

### Step 21 — `sopto1` (SOP to CHOP)
- Connect: `null13` → `sopto1`
- SOP: **`null13`**
- Position XYZ: **On**
- All other toggles (Color RGB, Normal, Texture UV, etc.): **Off**
- Sample Rate: **60**

---

## SECTION 5 — Merge CHOP (Combine Streams)

### Step 22 — `merge1` (Merge CHOP)
- Connect: `sopto1` → input 0, `shuffle1` → input 1, `math1` → input 2
- Align: **Automatic**
- Duplicate Names: **Make Unique**

### Step 23 — `null4` (Null CHOP)
- Connect: `merge1` → `null4`
- Core Type: **Automatic**
- This is the **instance data source** — referenced by `geo1`

---

## SECTION 6 — 3D Geometry (COMP Network)

### Step 24 — `box1` (Box SOP) — inside `geo1`
- Rotate Order: **Rx Ry Rz**
- Size: **0.4, 0.4, 0.4**
- Center: **0.2, 0.2, 0.2**
- Rotate: **0.2, 0.2, 0.2**
- Scale: **0.04** (later increased to ~0.1 for heavier look)
- Reverse Anchors: **Off**
- Anchor U/V/W: driven by `lfo2`/`lfo4` expressions (animated — see Step 28)
- Texture Coordinates: **Box Inside**
- Compute Normals: **On**

### Step 25 — `geo1` (Geometry COMP)
- Drop `box1` SOP into `geo1`
- Tab: **Xform**
  - Transform Order: **Scale Rotate Translate**
  - Rotate Order: **Rx Ry Rz**
  - Translate: **0, 0, 0**; Scale: **1, 1, 1**
- Tab: **Instance** (Instance 1)
  - Instancing: **On**
  - Instance Count Mode: **Instance OP(s) Length**
  - Default Instance OP: **`null4`**
  - Transform Order: **Scale Rotate Translate**
  - Rotate Order: **Rx Ry Rz**

### Step 26 — `cam1` (Camera COMP)
- Tab: **Xform**
  - Translate Z: **5**
  - All else default
- Tab: **View**
  - Projection: **Perspective**
  - Viewing Angle Method: **Horizontal FOV**
  - FOV Angle: **45**
  - Near: **0.1**, Far: **1000**
  - Window Roll Pivot: **Viewport Origin**

### Step 27 — `light1` (Light COMP)
- Default parameters
- Provides depth shading on the instanced boxes

### Step 28 — `lfo2` / `lfo4` (LFO CHOPs — box anchor animation)
Both identical settings:
- Type: **Sine**
- Play: **On**
- Frequency: **0.34**
- Offset: **−1.64**
- Amplitude: **1.05**
- Phase: **0**
- Connect outputs → `box1` Anchor U (`lfo2`) and Anchor V (`lfo4`)

### Step 29 — `constant2` (Constant MAT)
- Tab: **Constant**
  - Color: **white (1, 1, 1)** — adjust to taste for point color
  - Alpha: **1**
  - Apply Point Color: **On**
- Connect → `geo1` material input

---

## SECTION 7 — Render & Composite

### Step 30 — `render1` (Render TOP)
- Tab: **Render**
  - Camera(s): **`cam1`**
  - Geometry: **`*`** (all)
  - Lights: **`*`** (all)
  - Anti-Alias: **4x**
  - Render Mode: **2D**
  - Transparency: **Sorted Draw with Blending**
- Tab: **Images** (Common)
  - Resolution: **1920 × 1080**
  - Use Global Res Multiplier: **On**
  - Pixel Format: **8-bit fixed (RGBA)**

### Step 31 — `null11` (Null TOP)
- Connect: `render1` → `null11`

### Step 32 — `over1` (Over TOP / Composite)
- Connect: `null11` → input 0, `constant3` → input 1
- Operation: **Over**

### Step 33 — `constant3` (Constant TOP — background)
- Color: **black (0, 0, 0)** or experiment with other colors
- Connected as second input to `over1`

### Step 34 — `bloom` (Bloom BASE — via palette)
- Connect: `over1` → `bloom`
- Blur Size: **23**
- Iterations: **2**
- Threshold: **0.26**
- Intensity: **0.98**
- Gamma: **1**
- Contrast: **1**
- Bloom Level: **0.073**
- Glow Level: **0.4**
- Glow Color: **white, 1**
- Ramp Glow Level: **0**
- Input Level (Mix Out): **1**
- Blur Type: **Hanning**
- Pre-Shrink: **1**, Sample Step: **1**
- Temporal Smooth: **0**
- Pixel Format: **16-bit float (RGB)**

---

## SECTION 8 — Output

### Step 35 — `resout1` (Resolution TOP)
- Connect: `bloom` → `resout1`
- Set output resolution as needed

### Step 36 — `moviefileout1` (Movie File Out TOP)
- Connect: `resout1` → `moviefileout1`
- Type: **Movie**
- Video Codec: **Photo/Motion JPEG**
- Movie Pixel Format: **YUV 4:2:0**
- Movie FPS: **60**
- File: `TDMovieOut.0.mov`
- Record: **Off** (toggle On to capture)

---

## Wiring Summary

```
moviefilein1 ─┐
               ├─► switch1 ──► level1 ──► null1 ──► noise1 ──► comp1 ──► null2 ──► res1
moviefilein2 ─┘                                                   ▲
lfo1 ──────────────────────────────────────────── (index) ──► switch1
feedback1 ──► level2 ──────────────────────────────────────────► comp1 (input 1)
    ▲
    └──────────────────── comp1 (Target TOP)

res1 ──► toptol1 ──► shuffle1 ──► math1 ──┐
                          │                │
                          └────────────────┼──► merge1 ──► null4
                                           │       ▲
grid1 (size: op('info1')['resx']/40) ──► noise2 ──► null13 ──► sopto1 ──► merge1
info1 (Operator: res1, Scope: res*) feeds grid1 size expressions

null4 ──► geo1 (Instancing On, Default Instance OP: null4)
box1 (inside geo1) ◄── constant2 MAT
lfo2 ──► box1 Anchor U
lfo4 ──► box1 Anchor V
cam1, light1 ──► render1

render1 ──► null11 ──► over1 ──► bloom ──► resout1 ──► moviefileout1
constant3 (black) ──► over1 (input 1)
```

---

## Notes
- The Anchor U/V/W values on `box1` animate live (LFO-driven) — the captured values are instantaneous mid-animation
- Multiple image sets (moviefilein3, moviefilein4...) can be added to `switch1` for richer variation
- Adjust `box1` Scale (0.04–0.1) and `level1`/`level2` contrast to control point density and brightness
- Background color via `constant3` changes the overall mood significantly
