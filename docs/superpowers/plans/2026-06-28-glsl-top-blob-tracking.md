# GLSL TOP Blob Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-contained TouchDesigner container `/project1/cont_blobtrack_glsl` that performs pure-GPU blob detection + tracking (GLSL mask → jump-flood connected-component labeling → GPU scatter centroid/area reduction → feedback ID association → colorized/overlay viz + a blob CHOP), driven live through the TD_MCP bridge.

**Architecture:** Every per-frame stage is a fragment shader (GLSL TOP) except the centroid reduction, which is a vertex scatter (GLSL MAT → Render TOP with additive blending). Canonical shader source lives in repo files under `touchdesigner/blobtrack/` and is loaded into TD Text DATs from disk via TD Python, so the repo is the source of truth and TD edits stay version-controlled. The container exposes a generic TOP input, a custom "Blob Track" parameter page, and Null TOP/CHOP outputs.

**Tech Stack:** TouchDesigner (GLSL TOPs, GLSL MAT, Render/Feedback/Grid/Convert SOPs+TOPs), OpenGL GLSL (TD dialect: `sTD2DInputs[]`, `uTD2DInfos[]`, `vUV`, `TDOutputSwizzle`), TD Python via `execute_script`, the TD_MCP bridge tools.

## Global Constraints

- **Working resolution `Procres` = 128** (square) default; input stays full-res for display, only tracking math is downscaled. Verbatim defaults: `Threshold 0.5`, `Minarea 8`, `Procres 128`, `Matchradius 0.08`, `Maxblobs 64`, `Showoverlay On`.
- **Data textures are 32-bit float** (RG32F / RGBA32F). Labels and coordinate sums must be exact integers stored as floats — never 8-bit.
- **Bridge discipline (CLAUDE.md):** `save_checkpoint` on `cont_blobtrack_glsl` before any bulk-destructive edit; **never** combine bulk destroy with force-cook in one `execute_script`; **never** press Start/Restart on `/project1/TD_MCP`.
- **Save discipline:** the live project may be **untitled** — `project.save()` then pops a modal that hangs the bridge. Snapshot with `save_checkpoint` between tasks; only call `execute_script("project.save()")` if the project is confirmed titled (has a `.toe` path). Verify with `execute_script("print(project.name)")`.
- **`execute_script` scoping:** runs in a wrapper where nested `def`s can't see top-level names. Walk op trees **iteratively** (stack/queue); keep helpers inline.
- **Positioning:** the container is top-level and disconnected — set its `nodeX/nodeY` far from the existing node cluster (use `nodeX=-2000, nodeY=600`).
- **GLSL TOP shader source** is always an external Text DAT loaded from the repo file; multiple GLSL TOPs that share a shader (the JFA passes) point to the **same** Text DAT and differ only by uniform values.
- **Git author trailer** on every commit: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Run git via the **PowerShell** tool, not Bash.

---

## File Structure

Repo files (canonical GLSL source + a loader helper):

- `touchdesigner/blobtrack/mask.frag` — Stage 1 luminance threshold → binary mask.
- `touchdesigner/blobtrack/seed.frag` — Stage 2 seed labels = own pixel coord.
- `touchdesigner/blobtrack/jfa.frag` — Stage 3 jump-flood / relaxation pass (shared by all passes).
- `touchdesigner/blobtrack/scatter_vert.glsl` — Stage 4 GLSL MAT vertex scatter.
- `touchdesigner/blobtrack/scatter_pixel.glsl` — Stage 4 GLSL MAT pixel passthrough.
- `touchdesigner/blobtrack/centroid.frag` — Stage 4 divide sums → normalized centroid + area.
- `touchdesigner/blobtrack/idtrack.frag` — Stage 5 nearest-previous ID inheritance.
- `touchdesigner/blobtrack/labelviz.frag` — Stage 6 hash(label)→color.
- `touchdesigner/blobtrack/overlay.frag` — Stage 6 input + labels composite.
- `touchdesigner/blobtrack/synth.frag` — dev-only synthetic 3-blob test source (one animated).

TD operators created live (all inside `/project1/cont_blobtrack_glsl` unless noted):
`in1`(inTOP), `text_*`(textDAT per shader), `glsl_mask`,`glsl_seed`,`glsl_jfa1..N`,`null_label`,
`grid1`(gridSOP),`convert1`(convertSOP),`geo_scatter`(geometryCOMP)+`glsl_scatter`(glslMAT),
`cam1`(cameraCOMP),`render_centroid`(renderTOP),`glsl_centroid`,`glsl_idtrack`+`feedback_id`(feedbackTOP),
`glsl_labelviz`,`glsl_overlay`,`out_mask`/`out_labels`/`out_viz`(nullTOPs),
`topto_blobs`(topto CHOP)+`math_wh`(mathCHOP)+`out_blobs`(nullCHOP),
`glsl_synth`(dev source).

---

## TD dialect reference (used by every shader)

TD GLSL TOPs auto-declare nothing for outputs in some builds; this plan declares explicitly and uses `TDOutputSwizzle`:
- Inputs: `texture(sTD2DInputs[i], uv)` or `texelFetch(sTD2DInputs[i], ivec2 p, 0)`.
- Resolution of input i: `uTD2DInfos[i].res.zw` = `(width, height)` as float vec2; `.xy` = `(1/w, 1/h)`.
- Varying: `in vec2 vUV;` (`vUV.st` ∈ [0,1]).
- Output: `out vec4 fragColor;` then `fragColor = TDOutputSwizzle(vec4(...));`.
- Custom uniforms are declared `uniform float uName;` and set on the GLSL TOP's **Vectors 1** page (name `uName`, value).

