# Five Overlapping Round-Robin Sweeps — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the single trigger→ramp chain in `/project1` into 5 independent sweep units fired by an external round-robin pulse, with overlapping envelopes, a composite of all 5, and a live `num_active_sweep` count.

**Architecture:** Flat ops suffixed `_0.._4`. Unit `_0` is the renamed existing chain; `_1.._4` are clones. One shared `ramp_keys_master` Table DAT fans out to all five Evaluate DATs; each eval resolves keys against its own trigger via the eval's `me.name` (verified: Evaluate DAT binds `me` to itself). A CHOP Execute DAT advances a stored index on each external pulse and fires that unit's trigger.

**Tech Stack:** TouchDesigner (live `/project1` via td-mcp bridge), Python `execute_script`, CHOPs/TOPs/DATs.

## Global Constraints

- All edits are to the **live, unsaved** session via the bridge; persist with `project.save()` only after verification.
- `execute_script` runs in a wrapper: **no comprehensions over outer-scope locals, no closures/recursion over top-level names** — use explicit loops and inline helpers.
- Never press Start/Restart on `/project1/TD_MCP`. Never combine bulk-destroy with force-cook in one script.
- Preserve the existing `mask_reset` channel on `master_controls`.
- TOP filter discipline: set new resampling TOPs to Nearest Pixel where relevant (ramps here are gradients; not critical, but keep composites at default unless blur appears).
- Verification is numeric/functional (`get_par_value`, `execute_script` reads, `get_errors`) — panels aren't screenshottable.

---

### Task 0: Safety restore point

**Files:** none (live session only)

- [ ] **Step 1: Save a known-good restore point**

`execute_script`:
```python
project.save()
print("saved:", project.name)
```
Expected: prints the project name, no errors.

- [ ] **Step 2: Checkpoint the network before the destructive rename**

Use `save_checkpoint` tool: `op_path=/project1`, `name=pre_5sweeps`, `description="before converting single sweep chain into 5-unit round-robin"`.
Expected: checkpoint saved.

---

### Task 1: Convert existing chain → unit `_0` and shared master keys

**Files:** ops in `/project1`: `ramp_control`, `eval1`, `ramp1`, `ramp2`, `comp2`, `ramp1_keys`

**Interfaces:**
- Produces: `trig_0` (Trigger CHOP, chan `sweep`), `eval_0` (Evaluate DAT), `rampA_0`/`rampB_0` (Ramp TOPs), `comp_0` (Composite TOP), `ramp_keys_master` (Table DAT). Key cells resolve `op('trig_'+me.name.split('_')[-1])[0] ± .3`.

- [ ] **Step 1: Capture pre-rename reference map (verify what points at the old names)**

`execute_script`:
```python
targets = ['ramp_control','eval1','ramp1','ramp2','comp2','ramp1_keys']
root = op('/project1')
hits = []
kids = root.findChildren(depth=3)
for o in kids:
    for p in o.pars():
        m = p.mode.name
        if m == 'EXPRESSION':
            e = p.expr or ''
            for t in targets:
                if ("'"+t+"'") in e or ('/'+t) in e:
                    hits.append(o.path + '.' + p.name + ' -> ' + e)
# wire consumers of comp2 / outputs
for t in targets:
    o = op('/project1/'+t)
    outs = []
    for c in o.outputs:
        outs.append(c.path)
    hits.append('OUT ' + t + ': ' + str(outs))
print('\n'.join(hits))
```
Expected: lists `comp3` as a consumer of `comp2`; the only expression refs to `ramp_control` are inside `ramp1_keys` cells (which we rewrite next). Record anything else for repointing.

- [ ] **Step 2: Rename the six ops to the `_0` / master scheme**

`execute_script`, undo_label="rename to _0":
```python
ren = [('ramp_control','trig_0'),
       ('eval1','eval_0'),
       ('ramp1','rampA_0'),
       ('ramp2','rampB_0'),
       ('comp2','comp_0'),
       ('ramp1_keys','ramp_keys_master')]
for old,new in ren:
    o = op('/project1/'+old)
    o.name = new
    print(old, '->', o.name)
```
Expected: all six print new names, no errors.

- [ ] **Step 3: Rewrite the master key cells to be unit-relative**

