# APC40 MK2 MIDI Monitor — Design Spec

**Date:** 2026-04-30  
**Status:** Approved

---

## Goal

A self-contained TouchDesigner baseCOMP (`apc40_monitor`) in `/project1` that renders the full APC40 MK2 button layout and lights up each element when its corresponding MIDI event fires. Used to verify that physical button presses match the expected layout positions.

---

## Component Structure

Location: `/project1/apc40_monitor`

```
apc40_monitor/
  midiin        MIDI In CHOP — device 1, all channels, notes + CCs
  midi_watch    Script CHOP  — cooks every frame, detects MIDI events, calls executeJavaScript
  layout_html   Text DAT     — self-contained HTML page (JSON embedded inline)
  webrender     WebRender TOP — sourced from layout_html (DAT: protocol), 1200×700
  null_out      Null TOP      — viewer output
```

The baseCOMP viewer is set to `webrender` via `par.opviewer`.

---

## MIDI In

- Operator: `midiin` (MIDI In CHOP)
- Device: MIDI device 1
- Channels: all
- Message types: notes on/off + CC

---

## MIDI Routing (midi_watch Script CHOP)

Cooks every frame. On each cook:

1. Read all channels from `op('midiin')`
2. Detect rising edges: note velocity > 0, or CC value change
3. For each event, call:
   ```python
   op('webrender').executeJavaScript(
       f"hit('{midi_type}', {channel}, {note_or_cc}, {value})"
   )
   ```

`midi_type` is `'note'` or `'cc'`.

---

## Hit Detection (JavaScript)

The `hit(type, channel, noteOrCC, value)` function:

1. Searches the embedded layout array for elements where:
   - `el.midi_type === type`
   - `el.note === noteOrCC` (for notes) or `el.cc === noteOrCC` (for CCs)
   - If `el.channel_mode === 'per_track'`: match `el.grid_col === channel` (channels 0–7 = tracks 1–8)
   - If `el.channel_mode === 'ignored'`: match on note/CC alone
2. Finds the SVG element with `data-id` matching `el.id`
3. Adds CSS class `active` → fill transitions to white
4. Removes `active` after 800ms → fill transitions back to green

---

## HTML/SVG Renderer

Stored inline in `layout_html` Text DAT. No external files or network requests.

**Canvas:** 1200×700px SVG

**Element shapes** (sized relative to canvas):

| Type | Shape | Approx size |
|------|-------|-------------|
| pad (clip_grid, scene_launch) | rounded rect | 60×60px |
| button (track_strip, transport, mode, device_nav) | rounded rect | 45×22px |
| knob | circle | r=18px |
| fader vertical | rect | 12×55px |
| fader horizontal (crossfader) | rect | 80×14px |

**Positioning:** `norm_x * 1200`, `norm_y * 700` = center of each element.

**Colors:**

| State | Fill |
|-------|------|
| Rest | `#28D25A` (green) |
| Active (hit) | `#FFFFFF` (white) |

Transition: CSS `transition: fill 800ms ease-out` on all SVG elements.

**Background:** `#1a1a1a` (near-black) so green elements read clearly.

---

## Spec Self-Review

- No TBDs or placeholders
- Architecture and feature descriptions are consistent
- Scope is a single buildable component
- All requirements have one clear interpretation

---

## Files

- Layout JSON: `C:\Users\nik\Documents\AI\MCP\Rhino_MCP\apc40mk2_layout.json`
- Spec: `docs/superpowers/specs/2026-04-30-apc40-monitor-design.md`
