# Threshold Convergence Method — Improvement Report

## Overview

This report covers the development and refinement of a batch image/video
threshold processing pipeline built inside TouchDesigner via the TD MCP tool
interface. The goal was to find a threshold value for each image such that
the proportion of white pixels after binarisation falls within a target range
of [0.30, 0.70]. Three approaches were tested across a reference set of
106 images.

---

## Convergence Results by Approach

| Approach | Converged | % | Notes |
|---|---|---|---|
| Raw global threshold | ~24/106 | ~23% | Baseline; images with bright/dark bias fail |
| Histogram normalisation (min-max stretch) | 27/106 | 25% | Scales range, does not reshape distribution |
| **Histogram equalization (PIL ImageOps)** | **75/106** | **71%** | Redistributes histogram uniformly; near-guaranteed convergence |

---

## Method Descriptions

### 1. Raw Global Threshold
Binary search over threshold ∈ [0, 1] applied directly to BT.709 luminance.
Images with dominant bright backgrounds (product shots, illustrations on white)
or uniformly dark content could not be driven into the target proportion range
by any single global threshold value.

### 2. Histogram Normalisation (min-max stretch)
Pre-processes luminance via `luma = (luma − min) / (max − min)` before
thresholding. Stretches the existing tonal range to fill [0, 1] but does not
change the shape of the distribution. A heavily skewed image (e.g. 80% bright
pixels) remains heavily skewed after stretching, so the binary search still
cannot find a threshold that produces ≤ 70% white pixels. Improvement minimal:
27/106 (25%).

### 3. Histogram Equalization (PIL `ImageOps.equalize`)
Remaps the 8-bit luminance histogram so each value has equal frequency.
By construction, threshold = 0.50 yields exactly 50% white pixels on any
equalised image with a non-trivial histogram. This makes the binary search
converge in a single iteration for every qualifying image. Result: 75/106 (71%).

A notable side-effect: **all 75 converging images land at threshold = 0.500**,
meaning the threshold value itself loses diagnostic meaning under this method —
it no longer reflects the image's tonal character, only the method's guarantee.
The threshold is informative only in approaches 1 and 2.

---

## Why 31 Images Still Fail Under Equalization

The remaining 31 non-converging images fall into identifiable categories:

- **Near-binary / sparse images** — images that are almost entirely one colour
  with small isolated elements. After equalization the histogram maps 0→0 and
  255→255 with nothing in between. Proportion stays near 0 or near 1 for all
  thresholds (observed prop values: 0.948, 0.986, 0.995, 1.000, 0.036).
- **Palette / indexed-colour PNGs with transparency** — PIL warns about these
  images during processing; their effective luma after RGBA conversion may be
  degenerate.
- **Genuinely flat images** — uniform fills where `luma.max == luma.min`,
  so equalization is a no-op.

For these images, adaptive (local) thresholding (e.g. Sauvola or Niblack)
would be the next logical approach, as it does not depend on the global
histogram having a meaningful spread.

---

## Role of TouchDesigner MCP Tool Calls

The TD MCP interface was central to building and debugging the pipeline
interactively. Key moments where MCP calls were particularly relevant:

- **`create_operator` / `connect_operators`** — Used to build the full image
  processing chain (`moviefilein1 → level1 → threshold1 → analyze1`) entirely
  through the API without touching the TD UI. The chain was rebuilt from scratch
  after a TD crash caused by a blocking ffmpeg pipe inside the HTTP handler.

- **`execute_script`** — Drove the iterative threshold optimiser interactively,
  running the binary search loop and reading back proportion values from the
  `analyze1` TOP. This exposed the critical bug: **TD's `moviefilein` TOP is
  asynchronous**; setting `par.index` and calling `cook(force=True)` does not
  guarantee the new frame is decoded before the downstream read. This meant
  all proportion measurements inside the TD operator chain returned stale cached
  values, making the in-TD optimiser unreliable. **The entire computation was
  moved to an ffmpeg pipe + numpy approach as a direct result of diagnosing
  this via `execute_script` and `take_screenshot`.**

- **`get_errors`** — Run after every state-changing MCP call per the established
  workflow rule. Caught the timer `callbacks` DAT broken-reference error
  immediately after the `timer2_callbacks` DAT was deleted.