`execute_script`, undo_label="rel key exprs":
```python
k = op('/project1/ramp_keys_master')
# pos column is col 0; rows 2,3,4 hold the sweep expressions (row0=header,row1=static 0,row5=static 1)
base = "op('trig_' + me.name.split('_')[-1])[0]"
k[2,0].val = base + " + .3"
k[3,0].val = base
k[4,0].val = base + " - .3"
out = ""
for ri in range(k.numRows):
    row = []
    for ci in range(k.numCols):
        row.append(k[ri,ci].val)
    out += "r%d %s\n" % (ri, row)
print(out)
```
Expected: rows 2–4 now read `op('trig_' + me.name.split('_')[-1])[0] + .3` etc.; header + rows 1/5 unchanged.

- [ ] **Step 4: Verify unit `_0` still resolves and animates**

`execute_script`:
```python
ev = op('/project1/eval_0')
# force a non-zero trigger value to confirm keys move
t = op('/project1/trig_0')
t.par.trigger.pulse()
print('eval_0 numRows', ev.numRows, 'rampA_0 dat ->', op('/project1/rampA_0').par.dat.eval().path)
# read resolved pos column
out = ""
for ri in range(ev.numRows):
    out += str(ev[ri,0].val) + " | "
print('resolved pos:', out)
print('errors:', [c[0].val for c in op('/project1').errors] if False else 'see get_errors')
```
Then run `get_errors`.
Expected: `rampA_0.dat` points to `eval_0`; resolved pos column shows numeric values (the middle three reflecting the trigger); no errors.

- [ ] **Step 5: Confirm `comp_0`→`comp3` wire intact**

`get_operator_info` on `/project1/comp3` (or `execute_script` reading `op('/project1/comp3').inputs`).
Expected: `comp3` input still includes `/project1/comp_0`.

- [ ] **Step 6: Commit checkpoint**

`save_checkpoint`: `op_path=/project1`, `name=unit0_converted`, `description="existing chain renamed to _0 + shared master keys, unit-relative exprs"`.

---

### Task 2: Clone units `_1.._4`

**Files:** ops in `/project1`

**Interfaces:**
- Consumes: `trig_0`,`eval_0`,`rampA_0`,`rampB_0`,`comp_0`, `ramp_keys_master`.
- Produces: `trig_N`,`eval_N`,`rampA_N`,`rampB_N`,`comp_N` for `N in 1..4`. Each `eval_N` input = `ramp_keys_master`; each `rampA_N.dat = eval_N`; each `comp_N` = `rampB_N` over `rampA_N`. Each `trig_N` independent.

- [ ] **Step 1: Copy the unit-0 op set 4× and rename**

`execute_script`, undo_label="clone units 1-4":
```python
root = op('/project1')
srcnames = ['trig_0','eval_0','rampA_0','rampB_0','comp_0']
src = []
for nm in srcnames:
    src.append(op('/project1/'+nm))
made = {}
for N in range(1,5):
    copies = root.copyOPs(src)   # preserves internal wiring + external ref to ramp_keys_master
    for c in copies:
        # rename suffix 0 -> N (names are like 'trig_0')
        stem = c.name.rsplit('_',1)[0]
        c.name = stem + '_' + str(N)
    made[N] = [c.name for c in copies]
for N in made:
    print(N, made[N])
```
Expected: prints units 1..4 each with `['trig_1','eval_1','rampA_1','rampB_1','comp_1']` style names. No name collisions/errors.

- [ ] **Step 2: Lay the clones out in the network (readability)**

`execute_script`:
```python
base_y = 1250
for N in range(0,5):
    dx = 0
    row_y = base_y - N*350
    for nm,off in [('trig_',-525),('eval_',-225),('rampA_',0),('rampB_',-275),('comp_',225)]:
        o = op('/project1/'+nm+str(N))
        if o:
            o.nodeX = 2200 + off + (0 if nm!='trig_' else -150)
            o.nodeY = row_y + (0 if nm in ('rampA_','comp_') else (-150 if nm=='rampB_' else 0))
print('laid out')
```
Expected: prints "laid out"; nodes spread into 5 rows (cosmetic — exact coords not asserted).

- [ ] **Step 3: Verify each clone's wiring + per-unit trigger resolution**