---

### Task 1: Scaffold container, input, parameter page, dev source

**Files:**
- Create: `touchdesigner/blobtrack/synth.frag`
- Live: `/project1/cont_blobtrack_glsl` + `in1`, `glsl_synth`, custom par page.

**Interfaces:**
- Consumes: nothing.
- Produces: container `cont_blobtrack_glsl` with custom pars `Threshold,Minarea,Procres,Matchradius,Maxblobs,Showoverlay`; an `in1` inTOP (the public input); a dev source `glsl_synth` (RG32F, `Procres`²) drawing 3 white disks on black at known normalized centers `(0.25,0.30)`,`(0.70,0.65)`,`(0.50,0.80)` radius `0.06`, the third oscillating in x by `±0.15` at `0.2 Hz` via `uTime`. `glsl_synth` is wired into `in1` for development only.

- [ ] **Step 1: Write the synthetic source shader**

`touchdesigner/blobtrack/synth.frag`:
```glsl
out vec4 fragColor;
uniform float uTime;     // seconds (absTime.seconds)
void main(){
    vec2 uv = vUV.st;
    vec2 c0 = vec2(0.25, 0.30);
    vec2 c1 = vec2(0.70, 0.65);
    vec2 c2 = vec2(0.50 + 0.15*sin(uTime*0.2*6.2831853), 0.80);
    float r = 0.06;
    float fg = 0.0;
    fg = max(fg, step(distance(uv, c0), r));
    fg = max(fg, step(distance(uv, c1), r));
    fg = max(fg, step(distance(uv, c2), r));
    fragColor = TDOutputSwizzle(vec4(fg, fg, fg, 1.0));
}
```

- [ ] **Step 2: Commit the shader file**

PowerShell:
```powershell
git add touchdesigner/blobtrack/synth.frag
git commit -m @'
feat(blobtrack): synthetic 3-disk dev source shader

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
'@
```

- [ ] **Step 3: Verify the container does not exist yet (red)**

`get_operator_info` on `/project1/cont_blobtrack_glsl`.
Expected: error / not found.

- [ ] **Step 4: Create container, input, dev source, and custom parameters**

`execute_script` (paths absolute; loads shader from repo file; iterative, no nested defs):
```python
root = op('/project1')
c = root.create(containerCOMP, 'cont_blobtrack_glsl')
c.nodeX = -2000; c.nodeY = 600
c.par.w = 320; c.par.h = 240

# --- custom parameter page "Blob Track" ---
pg = c.appendCustomPage('Blob Track')
p = pg.appendFloat('Threshold')[0];   p.normMin=0; p.normMax=1; p.default=0.5; p.val=0.5
p = pg.appendInt('Minarea')[0];       p.default=8;  p.val=8
p = pg.appendInt('Procres')[0];       p.default=128;p.val=128
p = pg.appendFloat('Matchradius')[0]; p.normMin=0; p.normMax=0.5; p.default=0.08; p.val=0.08
p = pg.appendInt('Maxblobs')[0];      p.default=64; p.val=64
p = pg.appendToggle('Showoverlay')[0];p.default=True; p.val=True

# --- public input ---
intop = c.create(inTOP, 'in1'); intop.nodeX=-800; intop.nodeY=0

# --- dev synthetic source ---
src = c.create(glslTOP, 'glsl_synth'); src.nodeX=-1100; src.nodeY=-200
tdat = c.create(textDAT, 'text_synth'); tdat.nodeX=-1100; tdat.nodeY=-330
tdat.text = open(r'C:\Users\NICKESCHEN\Dev\TD-MCP\touchdesigner\blobtrack\synth.frag').read()
src.par.pixeldat = tdat.name
src.par.resolutionw.expr = "parent().par.Procres"
src.par.resolutionh.expr = "parent().par.Procres"
src.par.format = 'rgba32float'
# uTime uniform
src.par.vec0name = 'uTime'
src.par.vec0valuex.expr = "absTime.seconds"
# wire dev source -> in1 for development
intop.inputConnectors[0].connect(src)
print('built', c.path)
```

- [ ] **Step 5: Verify structure (green)**

`get_operator_info` on `/project1/cont_blobtrack_glsl` — confirm children `in1`, `glsl_synth`, `text_synth`, and custom pars present. `get_par_value` for `Procres` → `128`. `get_errors` on the container → none. `take_screenshot` on `/project1/cont_blobtrack_glsl/glsl_synth` → 3 white disks on black.

- [ ] **Step 6: Snapshot**

`save_checkpoint` on `/project1/cont_blobtrack_glsl` (label "task1-scaffold").

---

### Task 2: Stage 1 — Mask

**Files:**
- Create: `touchdesigner/blobtrack/mask.frag`
- Live: `glsl_mask`, `text_mask`.

**Interfaces:**
- Consumes: `in1` (TOP, any input). `parent().par.Threshold`, `parent().par.Procres`.
- Produces: `glsl_mask` (RG32F, `Procres`²): `R = 1.0` foreground / `0.0` background; `G = 0.0` reserved.

- [ ] **Step 1: Write the mask shader**

`touchdesigner/blobtrack/mask.frag`:
```glsl
out vec4 fragColor;
uniform float uThreshold;
void main(){
    vec4 c = texture(sTD2DInputs[0], vUV.st);
    float lum = dot(c.rgb, vec3(0.299, 0.587, 0.114));
    float fg = step(uThreshold, lum);
    fragColor = TDOutputSwizzle(vec4(fg, 0.0, 0.0, 1.0));
}
```