- **`get_par_value` / `set_par_value`** — Used to read the live `level1` and
  `threshold1` operator parameters and inject them as labelled metadata into
  the batch output images, ensuring the thumbnails are self-documenting
  regardless of which parameter state was active at run time.

- **`take_screenshot` / `TOP.save()`** — Used to diagnose the cook-chain caching
  issue: both the `threshold1` output at threshold=0.9 and at threshold=0.1
  saved as identical all-white images, which confirmed that the in-TD pipeline
  was not re-cooking between script iterations.

---

## Operator Parameter Adjustment Table

Parameters on the core processing operators, tracked across the full session.
"Via MCP" = adjusted through `execute_script` or `set_par_value` tool calls.
"Programmatic" = adjusted inside Python scripts executed by or launched from MCP.

| Operator | Parameter | MCP Adjustments | Programmatic | Notes |
|---|---|---|---|---|
| `threshold1` | `threshold` | 8 | ~1800 | 8 during interactive test; up to 15 iters × 106 images × 3 batch runs in workers |
| `threshold1` | `rgb` | 1 | 0 | Set to `luminance` during initial setup |
| `threshold1` | `comparator` | 1 | 0 | Set to `greater` during initial setup |
| `threshold1` | `soften` | 0 | 0 | Read only; passed to batch label |
| `analyze1` | `op` | 1 | 0 | Set to `average` |
| `analyze1` | `analyzechannel` | 1 | 0 | Set to `luminance` |
| `moviefilein1` | `play` | 5 | 3 | Paused for frame-seeking attempts |
| `moviefilein1` | `playmode` | 5 | 3 | Switched to `specify` for frame seeking |
| `moviefilein1` | `indexunit` | 4 | 3 | Set to `frames` |
| `moviefilein1` | `index` | ~20 | ~20 | Frame seeking debug; ultimately abandoned |
| `moviefilein1` | `file` | 4 | 2 | Different test videos and PNG loads |
| `level1` | `brightness1` | 0 | 0 | Read only; passed to batch label and worker |
| `level1` | `contrast` | 0 | 0 | Read only |
| `level1` | `gamma1` | 0 | 0 | Read only |
| `level1` | `blacklevel` | 0 | 0 | Read only |
| `level1` | `invert` | 0 | 0 | Read only |
| `moviefilein_minprop` | `file` | 4 | 2 | Updated from `/tmp` path to persistent project path |
| `moviefilein_minprop` | `playmode` | 3 | 0 | Tried `specify` then switched to `locked` |
| `moviefilein_minprop` | `index` | 3 | 0 | Set to min-proportion frame; abandoned for PNG approach |
| `moviefilein_maxprop` | `file` | 4 | 2 | Same as minprop |
| `moviefilein_maxprop` | `playmode` | 3 | 0 | Same as minprop |
| `moviefilein_maxprop` | `index` | 3 | 0 | Same as minprop |
| `moviefileout1` | `record` | 2 | 4 | Export control; moved to background worker |
| `moviefileout1` | `type` | 1 | 1 | Set to `movie` |
| `timer2` | `length` | 1 | 0 | 5 second period |
| `timer2` | `cycle` | 1 | 0 | Enabled for repeat |
| `timer2` | `lengthunits` | 1 | 0 | Set to `seconds` |
| `timer2` | `active` | 1 | 0 | Enabled |
| `chopexec_watcher` | `chop` | 1 | 0 | Pointed at timer2 |
| `chopexec_watcher` | `channel` | 1 | 0 | Set to `done` |
| `chopexec_watcher` | `offtoon` | 1 | 0 | Trigger on rising edge |
| `video_processor` | `opviewer` | 1 | 0 | Set to `./overview_display` for container viewer |

**Total distinct parameters touched:** 31
**Total MCP-direct adjustments:** ~83
**Total programmatic adjustments (scripts):** ~1860 (dominated by threshold binary search across 3 batch runs)

---

## Key Finding

Histogram equalization is the most effective pre-processing step for guaranteeing
threshold convergence across a diverse image set. However it trades diagnostic
value (threshold no longer reflects image content) for convergence reliability.
For workflows where the threshold value must remain meaningful, the raw approach
with explicit handling of non-converging cases (e.g. reporting achievable range,
using adaptive thresholding as fallback) is preferred.
