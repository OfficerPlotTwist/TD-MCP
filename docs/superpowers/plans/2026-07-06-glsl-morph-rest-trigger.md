# GLSL Morph-Heuristic Rest Trigger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `/project1/cont_rest_trigger` container in the live TouchDesigner session that fires a `trigger7`-shaped CHOP pulse when the IR sticker's silhouette stops morphing (hand comes to rest).

**Architecture:** A GLSL TOP frame-differences the blob mask (`out_mask` vs. a 1-frame Feedback delay) to produce a per-pixel silhouette-change texture; a Script CHOP reduces it (numpyArray mean) to a scalar `morph_energy`; a Trail→Analyze(max) chain builds a running max; a Trigger CHOP cloned from `/project1/trigger7` (adaptive `.85×max`, `triggeron=decrease`) fires on the change→idle transition; a `blob_idx0.area>0` gate suppresses "sticker left frame" false fires.

**Tech Stack:** TouchDesigner (GLSL TOP, Feedback TOP, Script CHOP w/ numpy, Trail/Analyze/Trigger/Math CHOPs) driven through the `touchdesigner` MCP bridge (`execute_script`, `get_operator_info`, `get_par_value`, `get_errors`, `save_checkpoint`). Shader source versioned in the repo.

## Global Constraints

- Target session is **live and unsaved**; mutations hit the running project immediately. Persist via `save_checkpoint` on the parent COMP — **do NOT call `project.save()`** (untitled-save pops a modal that hangs the bridge; persisting the `.toe` to disk is the user's job at the keyboard).
- **Never** press any server-control button on `/project1/TD_MCP`.
- All mask-domain TOPs use **Nearest Pixel** filtering (`inputfiltertype=nearest`, `filtertype=nearest`). The Script CHOP reduction is the one deliberate *averaging* step.
- Do **not** modify existing ops: `/project1/trigger7`, `select2`, `blob_idx0`, `max_biggest_blob`, `trail2`, or anything in `/project1/cont_blobtrack_glsl`. This build only *reads* them.
- `execute_script` runs in a wrapper where nested `def`s can't see top-level names; walk trees iteratively and keep helpers inline (except Script CHOP callbacks, which run in their own DAT scope and may use `def onCook`).
- New top-level COMP: set `nodeX/nodeY` far from the existing cluster so the patch stays readable.
- Trigger CHOP params must match `/project1/trigger7` verbatim (see the table in Task 5, captured 2026-07-06).
- Reference: `docs/superpowers/specs/2026-07-06-glsl-morph-rest-trigger-design.md`.

---

## File Structure

- `touchdesigner/resttrigger/morph.frag` — **Create.** GLSL fragment shader for the silhouette frame-difference. Source of truth for the `text_morph` DAT.
- `touchdesigner/resttrigger/README.md` — **Create (Task 8).** Container documentation, mirroring `touchdesigner/blobtrack/README.md` style.
- Live TD (not on disk): `/project1/cont_rest_trigger` and its children, built via `execute_script`.

Live child ops (final target state):

| Op | Type | Role |
|----|------|------|
| `in1` | inTOP | Receives `out_mask` (TOP input 0) |
| `in2` | inCHOP | Receives `blob_idx0` (CHOP input 0) |
| `top_maskclean` | blurTOP | Optional edge pre-filter (size = `Edgeclean`, 0=off) |
| `feedback_mask` | feedbackTOP | 1-frame delay of `top_maskclean` |
| `text_morph` | textDAT | Holds `morph.frag` |
| `glsl_morph` | glslTOP | `|mask_t − mask_{t-1}|` → `out_morph_viz` |
| `script_morph_energy` | scriptCHOP | numpyArray mean of `glsl_morph` → `morph_energy` |
| `trail_morph` | trailCHOP | 3 s window of `morph_energy` |
| `max_morph` | analyzeCHOP | running maximum |
| `trigger_rest` | triggerCHOP | `trigger7` clone; fires on decrease |
| `select_area` | selectCHOP | picks `area` from `in2`, renames to `chan1` |
| `gate_present` | expressionCHOP | `1` when area>0 (or gate off), else `0` |
| `math_gate` | mathCHOP | `trigger_rest × gate_present` |
| `out_rest_trigger` | outCHOP | the deliverable pulse |
| `out_morph_energy` | outCHOP | scalar energy (tuning) |
| `out_morph_viz` | outTOP | diff texture (debug) |

---

## Task 1: Container skeleton + external wiring

**Files:**
- Live: create `/project1/cont_rest_trigger` with `in1`(inTOP), `in2`(inCHOP), and the three out-ops; wire external sources.

**Interfaces:**
- Consumes: `/project1/cont_blobtrack_glsl/out_mask` (TOP), `/project1/blob_idx0` (CHOP).
- Produces: container `cont_rest_trigger` with input connector 0 = TOP (mask), input connector 1 = CHOP (blob); child In-ops `in1`/`in2` and Out-ops `out_rest_trigger`/`out_morph_energy`/`out_morph_viz` (created empty here, wired in later tasks).

- [ ] **Step 1: Checkpoint the parent (restore point)**

Call `save_checkpoint` with `path="/project1"` (label e.g. `pre-rest-trigger`). Expected: checkpoint id returned, no error.

- [ ] **Step 2: Verify the target doesn't exist yet**

`execute_script`:
```python
print('exists:', op('/project1/cont_rest_trigger'))
print('mask src:', op('/project1/cont_blobtrack_glsl/out_mask'))
print('blob src:', op('/project1/blob_idx0'))
```
Expected: `exists: None`, and both sources print a valid op path (not None).

- [ ] **Step 3: Create the container + In/Out ops**

`execute_script` (undo_label `rest: skeleton`):
```python
p = op('/project1')
cont = p.create(containerCOMP, 'cont_rest_trigger')
cont.nodeX, cont.nodeY = 1400, -600   # far from the cluster
inT = cont.create(inTOP,  'in1');  inT.par.index = 0
inC = cont.create(inCHOP, 'in2');  inC.par.index = 0
oT  = cont.create(outTOP,  'out_morph_viz')
oE  = cont.create(outCHOP, 'out_morph_energy')
oR  = cont.create(outCHOP, 'out_rest_trigger')
# tidy layout
inT.nodeX, inT.nodeY = -800, 200
inC.nodeX, inC.nodeY = -800, -200
oR.nodeX,  oR.nodeY  = 800, 0
oE.nodeX,  oE.nodeY  = 800, -150
oT.nodeX,  oT.nodeY  = 800, 150
print('children:', sorted(c.name for c in cont.children))
```
Expected: `children: ['in1', 'in2', 'out_morph_energy', 'out_morph_viz', 'out_rest_trigger']`.

- [ ] **Step 4: Wire external sources into the container**

`execute_script` (undo_label `rest: extern wire`):
```python
cont = op('/project1/cont_rest_trigger')
mask_src = op('/project1/cont_blobtrack_glsl/out_mask')
blob_src = op('/project1/blob_idx0')
# Container input connectors list TOP inputs before CHOP inputs.
mask_src.outputConnectors[0].connect(cont.inputConnectors[0])   # TOP -> in1
blob_src.outputConnectors[0].connect(cont.inputConnectors[1])   # CHOP -> in2
for i, c in enumerate(cont.inputConnectors):
    print(i, c.name, '<-', [cn.owner.path for cn in c.connections])
```
Expected: connector 0 shows `<- ['/project1/cont_blobtrack_glsl/out_mask']`, connector 1 shows `<- ['/project1/blob_idx0']`. If they landed swapped, disconnect and retry with indices swapped.

- [ ] **Step 5: Verify inputs reach the In-ops and cook clean**

`execute_script`:
```python
cont = op('/project1/cont_rest_trigger')
print('in1 res:', op('/project1/cont_rest_trigger/in1').width, op('/project1/cont_rest_trigger/in1').height)
print('in2 chans:', [c.name for c in op('/project1/cont_rest_trigger/in2').chans()])
```
Expected: `in1 res: 128 128`; `in2 chans: ['id', 'tx', 'ty', 'area', 'w', 'h']`. Then call `get_errors` — expected: no errors on `cont_rest_trigger` subtree.

- [ ] **Step 6: Checkpoint**

Call `save_checkpoint` `path="/project1"` (label `rest-t1-skeleton`).

---

## Task 2: Morph diff (shader + Feedback + pre-filter)

**Files:**
- Create: `touchdesigner/resttrigger/morph.frag`
- Live: `top_maskclean`, `feedback_mask`, `text_morph`, `glsl_morph`; wire `glsl_morph → out_morph_viz`.

**Interfaces:**
- Consumes: `in1` (128² binary mask TOP).
- Produces: `glsl_morph` (128² RGBA32F, R = per-pixel silhouette change this frame), surfaced on `out_morph_viz`.

- [ ] **Step 1: Write the shader source (repo)**

Create `touchdesigner/resttrigger/morph.frag`:
```glsl
// morph.frag — silhouette frame-difference for the rest-trigger morph heuristic.
// sTD2DInputs[0] = current mask (R=1 foreground), sTD2DInputs[1] = previous-frame mask.
// Output R = 1.0 where the silhouette flipped this frame, else 0.0.
out vec4 fragColor;

void main()
{
    float a = texture(sTD2DInputs[0], vUV.st).r;   // mask_t
    float b = texture(sTD2DInputs[1], vUV.st).r;   // mask_{t-1}
    float d = abs(a - b);
    fragColor = TDOutputSwizzle(vec4(d, d, d, 1.0));
}
```

- [ ] **Step 2: Verify diff ops don't exist yet**

`execute_script`:
```python
print([op('/project1/cont_rest_trigger/'+n) for n in ('top_maskclean','feedback_mask','text_morph','glsl_morph')])
```
Expected: `[None, None, None, None]`.

- [ ] **Step 3: Build the diff chain**

Read `touchdesigner/resttrigger/morph.frag` and paste its contents into the `FRAG` string below. `execute_script` (undo_label `rest: morph diff`):
```python
cont = op('/project1/cont_rest_trigger')
FRAG = r"""<<PASTE morph.frag CONTENTS HERE>>"""

clean = cont.create(blurTOP, 'top_maskclean')
clean.par.size = 0                       # 0 = passthrough; bound to Edgeclean in Task 7
clean.par.filtertype = 'nearest'
clean.par.inputfiltertype = 'nearest'
op('/project1/cont_rest_trigger/in1').outputConnectors[0].connect(clean.inputConnectors[0])

fb = cont.create(feedbackTOP, 'feedback_mask')       # 1-frame delay of wired input
clean.outputConnectors[0].connect(fb.inputConnectors[0])

txt = cont.create(textDAT, 'text_morph')
txt.text = FRAG

g = cont.create(glslTOP, 'glsl_morph')
g.par.pixeldat = 'text_morph'
g.par.filtertype = 'nearest'
g.par.inputfiltertype = 'nearest'
clean.outputConnectors[0].connect(g.inputConnectors[0])   # in0 = mask_t
fb.outputConnectors[0].connect(g.inputConnectors[1])      # in1 = mask_{t-1}

g.outputConnectors[0].connect(op('/project1/cont_rest_trigger/out_morph_viz').inputConnectors[0])

# layout
clean.nodeX, clean.nodeY = -500, 200
fb.nodeX,    fb.nodeY    = -300, 350
txt.nodeX,   txt.nodeY   = -300, 500
g.nodeX,     g.nodeY     = -100, 200
print('built:', sorted(c.name for c in cont.children))
```
Expected: children now include `glsl_morph`, `feedback_mask`, `text_morph`, `top_maskclean`.

- [ ] **Step 4: Verify the shader compiles and the diff responds**

`execute_script`:
```python
import numpy as np
g = op('/project1/cont_rest_trigger/glsl_morph')
print('glsl errors:', g.errors())
a = g.numpyArray()
print('diff res:', a.shape, 'diff sum R:', float(a[:,:,0].sum()))
```
Then `get_errors` on the subtree. Expected: `glsl errors:` empty string; `diff res: (128, 128, 4)`; no compile errors. (Sum may be 0 when the mask is static/empty — that's correct; verify responsiveness live by disturbing the feed, or in Task 3's numeric check.)

- [ ] **Step 5: Commit the shader (repo)**

```bash
git -C "C:/Users/NICKESCHEN/dev/TD-MCP" add touchdesigner/resttrigger/morph.frag
git -C "C:/Users/NICKESCHEN/dev/TD-MCP" commit -m "feat(rest-trigger): silhouette frame-diff GLSL shader"
```

- [ ] **Step 6: Checkpoint the live state**

`save_checkpoint` `path="/project1"` (label `rest-t2-morph`).

---

## Task 3: Reduce to scalar `morph_energy`

**Files:**
- Live: `script_morph_energy` (scriptCHOP); wire to `out_morph_energy`.

**Interfaces:**
- Consumes: `glsl_morph` (128² RGBA32F).
- Produces: `script_morph_energy` CHOP with one channel `morph_energy` (1 sample) = mean of the diff's R channel ∈ [0,1]. Surfaced on `out_morph_energy`.

- [ ] **Step 1: Verify it doesn't exist yet**

`execute_script`: `print(op('/project1/cont_rest_trigger/script_morph_energy'))` → Expected `None`.

- [ ] **Step 2: Build the Script CHOP and its callback**

`execute_script` (undo_label `rest: energy reduce`):
```python
cont = op('/project1/cont_rest_trigger')
s = cont.create(scriptCHOP, 'script_morph_energy')
s.nodeX, s.nodeY = 150, 200
cb = s.par.callbacks.eval()   # the auto-created callbacks DAT
dat = op(cb) if cb else s.op('callbacks') if hasattr(s,'op') else None
# scriptCHOP creates a docked 'callbacks' DAT; find it robustly:
if dat is None:
    for ch in cont.children:
        if ch.name.startswith('script_morph_energy') and ch.type == 'DAT':
            dat = ch; break
CALLBACK = '''
import numpy as np

def onCook(scriptOp):
\tscriptOp.clear()
\tsrc = op('glsl_morph')
\te = 0.0
\tif src is not None:
\t\ttry:
\t\t\tarr = src.numpyArray()
\t\t\te = float(arr[:, :, 0].mean())
\t\texcept Exception:
\t\t\te = 0.0
\tc = scriptOp.appendChan('morph_energy')
\tc.vals = [e]
\treturn
'''
dat.text = CALLBACK
s.cook(force=True)
s.outputConnectors[0].connect(op('/project1/cont_rest_trigger/out_morph_energy').inputConnectors[0])
print('chans:', [c.name for c in s.chans()], 'val:', [round(c.eval(),6) for c in s.chans()])
```
Expected: `chans: ['morph_energy'] val: [<float>]` (0.0 when the mask is static/empty — correct).

- [ ] **Step 3: Verify responsiveness (numeric)**

`execute_script` — force a synthetic change by momentarily comparing two known-different arrays is not possible without the feed, so verify the wiring and that the value is finite and non-negative:
```python
s = op('/project1/cont_rest_trigger/script_morph_energy')
s.cook(force=True)
v = s['morph_energy'].eval()
print('morph_energy =', v, 'finite&>=0:', (v == v) and v >= 0.0)
print('out chan:', op('/project1/cont_rest_trigger/out_morph_energy')['morph_energy'].eval())
```
Expected: `finite&>=0: True`; out chan matches. (When the live IR feed is running, `morph_energy` should rise above 0 while the silhouette moves — this is confirmed in Task 8's live validation.)

- [ ] **Step 4: Checkpoint**

`save_checkpoint` `path="/project1"` (label `rest-t3-energy`).

---

## Task 4: Running-max chain (Trail → Analyze)

**Files:**
- Live: `trail_morph` (trailCHOP), `max_morph` (analyzeCHOP).

**Interfaces:**
- Consumes: `script_morph_energy` (`morph_energy`).
- Produces: `max_morph` CHOP, channel `morph_energy` = running maximum of energy over a 3 s window. Read by Task 5 as `op('max_morph')[0]`.

- [ ] **Step 1: Verify absent**

`execute_script`: `print(op('/project1/cont_rest_trigger/trail_morph'), op('/project1/cont_rest_trigger/max_morph'))` → Expected `None None`.

- [ ] **Step 2: Build the chain (mirror trail2 / max_biggest_blob)**

`execute_script` (undo_label `rest: running max`):
```python
cont = op('/project1/cont_rest_trigger')
tr = cont.create(trailCHOP, 'trail_morph')
tr.par.wlength = 3.0
tr.par.wlengthunit = 'seconds'
tr.par.capture = 'timeslice'
op('/project1/cont_rest_trigger/script_morph_energy').outputConnectors[0].connect(tr.inputConnectors[0])

mx = cont.create(analyzeCHOP, 'max_morph')
mx.par.function = 'maximum'
tr.outputConnectors[0].connect(mx.inputConnectors[0])

tr.nodeX, tr.nodeY = 350, 200
mx.nodeX, mx.nodeY = 500, 200
mx.cook(force=True)
print('max chans:', [c.name for c in mx.chans()], 'val:', [round(c.eval(),6) for c in mx.chans()])
print('index0:', op('/project1/cont_rest_trigger/max_morph')[0].eval())
```
Expected: `max chans: ['morph_energy']`; `index0:` a finite float ≥ current energy.

- [ ] **Step 3: Verify running-max semantics**

`execute_script`:
```python
mx = op('/project1/cont_rest_trigger/max_morph')
en = op('/project1/cont_rest_trigger/script_morph_energy')['morph_energy'].eval()
print('max >= current energy:', mx[0].eval() >= en - 1e-9)
```
Expected: `True`.

- [ ] **Step 4: Checkpoint**

`save_checkpoint` `path="/project1"` (label `rest-t4-max`).

---

## Task 5: Trigger CHOP (clone `trigger7`)

**Files:**
- Live: `trigger_rest` (triggerCHOP), fed by `script_morph_energy`.

**Interfaces:**
- Consumes: `script_morph_energy` (`morph_energy`), `max_morph`.
- Produces: `trigger_rest` CHOP, channel `chan1` = shaped pulse (peak 1) emitted when energy decreases through `.85×max_morph`.

**`trigger7` parameter reference (captured 2026-07-06 from `/project1/trigger7`):**

| Param | Value | Param | Value |
|-------|-------|-------|-------|
| `threshold` | `True` | `triggeron` | `'decrease'` |
| `threshup` | `.85 * op('max_morph')[0]` (EXPRESSION) | `multitrigger` | `'ignore'` |
| `threshdown` | `0.0` | `clamppeak` | `True` |
| `retrigger` | `0.0` / `retriggerunit='seconds'` | `complete` | `True` |
| `mintrigger` | `0.0` / `mintriggerunit='seconds'` | `updateonce` | `False` |
| `delay` | `0.0` / `delayunit='samples'` | `remainder` | `'extend'` |
| `attack` | `0.0` / `attackunit='samples'` | `ashape` | `'halfcos'` |
| `peak` | `1.0` | `peaklen` | `6.0` / `peaklenunit='samples'` |
| `decay` | `4.0` / `decayunit='samples'` | `dshape` | `'halfcos'` |
| `sustain` | `0.0` | `minsustain` | `0.0` / `minsustainunit='seconds'` |
| `release` | `4.0` / `releaseunit='frames'` | `rshape` | `'halfcos'` |
| `channame` | `'chan1'` | `timeslice` | `True` |
| `rate` | `me.time.rate` (EXPRESSION) | `scope` | `'*'` |
| `srselect` | `'max'` | `specifyrate` | `False` |

- [ ] **Step 1: Verify absent**

`execute_script`: `print(op('/project1/cont_rest_trigger/trigger_rest'))` → Expected `None`.

- [ ] **Step 2: Build the Trigger CHOP with matched params**

`execute_script` (undo_label `rest: trigger`):
```python
cont = op('/project1/cont_rest_trigger')
t = cont.create(triggerCHOP, 'trigger_rest')
t.nodeX, t.nodeY = 500, 50
op('/project1/cont_rest_trigger/script_morph_energy').outputConnectors[0].connect(t.inputConnectors[0])

t.par.threshold = True
t.par.threshup.expr = ".85 * op('max_morph')[0]"
t.par.threshup.mode = ParMode.EXPRESSION
t.par.threshdown = 0.0
t.par.retrigger = 0.0;  t.par.retriggerunit = 'seconds'
t.par.mintrigger = 0.0; t.par.mintriggerunit = 'seconds'
t.par.triggeron = 'decrease'
t.par.multitrigger = 'ignore'
t.par.clamppeak = True
t.par.updateonce = False
t.par.complete = True
t.par.remainder = 'extend'
t.par.delay = 0.0;   t.par.delayunit = 'samples'
t.par.attack = 0.0;  t.par.attackunit = 'samples'; t.par.ashape = 'halfcos'
t.par.peak = 1.0
t.par.peaklen = 6.0; t.par.peaklenunit = 'samples'
t.par.decay = 4.0;   t.par.decayunit = 'samples';  t.par.dshape = 'halfcos'
t.par.sustain = 0.0
t.par.minsustain = 0.0; t.par.minsustainunit = 'seconds'
t.par.release = 4.0; t.par.releaseunit = 'frames'; t.par.rshape = 'halfcos'
t.par.channame = 'chan1'
t.par.specifyrate = False
t.par.rate.expr = 'me.time.rate'; t.par.rate.mode = ParMode.EXPRESSION
t.par.timeslice = True
t.par.scope = '*'
t.par.srselect = 'max'
print('threshup evals:', t.par.threshup.eval(), 'triggeron:', t.par.triggeron.eval())
```
Expected: `threshup evals:` a finite float (`.85 × max_morph`); `triggeron: decrease`.

- [ ] **Step 3: Verify params match `trigger7`**

`execute_script`:
```python
a = op('/project1/trigger7'); b = op('/project1/cont_rest_trigger/trigger_rest')
keys = ['threshold','threshdown','retrigger','retriggerunit','mintrigger','mintriggerunit',
        'triggeron','multitrigger','clamppeak','updateonce','complete','remainder',
        'delay','delayunit','attack','attackunit','ashape','peak','peaklen','peaklenunit',
        'decay','decayunit','dshape','sustain','minsustain','minsustainunit',
        'release','releaseunit','rshape','channame','specifyrate','timeslice','scope','srselect']
diffs = [(k, getattr(a.par,k).eval(), getattr(b.par,k).eval())
         for k in keys if getattr(a.par,k).eval() != getattr(b.par,k).eval()]
print('param diffs vs trigger7:', diffs)
print('rate expr match:', a.par.rate.expr == b.par.rate.expr)
```
Expected: `param diffs vs trigger7: []` (only `threshup`'s referenced op differs by design, and it is intentionally excluded from this list); `rate expr match: True`.

- [ ] **Step 4: Checkpoint**

`save_checkpoint` `path="/project1"` (label `rest-t5-trigger`).

---

## Task 6: Blob-present gate + final output

**Files:**
- Live: `select_area` (selectCHOP), `gate_present` (expressionCHOP), `math_gate` (mathCHOP); wire to `out_rest_trigger`.

**Interfaces:**
- Consumes: `in2` (`blob_idx0` row), `trigger_rest` (`chan1`).
- Produces: `out_rest_trigger` CHOP channel `chan1` = `trigger_rest.chan1 × gate`, where `gate = 1` when `area>0` (or gate disabled), else `0`.

- [ ] **Step 1: Verify absent**

`execute_script`: `print([op('/project1/cont_rest_trigger/'+n) for n in ('select_area','gate_present','math_gate')])` → Expected `[None, None, None]`.

- [ ] **Step 2: Build the gate chain**

`execute_script` (undo_label `rest: gate`):
```python
cont = op('/project1/cont_rest_trigger')
sel = cont.create(selectCHOP, 'select_area')
sel.par.channames = 'area'
sel.par.renamefrom = 'area'
sel.par.renameto = 'chan1'
op('/project1/cont_rest_trigger/in2').outputConnectors[0].connect(sel.inputConnectors[0])

gp = cont.create(expressionCHOP, 'gate_present')
# gate open (1) when the Present Gate is off, or a blob is present (area>0)
gp.par.expr0 = '1.0 if (parent().par.Presentgate.eval() == 0 or me.inputVal > 0) else 0.0'
sel.outputConnectors[0].connect(gp.inputConnectors[0])

mg = cont.create(mathCHOP, 'math_gate')
mg.par.chopop = 'multiply'                 # multiply matching channels across inputs
op('/project1/cont_rest_trigger/trigger_rest').outputConnectors[0].connect(mg.inputConnectors[0])
gp.outputConnectors[0].connect(mg.inputConnectors[1])
mg.outputConnectors[0].connect(op('/project1/cont_rest_trigger/out_rest_trigger').inputConnectors[0])

sel.nodeX, sel.nodeY = -400, -200
gp.nodeX,  gp.nodeY  = -200, -200
mg.nodeX,  mg.nodeY  = 650, 0
print('built:', [n for n in ('select_area','gate_present','math_gate') if op('/project1/cont_rest_trigger/'+n)])
```
Note: `Presentgate` par is added in Task 7. Until then the expression will error on `parent().par.Presentgate`; that is expected and cleared by Task 7. To keep Task 6 independently verifiable, temporarily set `gp.par.expr0 = '1.0 if me.inputVal > 0 else 0.0'` for Steps 3–4, then restore the full expression in Task 7 Step 2.

- [ ] **Step 3: Verify gate math**

`execute_script`:
```python
gp = op('/project1/cont_rest_trigger/gate_present')
mg = op('/project1/cont_rest_trigger/math_gate')
out = op('/project1/cont_rest_trigger/out_rest_trigger')
print('gate val (area=0 -> expect 0):', gp['chan1'].eval())
print('out chans:', [c.name for c in out.chans()], 'val:', [c.eval() for c in out.chans()])
```
Expected: with the feed idle (`area=0`), `gate val: 0.0`, and `out_rest_trigger` `chan1 = 0.0` regardless of trigger state. `out chans: ['chan1']`. Then `get_errors` — expected clean (with the temporary gate expression from Step 2's note).

- [ ] **Step 4: Checkpoint**

`save_checkpoint` `path="/project1"` (label `rest-t6-gate`).

---

## Task 7: Custom parameter page

**Files:**
- Live: add "Rest Trigger" page to `cont_rest_trigger`; bind internals to the custom pars.

**Interfaces:**
- Consumes: nothing new.
- Produces: `cont_rest_trigger` custom pars `Threshfrac`(float, 0.85), `Windowsec`(float, 3.0), `Edgeclean`(float, 0), `Presentgate`(toggle, On) driving `trigger_rest.threshup`, `trail_morph.wlength`, `top_maskclean.size`, and `gate_present`.

- [ ] **Step 1: Verify page absent**

`execute_script`: `print([p.name for p in op('/project1/cont_rest_trigger').customPars])` → Expected `[]`.

- [ ] **Step 2: Add pars and bind internals**

`execute_script` (undo_label `rest: custom pars`):
```python
cont = op('/project1/cont_rest_trigger')
pg = cont.appendCustomPage('Rest Trigger')
pTf = pg.appendFloat('Threshfrac', label='Threshold Frac')[0]; pTf.default = 0.85; pTf.val = 0.85; pTf.normMin, pTf.normMax = 0.0, 1.0
pW  = pg.appendFloat('Windowsec', label='Window')[0];          pW.default = 3.0;  pW.val = 3.0;  pW.normMin, pW.normMax = 0.1, 10.0
pE  = pg.appendFloat('Edgeclean', label='Edge Clean')[0];      pE.default = 0.0;  pE.val = 0.0;  pE.normMin, pE.normMax = 0.0, 5.0
pP  = pg.appendToggle('Presentgate', label='Present Gate')[0]; pP.default = True; pP.val = True

# bind internals to the custom pars
t = op('/project1/cont_rest_trigger/trigger_rest')
t.par.threshup.expr = "parent().par.Threshfrac * op('max_morph')[0]"
op('/project1/cont_rest_trigger/trail_morph').par.wlength.expr = 'parent().par.Windowsec'
op('/project1/cont_rest_trigger/trail_morph').par.wlength.mode = ParMode.EXPRESSION
op('/project1/cont_rest_trigger/top_maskclean').par.size.expr = 'parent().par.Edgeclean'
op('/project1/cont_rest_trigger/top_maskclean').par.size.mode = ParMode.EXPRESSION
# restore the full gate expression now that Presentgate exists
op('/project1/cont_rest_trigger/gate_present').par.expr0 = '1.0 if (parent().par.Presentgate.eval() == 0 or me.inputVal > 0) else 0.0'
print('pars:', [p.name for p in cont.customPars])
```
Expected: `pars: ['Threshfrac', 'Windowsec', 'Edgeclean', 'Presentgate']`.

- [ ] **Step 3: Verify pars drive internals**

`execute_script`:
```python
cont = op('/project1/cont_rest_trigger')
cont.par.Windowsec = 2.0
cont.par.Threshfrac = 0.5
print('trail wlength:', op('/project1/cont_rest_trigger/trail_morph').par.wlength.eval())
print('threshup:', op('/project1/cont_rest_trigger/trigger_rest').par.threshup.eval(),
      'expect ~', 0.5 * op('/project1/cont_rest_trigger/max_morph')[0].eval())
cont.par.Windowsec = 3.0; cont.par.Threshfrac = 0.85    # restore defaults
```
Expected: `trail wlength: 2.0`; `threshup` equals `0.5 × max_morph[0]`. Then `get_errors` — expected clean (the `gate_present` error from Task 6 is now resolved).

- [ ] **Step 4: Checkpoint**

`save_checkpoint` `path="/project1"` (label `rest-t7-pars`).

---

## Task 8: End-to-end validation + docs

**Files:**
- Create: `touchdesigner/resttrigger/README.md`
- Live: final full-subtree verification + checkpoint.

**Interfaces:**
- Consumes: everything above.
- Produces: a documented, verified container.

- [ ] **Step 1: Full structural verification**

`execute_script`:
```python
cont = op('/project1/cont_rest_trigger')
need = ['in1','in2','top_maskclean','feedback_mask','text_morph','glsl_morph',
        'script_morph_energy','trail_morph','max_morph','trigger_rest',
        'select_area','gate_present','math_gate','out_rest_trigger','out_morph_energy','out_morph_viz']
have = set(c.name for c in cont.children)
print('missing:', [n for n in need if n not in have])
# end-to-end signal read
cont.op('trigger_rest').cook(force=True)
print('energy:', cont.op('script_morph_energy')['morph_energy'].eval(),
      'max:', cont.op('max_morph')[0].eval(),
      'threshup:', cont.op('trigger_rest').par.threshup.eval(),
      'trigger:', cont.op('trigger_rest')['chan1'].eval(),
      'gate:', cont.op('gate_present')['chan1'].eval(),
      'OUT:', cont.op('out_rest_trigger')['chan1'].eval())
```
Expected: `missing: []`; all values finite; with an idle/empty feed, `gate: 0.0` and `OUT: 0.0`. Then `get_errors` on the subtree — expected fully clean.

- [ ] **Step 2: Live behavioral validation (feed running)**

Requires the blob tracker fed (live OptiTrack IR or a movie replay into `cont_blobtrack_glsl`). Ask the user to move the sticker, then rest it. Verify via repeated reads (or a CHOP viewer): `morph_energy` rises during motion; `max_morph` tracks the peak; a single `OUT` pulse (chan1→1→0 over ~6 samples) fires as motion settles and `area>0`; a small edge graze produces no pulse; removing the blob (`area→0`) produces no pulse. If the feed is not available this session, document it as a pending live check and hand it to the user.

- [ ] **Step 3: Write the container README (repo)**

Create `touchdesigner/resttrigger/README.md` documenting: purpose, inputs (`in1`=out_mask TOP, `in2`=blob_idx0 CHOP), outputs (`out_rest_trigger`, `out_morph_energy`, `out_morph_viz`), the morph-energy definition, the `trigger7` param match, the custom "Rest Trigger" page, and the known risks from spec §10 (Feedback reliability + Cache TOP fallback, tiny-sticker SNR, bouncy-landing double-fire). Mirror the structure of `touchdesigner/blobtrack/README.md`.

- [ ] **Step 4: Commit docs (repo)**

```bash
git -C "C:/Users/NICKESCHEN/dev/TD-MCP" add touchdesigner/resttrigger/README.md
git -C "C:/Users/NICKESCHEN/dev/TD-MCP" commit -m "docs(rest-trigger): container README"
```

- [ ] **Step 5: Final checkpoint + hand-off note**

`save_checkpoint` `path="/project1"` (label `rest-trigger-complete`). Then tell the user: the container is built and verified in the live session; **persisting to the `.toe` on disk is theirs to do at the keyboard** (do not call `project.save()` from the bridge on this untitled session). Note any pending live behavioral check from Step 2.

---

## Self-Review Notes

- **Spec coverage:** §3 inputs/outputs → Task 1; §4.1 pre-filter → Task 2 + Task 7 binding; §4.2 feedback → Task 2; §4.3 glsl_morph → Task 2; §4.4 reduce → Task 3; §4.5 trail/max → Task 4; §4.6 trigger → Task 5; §4.7 gate → Task 6; §5 param match → Task 5 table + verify; §7 custom pars → Task 7; §8 placement/save → Global Constraints + per-task checkpoints; §9 verification → each task + Task 8; §10 risks → README (Task 8 Step 3). All covered.
- **Reduction approach:** uses a Script CHOP numpyArray mean rather than `TOP to CHOP`, because this build is documented (blobtrack README) to not emit per-pixel samples reliably from `TOP to CHOP`. This is the same GPU→CPU idiom `script_idtrack` already uses.
- **Type consistency:** the driving channel is `morph_energy` end-to-end (script→trail→analyze→trigger input); the trigger's *output* channel is `chan1`; `select_area` renames `area→chan1` so `math_gate` multiplies `chan1×chan1→chan1`. Consistent across Tasks 3–8.
- **Ordering caveat:** Task 6's `gate_present` expression references `Presentgate` (created in Task 7); Task 6's note swaps in a temporary expression for independent verification, and Task 7 Step 2 restores the full one.