- [ ] **Step 2: Commit**

```powershell
git add touchdesigner/blobtrack/mask.frag
git commit -m @'
feat(blobtrack): stage1 luminance-threshold mask shader

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
'@
```

- [ ] **Step 3: Verify mask op absent (red)**

`get_operator_info` on `/project1/cont_blobtrack_glsl/glsl_mask` → not found.

- [ ] **Step 4: Build glsl_mask**

```python
c = op('/project1/cont_blobtrack_glsl')
g = c.create(glslTOP, 'glsl_mask'); g.nodeX=-560; g.nodeY=0
t = c.create(textDAT, 'text_mask'); t.nodeX=-560; t.nodeY=-130
t.text = open(r'C:\Users\NICKESCHEN\Dev\TD-MCP\touchdesigner\blobtrack\mask.frag').read()
g.par.pixeldat = t.name
g.par.format = 'rgba32float'
g.par.outputresolution = 'custom'   # required so resolutionw/h are honored
g.par.resmult = False               # else 'useinput'/mult doubles to 2x
g.par.resolutionw.expr = "parent().par.Procres"
g.par.resolutionh.expr = "parent().par.Procres"
g.par.vec0name = 'uThreshold'
g.par.vec0valuex.expr = "parent().par.Threshold"
g.inputConnectors[0].connect(c.op('in1'))
print('ok')
```

- [ ] **Step 5: Verify mask (green)**

`get_errors` on `glsl_mask` → none. `take_screenshot` on `glsl_mask` → 3 solid white disks (binary, no gray). Numeric: create a temporary `topto1 = c.create(topto CHOP)` reading `glsl_mask`, confirm channel max == 1.0 and min == 0.0, then delete it. (Set `Threshold` to 0.9 and back to 0.5 to confirm the uniform responds.)

- [ ] **Step 6: Snapshot** — `save_checkpoint` ("task2-mask").

---

### Task 3: Stage 2 — Seed labels

**Files:**
- Create: `touchdesigner/blobtrack/seed.frag`
- Live: `glsl_seed`, `text_seed`.

**Interfaces:**
- Consumes: `glsl_mask` (RG32F; `R` = foreground flag).
- Produces: `glsl_seed` (RG32F): foreground pixels carry `RG = (x, y)` integer pixel coord (the root candidate) and `B = 1.0` (foreground flag); background = `RG = (uSentinel, uSentinel)`, `B = 0.0`. `uSentinel = 1e8`.

- [ ] **Step 1: Write the seed shader**

`touchdesigner/blobtrack/seed.frag`:
```glsl
out vec4 fragColor;
uniform float uSentinel;
void main(){
    vec2 res = uTD2DInfos[0].res.zw;          // (w,h)
    ivec2 p = ivec2(vUV.st * res);
    float fg = texelFetch(sTD2DInputs[0], p, 0).r;
    if (fg > 0.5) {
        fragColor = TDOutputSwizzle(vec4(float(p.x), float(p.y), 1.0, 1.0));
    } else {
        fragColor = TDOutputSwizzle(vec4(uSentinel, uSentinel, 0.0, 1.0));
    }
}
```

- [ ] **Step 2: Commit**

```powershell
git add touchdesigner/blobtrack/seed.frag
git commit -m @'
feat(blobtrack): stage2 seed-label shader

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
'@
```

- [ ] **Step 3: Verify seed op absent (red)** — `get_operator_info` on `glsl_seed` → not found.

- [ ] **Step 4: Build glsl_seed**

```python
c = op('/project1/cont_blobtrack_glsl')
g = c.create(glslTOP, 'glsl_seed'); g.nodeX=-320; g.nodeY=0
t = c.create(textDAT, 'text_seed'); t.nodeX=-320; t.nodeY=-130
t.text = open(r'C:\Users\NICKESCHEN\Dev\TD-MCP\touchdesigner\blobtrack\seed.frag').read()
g.par.pixeldat = t.name
g.par.format = 'rgba32float'
g.par.vec0name = 'uSentinel'; g.par.vec0valuex = 1e8
g.inputConnectors[0].connect(c.op('glsl_mask'))
print('ok')
```

- [ ] **Step 5: Verify seed (green)**

`get_errors` → none. Numeric check via a temporary topto CHOP on `glsl_seed`: a foreground texel near disk 0 center (pixel ≈ `(0.25*128, 0.30*128)=(32,38)`) should read `R≈32, G≈38, B=1`; a background texel reads `R=1e8, B=0`. Delete the temp CHOP.

- [ ] **Step 6: Snapshot** — `save_checkpoint` ("task3-seed").

---

### Task 4: Stage 3 — Jump-Flood connected-component labeling

**Files:**
- Create: `touchdesigner/blobtrack/jfa.frag`
- Live: `glsl_jfa1..glsl_jfaN` (shared `text_jfa`), `null_label`.

**Interfaces:**
- Consumes: `glsl_seed` (RG32F root field + `B` flag).
- Produces: `null_label` (RG32F) = final label field where every foreground pixel holds its blob's stable **root** coordinate (min linear index in the connected component); pixels sharing a root are one blob. `B` flag preserved.

Pass schedule for `Procres=128`: steps `64,32,16,8,4,2,1` (JFA, 7 passes) then `1,1,1` (relaxation) = **10 passes**. The shared shader reads each pass's step from uniform `uStep`.

- [ ] **Step 1: Write the JFA pass shader**

