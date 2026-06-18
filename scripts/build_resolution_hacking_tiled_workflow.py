"""TouchDesigner Textport script for /project1/resolution_hacking.

Run inside TouchDesigner if the MCP bridge is unavailable. It expects
out/resolution_tiles/manifest.json to already exist.
"""

import json

root = op('/project1/resolution_hacking')
manifest_path = r'C:/Users/nik/Documents/AI/MCP/TD MCP/out/resolution_tiles/manifest.json'

with open(manifest_path, 'r') as f:
    manifest = json.load(f)

for name in ['display_tiles', 'window_tiles_second_display', 'tile_manifest', 'workflow_notes']:
    existing = root.op(name)
    if existing:
        existing.destroy()

for child in list(root.children):
    if child.name.startswith('tile_chain_'):
        child.destroy()


def set_par(o, name, value):
    p = getattr(o.par, name, None)
    if p is None:
        return
    try:
        p.val = value
    except Exception:
        pass


def pulse(o, name):
    p = getattr(o.par, name, None)
    if p is None:
        return
    try:
        p.pulse()
    except Exception:
        pass


source_w = int(manifest['source_width'])
source_h = int(manifest['source_height'])

root.par.w = source_w
root.par.h = source_h
root.par.align = 'none'
root.viewer = True

table = root.create(tableDAT, 'tile_manifest')
table.nodeX = -700
table.nodeY = 150
table.clear()
table.appendRow(['col', 'row', 'x', 'y_top', 'panel_x', 'panel_y', 'w', 'h', 'file', 'chain', 'out_top'])

display = root.create(containerCOMP, 'display_tiles')
display.nodeX = 650
display.nodeY = 0
set_par(display, 'w', source_w)
set_par(display, 'h', source_h)
set_par(display, 'align', 'none')
set_par(display, 'bgcolorr', 0)
set_par(display, 'bgcolorg', 0)
set_par(display, 'bgcolorb', 0)
set_par(display, 'bgalpha', 1)
display.viewer = True

for tile in manifest['tiles']:
    col = int(tile['col'])
    row = int(tile['row'])
    w = int(tile['w'])
    h = int(tile['h'])
    x = int(tile['x'])
    y_top = int(tile['y'])
    panel_y = source_h - y_top - h

    chain = root.create(baseCOMP, 'tile_chain_%d_%d' % (col, row))
    chain.nodeX = -250 + col * 260
    chain.nodeY = -row * 220

    movie = chain.create(moviefileinTOP, 'movie_in')
    movie.nodeX = 0
    movie.nodeY = 0
    set_par(movie, 'file', tile['file'])
    set_par(movie, 'playmode', 'sequential')
    set_par(movie, 'play', False)
    set_par(movie, 'cue', True)
    set_par(movie, 'cuepoint', 0)
    set_par(movie, 'outputresolution', 'useinput')
    set_par(movie, 'outputaspect', 'resolution')
    set_par(movie, 'filtertype', 'nearest')
    set_par(movie, 'inputfiltertype', 'nearest')
    pulse(movie, 'reloadpulse')

    level = chain.create(levelTOP, 'process_level_identical')
    level.nodeX = 180
    level.nodeY = 0
    level.inputConnectors[0].connect(movie)
    set_par(level, 'opacity', 1)

    out = chain.create(nullTOP, 'null_tile_out')
    out.nodeX = 360
    out.nodeY = 0
    out.inputConnectors[0].connect(level)

    panel = display.create(containerCOMP, 'panel_%d_%d' % (col, row))
    panel.nodeX = col * 180
    panel.nodeY = -row * 160
    set_par(panel, 'x', x)
    set_par(panel, 'y', panel_y)
    set_par(panel, 'w', w)
    set_par(panel, 'h', h)
    set_par(panel, 'align', 'none')
    set_par(panel, 'bgcolorr', 0)
    set_par(panel, 'bgcolorg', 0)
    set_par(panel, 'bgcolorb', 0)
    set_par(panel, 'bgalpha', 0)
    set_par(panel, 'top', out.path)
    set_par(panel, 'topfill', 'off')
    set_par(panel, 'topsmoothness', 'nearest')
    panel.viewer = True

    table.appendRow([col, row, x, y_top, x, panel_y, w, h, tile['file'], chain.path, out.path])

window = root.create(windowCOMP, 'window_tiles_second_display')
window.nodeX = 650
window.nodeY = -220
set_par(window, 'winop', display.path)
set_par(window, 'display', 1)
set_par(window, 'justifyh', 'left')
set_par(window, 'justifyv', 'bottom')
set_par(window, 'winoffsetx', 0)
set_par(window, 'winoffsety', 0)
set_par(window, 'borders', False)
set_par(window, 'alwaysontop', True)
set_par(window, 'interact', False)
set_par(window, 'cursorvisible', 'cursoronmove')
set_par(window, 'size', 'custom')
set_par(window, 'winw', source_w)
set_par(window, 'winh', source_h)

notes = root.create(textDAT, 'workflow_notes')
notes.nodeX = -700
notes.nodeY = -100
notes.text = '''Resolution cap workaround sample

Original oversized input kept as: /project1/resolution_hacking/moviefilein1
That operator demonstrates the Non-Commercial 1280x1280 cap.

Working path:
1. Source image is pre-tiled on disk into out/resolution_tiles/.
2. Each tile is <=1280 in both dimensions.
3. Each tile_chain_* loads one tile with its own Movie File In TOP.
4. All tile chains contain the same neutral process node: process_level_identical.
5. /project1/resolution_hacking/display_tiles places tile panels at original pixel coordinates.
6. /project1/resolution_hacking/window_tiles_second_display targets display 1 but is not opened automatically.

For animated sources, generate matching tile movie files and drive every movie_in index from one shared master clock expression.'''

print('built tiled workflow: %d cols x %d rows, %d tiles' % (manifest['cols'], manifest['rows'], len(manifest['tiles'])))