`execute_script`:
```python
out = ""
for N in range(0,5):
    ev = op('/project1/eval_'+str(N))
    ra = op('/project1/rampA_'+str(N))
    cp = op('/project1/comp_'+str(N))
    ev_in = ev.inputs[0].path if ev.inputs else 'NONE'
    ra_dat = ra.par.dat.eval()
    ra_dat = ra_dat.path if ra_dat else 'NONE'
    cp_ins = []
    for i in cp.inputs:
        cp_ins.append(i.name)
    out += "unit %d: eval.in=%s rampA.dat=%s comp.in=%s\n" % (N, ev_in, ra_dat, cp_ins)
print(out)
```
Expected: every unit shows `eval.in=ramp_keys_master`, `rampA.dat=eval_N` (matching N), `comp.in=[rampB_N, rampA_N]` (two inputs).

- [ ] **Step 4: Verify independent triggers drive distinct eval output**

`execute_script`:
```python
op('/project1/trig_1').par.trigger.pulse()
import time
# read trig values and eval_1 resolved middle key vs eval_3 (untriggered)
v1 = op('/project1/trig_1')[0]
v3 = op('/project1/trig_3')[0]
print('trig_1[0]=', v1, 'trig_3[0]=', v3)
print('eval_1 pos[3]=', op('/project1/eval_1')[3,0].val, 'eval_3 pos[3]=', op('/project1/eval_3')[3,0].val)
```
Expected: `trig_1[0]` rises after its pulse while `trig_3[0]` stays 0; `eval_1`'s resolved middle position differs from `eval_3`'s — proving each eval reads its own trigger. (Values are time-dependent; assert only that eval_1 ≠ eval_3 when one is triggered.)

- [ ] **Step 5: Run `get_errors`**

Expected: no cook-dependency-loop or expression errors.

- [ ] **Step 6: Checkpoint**

`save_checkpoint`: `op_path=/project1`, `name=units_cloned`, `description="trig/eval/rampA/rampB/comp _1.._4 cloned, shared master fan-out verified"`.

---

### Task 3: Composite all 5 units → `comp_all`

**Files:** create `/project1/comp_all` (Composite TOP)

**Interfaces:**
- Consumes: `comp_0..comp_4`.
- Produces: `comp_all` (Composite TOP) with the 5 unit outputs as inputs, `operand=over` (or `add` if overlap should brighten).

- [ ] **Step 1: Create and wire `comp_all`**

`execute_script`, undo_label="comp_all":
```python
root = op('/project1')
ca = op('/project1/comp_all')
if not ca:
    ca = root.create(compositeTOP, 'comp_all')
ca.nodeX = 3100; ca.nodeY = 200
# wire comp_0..comp_4 into inputs 0..4
for N in range(0,5):
    src = op('/project1/comp_'+str(N))
    ca.inputConnectors[N].connect(src)
ca.par.operand = 'over'
ins = []
for i in ca.inputs:
    ins.append(i.name)
print('comp_all inputs:', ins, 'operand:', ca.par.operand.eval())
```
Expected: `comp_all inputs: ['comp_0','comp_1','comp_2','comp_3','comp_4'] operand: over`.

- [ ] **Step 2: Verify it cooks without error**

`execute_script`:
```python
ca = op('/project1/comp_all')
print('comp_all res:', ca.width, 'x', ca.height, 'cooked:', ca.cookedThisFrame)
```
Then `get_errors`.
Expected: nonzero resolution, no errors.

- [ ] **Step 3: Checkpoint**

`save_checkpoint`: `op_path=/project1`, `name=comp_all_wired`, `description="5 units composited over each other"`.

---

### Task 4: Round-robin sequencer (external pulse advances)

**Files:** create `/project1/seq_advance` (Constant CHOP, input), `/project1/seq_exec` (CHOP Execute DAT)

**Interfaces:**
- Consumes: `trig_0..trig_4`.
- Produces: `seq_advance` (CHOP whose channel `advance` the user wires/pulses), `seq_exec` driving round-robin. Index stored at `seq_exec.fetch('idx',0)`.

- [ ] **Step 1: Create the advance input CHOP**

