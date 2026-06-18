# Verification Discipline for Visual Output

The model has a recurring failure mode: claiming visual output is correct without verifying it. Several corrections happened because the model either didn't look at its own output or looked but didn't notice obvious errors (tiles in wrong positions, wrong colors, beige/empty tiles indicating render failures).

## Before claiming visual output is correct

### 1. Take a screenshot
```python
take_screenshot('/project1/out1')
```
Or whatever TOP represents the rendered output. Never claim "the tiles look correct" from code inspection alone.

### 2. Check for these failure signatures
- **Uniform color regions** (solid beige, black, white) — usually an empty input or failed render pass
- **Hard edges where blending should occur** — border composite didn't run or ran with wrong parameters
- **Tiles in wrong grid positions** — layout indexing is off by one row/column
- **Repeated identical content across tiles** — same input fed to multiple tiles
- **Visible operator wires / network artifacts** — wrong TOP is connected to the output

### 3. Check multiple areas of the output
Don't just glance at the center. The most common failures (border blending, edge tiles, corner artifacts) happen at the edges and corners of the frame.

### 4. When output is wrong, say so immediately
Don't soften it. "The tiles are misplaced — right two columns are on the left" is what the user needs to hear. "The output appears to have some minor positioning variances" is not.

### 5. For multi-pass pipelines, verify each pass
If a pipeline has passes 1 through N, screenshot each pass's intermediate output. The user asked for this explicitly (prompt 24: "for each test, I want dailies of input → output of each diffusion pass with annotations"). Cumulative errors are easier to trace when intermediate outputs are captured.

## The pattern this replaces

Three corrections in the stream diffusion session alone:
- Prompt 25: "tiles are clearly misplaced in output. right two columns are on the left"
- Prompt 26: same layout bug + "beige tiles in the top — are there failures in rendering?"
- Prompt 34: "the dailies are not putting post diffusion tiles in the right place"
- Prompt 36: "I'm sorry but there is clearly orange background tiles with wires that should be elsewhere you are wrong"

Each time, the model had presented output as correct or nearly correct. Screenshots + systematic checking would have caught these before the user did.

## Screenshot annotation conventions

When presenting a screenshot for the user to review:
- Name the file descriptively: `pass2_tile_2_3_output.png` not `screenshot_12345.png`
- State what pipeline stage it represents
- Point out anything you're uncertain about before the user has to spot it