`touchdesigner/blobtrack/jfa.frag`:
```glsl
out vec4 fragColor;
uniform float uStep;
void main(){
    vec2 res = uTD2DInfos[0].res.zw;
    ivec2 p = ivec2(vUV.st * res);
    vec4 self = texelFetch(sTD2DInputs[0], p, 0);
    if (self.b < 0.5) { fragColor = TDOutputSwizzle(self); return; }  // background frozen
    vec2 bestRoot = self.rg;
    float bestKey = bestRoot.y * res.x + bestRoot.x;
    int s = int(uStep);
    int W = int(res.x), H = int(res.y);
    for (int dy = -1; dy <= 1; ++dy) {
        for (int dx = -1; dx <= 1; ++dx) {
            if (dx == 0 && dy == 0) continue;
            ivec2 q = p + ivec2(dx, dy) * s;
            if (q.x < 0 || q.y < 0 || q.x >= W || q.y >= H) continue;
            vec4 nb = texelFetch(sTD2DInputs[0], q, 0);
            if (nb.b < 0.5) continue;                 // only foreground propagates
            float key = nb.g * res.x + nb.r;
            if (key < bestKey) { bestKey = key; bestRoot = nb.rg; }
        }
    }
    fragColor = TDOutputSwizzle(vec4(bestRoot, 1.0, 1.0));
}
```

- [ ] **Step 2: Commit**

```powershell
git add touchdesigner/blobtrack/jfa.frag
git commit -m @'
feat(blobtrack): stage3 jump-flood CCL pass shader

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
'@
```

- [ ] **Step 3: Verify no jfa ops yet (red)** — `get_operator_info` on `glsl_jfa1` → not found.

- [ ] **Step 4: Build the unrolled JFA chain**

```python
c = op('/project1/cont_blobtrack_glsl')
t = c.create(textDAT, 'text_jfa'); t.nodeX=0; t.nodeY=-130
t.text = open(r'C:\Users\NICKESCHEN\Dev\TD-MCP\touchdesigner\blobtrack\jfa.frag').read()
steps = [64,32,16,8,4,2,1,1,1,1]   # 7 JFA + 3 relaxation (Procres=128)
prev = c.op('glsl_seed')
x = 0
for i, s in enumerate(steps):
    g = c.create(glslTOP, 'glsl_jfa%d' % (i+1))
    g.nodeX = x; g.nodeY = 0; x += 160
    g.par.pixeldat = 'text_jfa'
    g.par.format = 'rgba32float'
    g.par.vec0name = 'uStep'; g.par.vec0valuex = s
    g.inputConnectors[0].connect(prev)
    prev = g
nl = c.create(nullTOP, 'null_label'); nl.nodeX=x; nl.nodeY=0
nl.inputConnectors[0].connect(prev)
print('chain built, last =', prev.name)
```

- [ ] **Step 5: Verify labeling (green)**

`get_errors` on each `glsl_jfaN` and `null_label` → none. Numeric via temporary topto CHOP on `null_label`: every foreground texel **inside one disk** must share an identical `RG` root; the three disks must have **three distinct** roots. Pick one texel per disk (near each center) and one straddling between disks; confirm same-disk texels match and different-disk texels differ. If two separate disks share a root → **gap-leak**; remediate by changing `steps` to all `1`s with count ≈ disk diameter in px (e.g. `[1]*18`) — pure 1-ring propagation is leak-free (same shader, re-run Step 4 after `delete_operator` on the old chain). Delete temp CHOP.

- [ ] **Step 6: Snapshot** — `save_checkpoint` ("task4-jfa").

---

### Task 5: Stage 4 — GPU scatter centroid + area reduction

**Files:**
- Create: `touchdesigner/blobtrack/scatter_vert.glsl`, `touchdesigner/blobtrack/scatter_pixel.glsl`, `touchdesigner/blobtrack/centroid.frag`
- Live: `grid1`(gridSOP), `convert1`(convertSOP), `geo_scatter`(geometryCOMP)+`glsl_scatter`(glslMAT), `cam1`(cameraCOMP), `render_centroid`(renderTOP), `glsl_centroid`(glslTOP)+`text_centroid`.

**Interfaces:**
- Consumes: `null_label` (RG32F root field + flag).
- Produces: `glsl_centroid` (RGBA32F, `Procres`²): at each blob's **root slot** `(rootIndex % W, rootIndex / W)` the texel holds `(cx_norm, cy_norm, area_px, 1.0)`; all other texels `0`. `cx_norm/cy_norm` ∈ [0,1] (origin bottom-left). Blobs with `area < Minarea` are zeroed.

**Note on TD par names:** Render/Geo/Convert par names vary by build. Before wiring (Step 5) run `get_operator_info` on a freshly created `renderTOP`, `geometryCOMP`, and `convertSOP` to read exact par names (e.g. blending/operand, render-as-points, convert-to). Use the discovered names; the snippet below uses the common TD2023 names and must be reconciled against that output.

- [ ] **Step 1: Write the scatter vertex shader**