`execute_script`, undo_label="seq_advance":
```python
root = op('/project1')
sa = op('/project1/seq_advance')
if not sa:
    sa = root.create(constantCHOP, 'seq_advance')
sa.nodeX = 1700; sa.nodeY = 1400
sa.par.name0 = 'advance'
sa.par.value0 = 0
print('seq_advance chan:', [c.name for c in sa.chans()])
```
Expected: `seq_advance chan: ['advance']`.

- [ ] **Step 2: Create the CHOP Execute DAT and point it at `seq_advance`**

`execute_script`, undo_label="seq_exec":
```python
root = op('/project1')
se = op('/project1/seq_exec')
if not se:
    se = root.create(chopexecDAT, 'seq_exec')
se.nodeX = 1700; se.nodeY = 1250
se.par.chop = 'seq_advance'
se.par.offtoon = True      # fire on off->on edge
se.par.valuechange = False
se.par.whileon = False
se.par.ononchange = False
print('seq_exec chop:', se.par.chop.eval(), 'offtoon:', se.par.offtoon.eval())
```
Expected: `seq_exec chop: seq_advance offtoon: True`.

- [ ] **Step 3: Write the callback body**

`execute_script`, undo_label="seq_exec body":
```python
se = op('/project1/seq_exec')
body = (
"def onOffToOn(channel, sampleIndex, val, prev):\n"
"    i = me.fetch('idx', 0)\n"
"    trg = op('trig_' + str(i))\n"
"    if trg is not None:\n"
"        trg.par.trigger.pulse()\n"
"    me.store('idx', (i + 1) % 5)\n"
"    return\n"
)
se.text = body
print(se.text)
```
Expected: prints the callback; `seq_exec` has no syntax errors (check `get_errors`).

- [ ] **Step 4: Verify round-robin order**

`execute_script`:
```python
se = op('/project1/seq_exec')
se.store('idx', 0)
sa = op('/project1/seq_advance')
order = []
for n in range(7):
    # simulate an off->on edge: 0 then 1
    sa.par.value0 = 0
    sa.cook(force=True)
    before = se.fetch('idx', 0)
    sa.par.value0 = 1
    sa.cook(force=True)
    order.append(before)
print('fired index sequence:', order)
```
Expected: `fired index sequence: [0, 1, 2, 3, 4, 0, 1]` (index used at each pulse, wrapping at 5). If the off→on callback doesn't fire under forced cook, fall back to verifying by manually invoking the index math; note the limitation.

- [ ] **Step 5: Run `get_errors`**

Expected: no errors from `seq_exec`.

- [ ] **Step 6: Checkpoint**

`save_checkpoint`: `op_path=/project1`, `name=sequencer_wired`, `description="external-pulse round-robin sequencer firing trig_0..4 in order"`.

---

### Task 5: `num_active_sweep` on `master_controls`

**Files:** create `/project1/num_active_sweep` (Constant CHOP) + a merge into `master_controls`'s input

**Interfaces:**
- Consumes: `trig_0..trig_4`, existing `master_controls` input (carrying `mask_reset`).
- Produces: `master_controls` Null now outputs both `mask_reset` and `num_active_sweep`.

- [ ] **Step 1: Inspect `master_controls` current input**

`execute_script`:
```python
mc = op('/project1/master_controls')
ins = []
for i in mc.inputs:
    ins.append(i.path)
print('master_controls type:', mc.type, 'inputs:', ins, 'chans:', [c.name for c in mc.chans()])
```
Expected: prints the current upstream op feeding `mask_reset` (record its path as `MC_SRC`).

- [ ] **Step 2: Create the count CHOP**

`execute_script`, undo_label="num_active_sweep":
```python
root = op('/project1')
na = op('/project1/num_active_sweep')
if not na:
    na = root.create(constantCHOP, 'num_active_sweep')
na.nodeX = 1700; na.nodeY = 1100
na.par.name0 = 'num_active_sweep'
expr = ("int(op('trig_0')[0]>0)+int(op('trig_1')[0]>0)+int(op('trig_2')[0]>0)"
        "+int(op('trig_3')[0]>0)+int(op('trig_4')[0]>0)")
na.par.value0.expr = expr
print('num_active_sweep value:', na[0])
```
Expected: prints a numeric value (0 when idle).

