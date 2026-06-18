# TD POP Attribute Math

Use this note when editing POP point attributes with native POP operators, especially `attributecombinePOP` and `mathcombinePOP`. The goal is to keep point motion in the POP network, not in Script CHOPs, Python callbacks, or Geometry COMP instance scale hacks.

## Workflow Rules

- Save the TouchDesigner project before mutating the live network.
- Prefer changing parameters on existing POPs when the user has selected or named them.
- Verify with a `poptoCHOP` or existing CHOP export by checking numeric channel ranges, especially `P_0`, `P_1`, and `P_2`.
- If a requested scalar attribute such as `brightness` is all zero, do not assume it is the useful signal. Inspect `Color_0`, `Color_1`, `Color_2`, and `Color_3`; in this project the usable brightness-like value was often `Color.rgb`.
- Do not add Script CHOPs or Python-generated attributes for POP displacement unless explicitly requested.

## Native Z Displacement Pattern

For displacement by brightness in Z using only `Attribute Combine POP` and `Math Combine POP`:

1. Use `Attribute Combine POP` to copy the source color/brightness attribute to a helper point attribute.
2. Use `Math Combine POP` to derive a scalar from that helper.
3. Multiply the scalar by a constant `float3` Z vector.
4. Add that vector back into `P`.
5. Route the result to the POP output used by render/instance consumers.

The resulting position change is:

```text
P.z = P.z + avg(height.rgb) * z_amount
```

## Attribute Combine POP Settings

For the current `tile_chain_0_0` pattern:

```text
attrclass              point
lengthmismatchaction   repeat
duplicateattrs         autorename
input0attrs            *
input0renameto
input1attrs            Color
input1renameto         height
```

Notes:

- `Attribute Combine POP` accepted `Color`, but not `Color.rgb`, as the input attribute selector.
- When `Color` is renamed to `height`, it becomes a four-component helper visible as `height_0..height_3` in `poptoCHOP`.
- Use `height.rgb` later in `Math Combine POP` to ignore alpha.

## Math Combine POP Settings

Use a constant vector and three combine rows:

```text
vec0name       zaxis
vec0type       float3
vec0value0     0
vec0value1     0
vec0value2     0.035
```

```text
comb0oper      compavg
comb0scopea    height.rgb
comb0scopeb
comb0result    height_scalar

comb1oper      mult
comb1scopea    height_scalar
comb1scopeb    zaxis
comb1result    zoffset

comb2oper      add
comb2scopea    P
comb2scopeb    zoffset
comb2result    P
```

Cleanup:

```text
delattrs       zaxis zoffset height_scalar
```

Important details:

- `zaxis` must be `float3`. A one-component `float` vector will not create a valid Z offset for adding to `P`.
- `comb0scopea = height.rgb` is valid in `Math Combine POP`; `height(0:2)` is not valid and gives an invalid component-pattern error.
- Writing back to `P` is what moves the points. Creating a separate `PointScale`, `height`, or `zoffset` attribute alone does not move points.
- POP sequence count parameters such as `vec` and `comb` display as `0` even when rows exist; inspect `par.vec.sequence.numBlocks` or the presence of `vec0...`, `comb0...`, `comb1...` parameters rather than relying on the displayed `0`.

## Verification

Use or create a temporary `poptoCHOP` only for inspection. Set:

```text
downloadtype   immediate
extract        points
nameformat     precise
attribscope    *
```

Then check:

```text
P_2 min/max/mean
height_0 height_1 height_2 ranges
Color_0 Color_1 Color_2 ranges
```

Expected for the current setup:

```text
P_2 range: 0.0 .. 0.035
height_0..2 range: 0.0 .. 1.0
brightness: may remain 0.0 everywhere
```

If `P_2` remains `0.0 .. 0.0`, check these first:

- `Attribute Combine POP` is actually upstream of `Math Combine POP`.
- `Math Combine POP` receives the attribute name used in `comb0scopea`.
- `vec0type` is `float3`, not `float`.
- `comb2result` is `P`.
- The final `outPOP` is fed by the `Math Combine POP`, not by the pre-displacement POP.

## Current Network State From This Session

Current live output path:

```text
/project1/resolution_hacking/tile_chain_0_0/attcombine1
  -> /project1/resolution_hacking/tile_chain_0_0/mathcombine1
  -> /project1/resolution_hacking/tile_chain_0_0/out1
```

Current render attribute reader:

```text
/project1/resolution_hacking/tile_chain_0_0/circle_point_render/pop_attrs
```

It now points to:

```text
/project1/resolution_hacking/tile_chain_0_0/out1
```

and uses:

```text
attribscope = P Color height brightness
```

`geo_instanced_circles` uses `P_0`, `P_1`, and `P_2` for instance translation. Its previous `PointScale` Z-scale reference was cleared because displacement is now baked into `P`.

## Difference From The Earlier `circle_point_render` Attempt

The earlier attempt inside `circle_point_render` built a separate render-local POP/CHOP path:

```text
pop_pointscale_from_color
probe_pointscale_chop
inst_attrs_zscale
pointscale_from_color_native
lookup_point_brightness
```

That approach differed from the current state in several ways:

- It tried to drive instance Z scale through a generated `PointScale`/`zscale` channel.
- It was partly outside the main POP chain and depended on `pop_attrs` reading a derived branch.
- It included a Script CHOP path at one point, which the user rejected.
- It did not actually move POP point positions; it only attempted to scale rendered instances.

The current state does not rely on that render-local branch. The point positions are changed upstream in `tile_chain_0_0` before `out1`, and render consumers read the displaced `P_2` directly.