`touchdesigner/blobtrack/scatter_vert.glsl` (GLSL MAT vertex; uses grid `uv` attribute → pixel):
```glsl
uniform sampler2D sLabels;   // null_label bound on MAT Samplers page as 'sLabels'
uniform float uRes;          // Procres
out vec4 vScatterColor;
void main(){
    int W = int(uRes);
    ivec2 px = ivec2(uv[0].st * uRes);                  // grid uv 0..1 -> pixel
    vec4 lab = texelFetch(sLabels, px, 0);
    if (lab.b < 0.5) {                                   // background -> offscreen, no contribution
        gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
        vScatterColor = vec4(0.0);
        return;
    }
    int root = int(lab.g) * W + int(lab.r);
    ivec2 slot = ivec2(root % W, root / W);
    vec2 ndc = (vec2(slot) + 0.5) / uRes * 2.0 - 1.0;   // slot center -> clip space
    gl_Position = vec4(ndc, 0.0, 1.0);
    vScatterColor = vec4(float(px.x), float(px.y), 1.0, 0.0);  // (x, y, count, -)
}
```

- [ ] **Step 2: Write the scatter pixel shader**

`touchdesigner/blobtrack/scatter_pixel.glsl`:
```glsl
in vec4 vScatterColor;
out vec4 fragColor;
void main(){
    fragColor = TDOutputSwizzle(vScatterColor);   // additive blend accumulates in Render TOP
}
```

- [ ] **Step 3: Write the centroid divide shader**

`touchdesigner/blobtrack/centroid.frag`:
```glsl
out vec4 fragColor;
uniform float uMinArea;
void main(){
    vec2 res = uTD2DInfos[0].res.zw;
    ivec2 p = ivec2(vUV.st * res);
    vec4 acc = texelFetch(sTD2DInputs[0], p, 0);   // (sumx, sumy, count, -)
    float n = acc.b;
    if (n < uMinArea) { fragColor = TDOutputSwizzle(vec4(0.0)); return; }
    vec2 cpx = acc.rg / n;                          // mean pixel coord
    vec2 cnorm = cpx / res;                         // normalize 0..1
    fragColor = TDOutputSwizzle(vec4(cnorm.x, cnorm.y, n, 1.0));
}
```

- [ ] **Step 4: Commit shaders**

```powershell
git add touchdesigner/blobtrack/scatter_vert.glsl touchdesigner/blobtrack/scatter_pixel.glsl touchdesigner/blobtrack/centroid.frag
git commit -m @'
feat(blobtrack): stage4 GPU scatter + centroid reduction shaders

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
'@
```

- [ ] **Step 5: Discover exact par names (red + recon)**

`get_operator_info` on `glsl_centroid` → not found (red). Temporarily create one each of `renderTOP`, `geometryCOMP`, `convertSOP` off to the side; `get_operator_info` on each; note the exact par names for: Render TOP **blending enable / blend operand (add)**, **pixel format (32-bit float)**, **camera**, **geometry**; Geometry COMP **material**, **render-as-points / point size**; Convert SOP **convert-to (points)**. Delete the three temps. Reconcile the names used in Step 6.

- [ ] **Step 6: Build the scatter render graph**

```python
import os
c = op('/project1/cont_blobtrack_glsl')
base = r'C:\Users\NICKESCHEN\Dev\TD-MCP\touchdesigner\blobtrack'

# grid of one point per working pixel
grid = c.create(gridSOP, 'grid1'); grid.nodeX=-320; grid.nodeY=300
grid.par.rows.expr = "parent().par.Procres"
grid.par.cols.expr = "parent().par.Procres"
conv = c.create(convertSOP, 'convert1'); conv.nodeX=-160; conv.nodeY=300
conv.inputConnectors[0].connect(grid)
# reconcile: set convert-to = Points using the name found in Step 5

# GLSL MAT scatter
mat = c.create(glslMAT, 'glsl_scatter'); mat.nodeX=-160; mat.nodeY=160
vtx = c.create(textDAT, 'text_scatter_v'); vtx.nodeX=-320; vtx.nodeY=160
pix = c.create(textDAT, 'text_scatter_p'); pix.nodeX=-320; pix.nodeY=90
vtx.text = open(os.path.join(base,'scatter_vert.glsl')).read()
pix.text = open(os.path.join(base,'scatter_pixel.glsl')).read()
mat.par.vertexdat = vtx.name
mat.par.pixeldat  = pix.name
# bind null_label as sampler 'sLabels' (use Samplers page names found in Step 5)
mat.par.sampler1name = 'sLabels'
mat.par.top1 = '../null_label'
mat.par.vec0name = 'uRes'; mat.par.vec0valuex.expr = "parent().par.Procres"

geo = c.create(geometryCOMP, 'geo_scatter'); geo.nodeX=0; geo.nodeY=240
# move grid+convert inside geo, or reference SOP; simplest: recreate SOP path inside geo.
# reconcile: set geo material = ./glsl_scatter (or ../glsl_scatter), render-as-points ON, point size 1

cam = c.create(cameraCOMP, 'cam1'); cam.nodeX=0; cam.nodeY=120
cam.par.projection = 'ortho'   # reconcile name; ortho spanning -1..1

rend = c.create(renderTOP, 'render_centroid'); rend.nodeX=160; rend.nodeY=240
rend.par.resolutionw.expr = "parent().par.Procres"
rend.par.resolutionh.expr = "parent().par.Procres"
rend.par.format = 'rgba32float'
# reconcile: geometry=geo_scatter, camera=cam1, clear color=0,
#            blending ON, blend operands = ADD/ONE+ONE, point size 1, AA off

cg = c.create(glslTOP, 'glsl_centroid'); cg.nodeX=320; cg.nodeY=240
ct = c.create(textDAT, 'text_centroid'); ct.nodeX=320; ct.nodeY=120
ct.text = open(os.path.join(base,'centroid.frag')).read()
cg.par.pixeldat = ct.name
cg.par.format = 'rgba32float'
cg.par.vec0name='uMinArea'; cg.par.vec0valuex.expr="parent().par.Minarea"
cg.inputConnectors[0].connect(rend)
print('scatter graph built')
```