- [ ] **Step 3: Merge `num_active_sweep` into `master_controls` input (preserve `mask_reset`)**

`execute_script`, undo_label="merge into master_controls":
```python
root = op('/project1')
mc = op('/project1/master_controls')
na = op('/project1/num_active_sweep')
# capture existing source
mc_src = mc.inputs[0] if mc.inputs else None
mrg = op('/project1/mc_merge')
if not mrg:
    mrg = root.create(mergeCHOP, 'mc_merge')
mrg.nodeX = mc.nodeX - 150; mrg.nodeY = mc.nodeY
# wire: [existing src, num_active_sweep] -> merge -> master_controls
mrg.inputConnectors[0].connect(mc_src) if mc_src else None
mrg.inputConnectors[1].connect(na)
mc.inputConnectors[0].connect(mrg)
print('merge inputs:', [i.path for i in mrg.inputs])
print('master_controls chans:', [c.name for c in mc.chans()])
```
Expected: `master_controls chans` now includes BOTH `mask_reset` and `num_active_sweep`.

- [ ] **Step 4: Verify the count reacts to active sweeps**

`execute_script`:
```python
op('/project1/trig_0').par.trigger.pulse()
op('/project1/trig_2').par.trigger.pulse()
mc = op('/project1/master_controls')
mc.cook(force=True)
vals = {}
for c in mc.chans():
    vals[c.name] = c[0]
print('master_controls:', vals)
```
Expected: `num_active_sweep` reads ≥1 (≈2 right after two pulses, while both envelopes are >0); `mask_reset` still present.

- [ ] **Step 5: Run `get_errors`**

Expected: no errors.

- [ ] **Step 6: Checkpoint**

`save_checkpoint`: `op_path=/project1`, `name=num_active_sweep_added`, `description="num_active_sweep merged into master_controls alongside mask_reset"`.

---

### Task 6: Final integration verification + persist

**Files:** none (verify + save)

- [ ] **Step 1: Full round-robin + overlap smoke test**

`execute_script`:
```python
se = op('/project1/seq_exec'); se.store('idx',0)
sa = op('/project1/seq_advance')
mc = op('/project1/master_controls')
log = []
for n in range(5):
    sa.par.value0 = 0; sa.cook(force=True)
    sa.par.value0 = 1; sa.cook(force=True)
    mc.cook(force=True)
    actives = 0
    for c in mc.chans():
        if c.name == 'num_active_sweep':
            actives = c[0]
    log.append((n, round(actives,2)))
print('pulse -> num_active_sweep:', log)
```
Expected: as pulses accumulate faster than the release tail, `num_active_sweep` climbs above 1 (overlap observable).

- [ ] **Step 2: Confirm no errors and `comp_all` cooks**

Run `get_errors`; `execute_script`: `print(op('/project1/comp_all').width, op('/project1/comp_all').height)`.
Expected: no errors; nonzero resolution.

- [ ] **Step 3: Persist**

`execute_script`: `project.save(); print('saved')`.
Expected: prints "saved".

- [ ] **Step 4: Final checkpoint**

`save_checkpoint`: `op_path=/project1`, `name=five_sweeps_complete`, `description="5 overlapping round-robin sweeps + num_active_sweep, verified"`.

---

## Self-Review

- **Spec coverage:** shared master keys (Task 1) ✓; 5 units (Tasks 1–2) ✓; per-unit trigger resolution via `me.name` (Task 1 Step 3, Task 2 Step 4) ✓; round-robin external pulse (Task 4) ✓; overlap (Task 6 Step 1) ✓; composite all 5 (Task 3) ✓; `num_active_sweep` preserving `mask_reset` (Task 5) ✓; convert existing → `_0` (Task 1) ✓; flat suffixed ops ✓; save discipline (Task 0, Task 6) ✓.
- **Placeholder scan:** every step has concrete code; the one fallback note (Task 4 Step 4) is an explicit contingency, not a placeholder.
- **Type/name consistency:** `trig_N`/`eval_N`/`rampA_N`/`rampB_N`/`comp_N`/`comp_all`/`seq_advance`/`seq_exec`/`num_active_sweep`/`mc_merge` used consistently; index stored as `idx`; channel `advance`.