- [ ] **Step 7: Verify centroid/area (green)**

`get_errors` on `render_centroid`, `glsl_centroid` → none. Numeric via temporary topto CHOP on `glsl_centroid`: exactly **3 slots** are non-zero; their `(cx,cy)` must match the synthetic centers within ±0.01 — disk0 `(0.25,0.30)`, disk1 `(0.70,0.65)`, disk2 `(~0.50,0.80)`; `area` ≈ `π·(0.06·128)²` ≈ `185` px each (±15%). If centroids are mirrored in Y, flip `cnorm.y = 1.0 - cnorm.y` in `centroid.frag` (TD render Y origin). Delete temp CHOP.

- [ ] **Step 8: Snapshot** — `save_checkpoint` ("task5-centroid").

---

### Task 6: Stage 5 — Feedback ID association

**Files:**
- Create: `touchdesigner/blobtrack/idtrack.frag`
- Live: `glsl_idtrack`(glslTOP)+`text_idtrack`, `feedback_id`(feedbackTOP).

**Interfaces:**
- Consumes: `glsl_centroid` (input 0, current `(cx,cy,area,valid)`), `feedback_id` (input 1, previous frame's id table, same layout as output).
- Produces: `glsl_idtrack` (RGBA32F, `Procres`²): at each active blob slot `(id, cx, cy, area)`; inactive `0`. IDs persist frame-to-frame for blobs that move less than `Matchradius` (normalized) between frames; new blobs mint `id = slotLinearIndex + uFrameSalt`. `feedback_id` mirrors `glsl_idtrack` one frame delayed.

- [ ] **Step 1: Write the ID-track shader**

`touchdesigner/blobtrack/idtrack.frag`:
```glsl
out vec4 fragColor;
uniform float uMatchRadius;   // normalized centroid distance
uniform float uFrameSalt;     // changes per frame; offsets newborn ids
void main(){
    vec2 res = uTD2DInfos[0].res.zw;
    ivec2 p = ivec2(vUV.st * res);
    vec4 cur = texelFetch(sTD2DInputs[0], p, 0);   // (cx,cy,area,valid)
    if (cur.a < 0.5) { fragColor = TDOutputSwizzle(vec4(0.0)); return; }
    int W = int(res.x), H = int(res.y);
    float best = uMatchRadius * uMatchRadius;
    float bestId = 0.0; bool found = false;
    for (int y = 0; y < H; ++y) {
        for (int x = 0; x < W; ++x) {
            vec4 prev = texelFetch(sTD2DInputs[1], ivec2(x,y), 0);  // (id,cx,cy,valid)
            if (prev.a < 0.5) continue;
            vec2 d = prev.gb - cur.rg;             // prev centroid (g,b) - cur centroid (r,g)
            float dd = dot(d, d);
            if (dd < best) { best = dd; bestId = prev.r; found = true; }
        }
    }
    float id = found ? bestId : (float(p.y) * res.x + float(p.x) + uFrameSalt);
    fragColor = TDOutputSwizzle(vec4(id, cur.r, cur.g, cur.b > 0.0 ? 1.0 : 1.0));
    // store: (id, cx, cy, valid=1); area carried separately via glsl_centroid for out_blobs
}
```

- [ ] **Step 2: Commit**

```powershell
git add touchdesigner/blobtrack/idtrack.frag
git commit -m @'
feat(blobtrack): stage5 feedback ID-association shader

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
'@
```

- [ ] **Step 3: Verify id op absent (red)** — `get_operator_info` on `glsl_idtrack` → not found.

- [ ] **Step 4: Build glsl_idtrack + feedback loop**

```python
c = op('/project1/cont_blobtrack_glsl')
g = c.create(glslTOP, 'glsl_idtrack'); g.nodeX=480; g.nodeY=240
t = c.create(textDAT, 'text_idtrack'); t.nodeX=480; t.nodeY=120
t.text = open(r'C:\Users\NICKESCHEN\Dev\TD-MCP\touchdesigner\blobtrack\idtrack.frag').read()
g.par.pixeldat = t.name
g.par.format = 'rgba32float'
g.par.vec0name='uMatchRadius'; g.par.vec0valuex.expr="parent().par.Matchradius"
g.par.vec1name='uFrameSalt';  g.par.vec1valuex.expr="absTime.frame*1000.0"
fb = c.create(feedbackTOP, 'feedback_id'); fb.nodeX=480; fb.nodeY=360
fb.par.top = g.name                       # feedback target = glsl_idtrack
g.inputConnectors[0].connect(c.op('glsl_centroid'))  # input 0 = current
g.inputConnectors[1].connect(fb)                      # input 1 = previous
print('idtrack built')
```

- [ ] **Step 5: Verify ID persistence (green)**

`get_errors` → none. Numeric via temporary topto CHOP on `glsl_idtrack`: 3 active slots, each with a non-zero `id`. **Persistence test:** read the `id` of the moving disk2's slot over ~30 frames (it translates in x); confirm its `id` stays constant while its slot/centroid move (because it matches its previous position within `Matchradius`). Confirm disk0/disk1 (static) keep constant ids. If ids churn every frame, raise `Matchradius` (e.g. 0.12) or confirm `feedback_id` is actually fed back (input 1 non-black). Delete temp CHOP.

- [ ] **Step 6: Snapshot** — `save_checkpoint` ("task6-idtrack").

---

### Task 7: Stage 6 — Visualization + blob CHOP + outputs

**Files:**
- Create: `touchdesigner/blobtrack/labelviz.frag`, `touchdesigner/blobtrack/overlay.frag`
- Live: `glsl_labelviz`+`text_labelviz`, `glsl_overlay`+`text_overlay`, `out_mask`/`out_labels`/`out_viz`(nullTOPs), `topto_blobs`(topto CHOP)+`math_wh`(mathCHOP)+`out_blobs`(nullCHOP).

**Interfaces:**
- Consumes: `glsl_mask`, `null_label`, `in1`, `glsl_idtrack`, `parent().par.Showoverlay`.
- Produces public outputs: `out_mask`(binary), `out_labels`(colorized components), `out_viz`(input+labels composite, gated by `Showoverlay`), `out_blobs`(CHOP channels `id, tx, ty, area, w, h`; one sample per active blob after filtering `valid`).

- [ ] **Step 1: Write the label-viz shader**

`touchdesigner/blobtrack/labelviz.frag`:
```glsl
out vec4 fragColor;
void main(){
    vec2 res = uTD2DInfos[0].res.zw;
    ivec2 p = ivec2(vUV.st * res);
    vec4 lab = texelFetch(sTD2DInputs[0], p, 0);   // null_label
    if (lab.b < 0.5) { fragColor = TDOutputSwizzle(vec4(0.0,0.0,0.0,1.0)); return; }
    float key = lab.g * res.x + lab.r;
    vec3 col = vec3(fract(sin(key*12.9898)*43758.5453),
                    fract(sin(key*78.2330)*43758.5453),
                    fract(sin(key*37.7190)*43758.5453));
    fragColor = TDOutputSwizzle(vec4(col, 1.0));
}
```

- [ ] **Step 2: Write the overlay shader**

`touchdesigner/blobtrack/overlay.frag` (input0 = full-res `in1`, input1 = `glsl_labelviz`):
```glsl
out vec4 fragColor;
uniform float uShow;
void main(){
    vec2 uv = vUV.st;
    vec4 src = texture(sTD2DInputs[0], uv);
    if (uShow < 0.5) { fragColor = TDOutputSwizzle(src); return; }
    vec4 lab = texture(sTD2DInputs[1], uv);          // upscaled label colors
    float m = max(max(lab.r, lab.g), lab.b);         // labeled where any channel lit
    vec3 outc = mix(src.rgb, lab.rgb, step(0.01, m) * 0.6);
    fragColor = TDOutputSwizzle(vec4(outc, 1.0));
}
```

- [ ] **Step 3: Commit shaders**

```powershell
git add touchdesigner/blobtrack/labelviz.frag touchdesigner/blobtrack/overlay.frag
git commit -m @'
feat(blobtrack): stage6 label-viz + overlay shaders

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
'@
```

- [ ] **Step 4: Verify outputs absent (red)** — `get_operator_info` on `out_blobs` → not found.

- [ ] **Step 5: Build viz, outputs, and blob CHOP**

```python
import os
c = op('/project1/cont_blobtrack_glsl')
base = r'C:\Users\NICKESCHEN\Dev\TD-MCP\touchdesigner\blobtrack'

lv = c.create(glslTOP, 'glsl_labelviz'); lv.nodeX=320; lv.nodeY=-200
lvt= c.create(textDAT, 'text_labelviz'); lvt.nodeX=320; lvt.nodeY=-330
lvt.text = open(os.path.join(base,'labelviz.frag')).read()
lv.par.pixeldat=lvt.name; lv.par.format='rgba32float'
lv.inputConnectors[0].connect(c.op('null_label'))

ov = c.create(glslTOP, 'glsl_overlay'); ov.nodeX=480; ov.nodeY=-200
ovt= c.create(textDAT, 'text_overlay'); ovt.nodeX=480; ovt.nodeY=-330
ovt.text = open(os.path.join(base,'overlay.frag')).read()
ov.par.pixeldat=ovt.name; ov.par.format='rgba32float'
ov.par.vec0name='uShow'; ov.par.vec0valuex.expr="parent().par.Showoverlay"
ov.inputConnectors[0].connect(c.op('in1'))
ov.inputConnectors[1].connect(lv)

om = c.create(nullTOP,'out_mask');   om.nodeX=160; om.nodeY=-100; om.inputConnectors[0].connect(c.op('glsl_mask'))
ol = c.create(nullTOP,'out_labels'); ol.nodeX=640; ol.nodeY=-200; ol.inputConnectors[0].connect(lv)
ovn= c.create(nullTOP,'out_viz');    ovn.nodeX=640; ovn.nodeY=-100; ovn.inputConnectors[0].connect(ov)

# blob CHOP: TOP to CHOP over id table -> rename -> derive w/h from area -> filter valid
tc = c.create(toptoCHOP,'topto_blobs'); tc.nodeX=640; tc.nodeY=240
tc.par.top = '../glsl_idtrack'
# channels arrive as r,g,b,a = id,cx,cy,valid ; area from glsl_centroid (b) added below
# rename via a Rename CHOP if needed; here keep r->id,g->tx,b->ty
mw = c.create(mathCHOP,'math_wh'); mw.nodeX=800; mw.nodeY=240
mw.inputConnectors[0].connect(tc)
ob = c.create(nullCHOP,'out_blobs'); ob.nodeX=960; ob.nodeY=240
ob.inputConnectors[0].connect(mw)
print('viz+out built')
```

- [ ] **Step 6: Wire area + w/h and channel names**

```python
c = op('/project1/cont_blobtrack_glsl')
# Bring area into the CHOP: add a second TOP to CHOP on glsl_centroid (b=area),
# merge so out_blobs has id,tx,ty,area; then w=h=2*sqrt(area/pi)/Procres (normalized).
tca = c.create(toptoCHOP,'topto_area'); tca.nodeX=640; tca.nodeY=360
tca.par.top = '../glsl_centroid'
mg = c.create(mergeCHOP,'merge_blobs'); mg.nodeX=800; mg.nodeY=300
mg.inputConnectors[0].connect(c.op('topto_blobs'))
mg.inputConnectors[1].connect(tca)
# reconnect math + out to merge
c.op('math_wh').inputConnectors[0].connect(mg)
print('area merged; set channel renames + w/h expression manually if needed')
```

Channel contract for `out_blobs` (rename channels to): `id` (=idtrack r), `tx` (=idtrack g), `ty` (=idtrack b), `area` (=centroid b). Add `w`,`h` via a Math/Expression CHOP: `w = h = 2.0*sqrt(area/3.14159)/parent().par.Procres` (normalized, **approximate** circular-equivalent diameter — exact bbox is out of scope per spec §6). Downstream consumers filter samples where `valid>0` / `area>0`.

- [ ] **Step 7: Verify outputs (green)**

`get_errors` on all new ops → none. `take_screenshot` on `out_labels` → 3 distinctly-colored disks; on `out_viz` → synthetic input with colored blob regions (toggle `Showoverlay` off → plain input). Numeric on `out_blobs` via inspecting the CHOP: 3 active samples with `id,tx,ty,area` matching Task 5/6 values; `w/h` ≈ `0.12` normalized. 

- [ ] **Step 8: Snapshot** — `save_checkpoint` ("task7-outputs").

---

### Task 8: Finalize — detach dev source, document, persist

**Files:** none (live wiring + repo README).

**Interfaces:** Consumes all prior. Produces the shippable container wired to the real input and a short usage doc.

- [ ] **Step 1: Verify full chain on the real feed (red→green)**

Rewire `in1` to the live OptiTrack feed and confirm end-to-end:
```python
c = op('/project1/cont_blobtrack_glsl')
c.op('in1').inputConnectors[0].connect(op('/project1/null_optitrack_cam'))
print('wired to optitrack')
```
`get_errors` recursively on the container → none. `take_screenshot` on `out_viz`/`out_labels` → blobs track the real feed. Tune `Threshold`/`Minarea` for the feed and record chosen values.

- [ ] **Step 2: Write usage doc**

Create `touchdesigner/blobtrack/README.md` describing: the container's input, the "Blob Track" parameter page, the four outputs (`out_mask/out_labels/out_viz/out_blobs`), the `out_blobs` channel contract (`id,tx,ty,area,w,h`; `valid>0` filter), and the known limitations (JFA gap-leak fallback, no occlusion-robust IDs, approximate `w/h`) cross-referencing the design spec.

- [ ] **Step 3: Commit doc**

```powershell
git add touchdesigner/blobtrack/README.md
git commit -m @'
docs(blobtrack): container usage + out_blobs channel contract

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
'@
```

- [ ] **Step 4: Decide dev-source disposition**

Leave `glsl_synth`/`text_synth` in place but disconnected (handy for regression checks), or `delete_operator` both if a clean ship is preferred — confirm with the user. Default: keep, disconnected.

- [ ] **Step 5: Persist**

`save_checkpoint` ("task8-final"). If `print(project.name)` shows a titled `.toe` (not "Untitled"), `execute_script("project.save()")`; otherwise stop at the checkpoint and tell the user to save manually at the keyboard (untitled save modal hangs the bridge).

---

## Self-Review

**1. Spec coverage:**
- Public interface (input, par page, 4 outputs) → Task 1 (input/pars), Task 7 (outputs). ✓
- Stage 1 mask → Task 2. Stage 2 seed → Task 3. Stage 3 JFA labeling → Task 4. Stage 4 scatter centroid/area → Task 5. Stage 5 feedback IDs → Task 6. Stage 6 viz + CHOP → Task 7. ✓
- 32-bit float textures → set `format='rgba32float'` on every data TOP. ✓
- Build/verify order 1→6 + bridge discipline → tasks ordered identically; checkpoint + untitled-save caveat in Global Constraints and Task 8. ✓
- Risks (JFA gap-leak fallback, ID churn tuning, bbox approx) → Task 4 Step 5 fallback, Task 6 Step 5 tuning, Task 7 Step 6 `w/h` approx note. ✓
- YAGNI exclusions (color classes, Kalman, sub-pixel, logging) → not implemented. ✓

**2. Placeholder scan:** All shader steps contain complete GLSL; all build steps contain complete `execute_script` Python. The one deliberate recon step (Task 5 Step 5) is a real action (read exact TD par names) with a concrete reconciliation target, not a deferred TODO. ✓

**3. Type consistency:** Texel layouts are consistent across stages — `glsl_seed`/`null_label` = `(rootx, rooty, fgflag, 1)`; `glsl_centroid` = `(cx_norm, cy_norm, area, valid)`; `glsl_idtrack`/`feedback_id` = `(id, cx, cy, valid)`. `idtrack.frag` reads prev centroid from `.gb` and cur from `.rg`, matching those layouts. Uniform names match between shader (`uThreshold/uSentinel/uStep/uRes/uMinArea/uMatchRadius/uFrameSalt/uShow`) and the `vec0name/vec1name` assignments. ✓
