"""
gen_apc40_html.py
Builds apc40_monitor.html by:
  1. Parsing the vector SVG layout
  2. Matching each SVG shape to a JSON MIDI element by nearest-centre proximity
  3. Injecting data-id attributes and green fill
  4. Wrapping in HTML with hit() JS for MIDI-driven white flash
"""

import json
import xml.etree.ElementTree as ET

LAYOUT_JSON = r'C:\Users\nik\Documents\AI\MCP\Rhino_MCP\apc40mk2_layout.json'
SVG_FILE    = r'C:\Users\nik\Documents\AI\MCP\Rhino_MCP\apc40mk2_layout.svg'
OUTPUT_HTML = r'C:\Users\nik\Documents\AI\MCP\TD MCP\apc40_monitor.html'

SVG_W, SVG_H = 1240, 973
SVG_NS = 'http://www.w3.org/2000/svg'

# ── 1. Parse SVG ──────────────────────────────────────────────────────────────

ET.register_namespace('', SVG_NS)
tree = ET.parse(SVG_FILE)
root = tree.getroot()

def strip_ns(tag):
    return tag.replace(f'{{{SVG_NS}}}', '')

svg_shapes = []  # (element_ref, uuid, cx, cy)

for elem in root:
    tag  = strip_ns(elem.tag)
    uuid = elem.get('id', '')
    if not uuid:
        continue

    if tag == 'circle':
        cx = float(elem.get('cx', 0))
        cy = float(elem.get('cy', 0))
        svg_shapes.append((elem, uuid, cx, cy))

    elif tag == 'polyline':
        raw = elem.get('points', '').strip()
        pairs = [p for p in raw.split() if ',' in p]
        if not pairs:
            continue
        xs = [float(p.split(',')[0]) for p in pairs]
        ys = [float(p.split(',')[1]) for p in pairs]
        w  = max(xs) - min(xs)
        h  = max(ys) - min(ys)
        if w > 1000 or h > 800:     # skip outer frame
            continue
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        svg_shapes.append((elem, uuid, cx, cy))

# Deduplicate by rounded centre (some shapes are exact duplicates in the SVG)
seen, unique_shapes = set(), []
for item in svg_shapes:
    key = (round(item[2], 1), round(item[3], 1))
    if key not in seen:
        seen.add(key)
        unique_shapes.append(item)

print(f'SVG shapes (deduplicated): {len(unique_shapes)}')

# ── 2. Parse JSON ─────────────────────────────────────────────────────────────

with open(LAYOUT_JSON, encoding='utf-8') as f:
    data = json.load(f)

elements = [e for e in data['elements'] if e['id'] != 'footswitch']  # footswitch is external

# ── 3. Greedy nearest-neighbour matching ─────────────────────────────────────
# Sort JSON elements by distance to their nearest SVG shape (most-constrained first)

def nearest(el, pool):
    ex, ey = el['norm_x'] * SVG_W, el['norm_y'] * SVG_H
    best_d, best_i = float('inf'), -1
    for i, (_, _, cx, cy) in enumerate(pool):
        d = (cx - ex)**2 + (cy - ey)**2
        if d < best_d:
            best_d, best_i = d, i
    return best_i, best_d ** 0.5

ranked = sorted(elements, key=lambda e: nearest(e, unique_shapes)[1])

remaining = list(unique_shapes)
mapping   = {}  # uuid -> json_id

for el in ranked:
    idx, dist = nearest(el, remaining)
    if idx < 0:
        print(f'  WARNING no SVG shapes left for {el["id"]}')
        continue
    if dist > 300:
        print(f'  INFO far match {el["id"]} dist={dist:.1f}')
    _, uuid, cx, cy = remaining[idx]
    mapping[uuid] = el['id']
    remaining.pop(idx)

print(f'Matched: {len(mapping)} / {len(elements)}')
if remaining:
    print(f'Unmatched SVG shapes: {len(remaining)}')

# ── 4. Annotate SVG elements ─────────────────────────────────────────────────

for elem, uuid, cx, cy in unique_shapes:
    if uuid in mapping:
        elem.set('data-id',  mapping[uuid])
        elem.set('class',    'apc-el')
        elem.set('fill',     '#000000')
        elem.set('stroke',   '#ffffff')
        elem.set('stroke-width', '1.2')
    else:
        elem.set('fill',     '#000000')
        elem.set('stroke',   '#333333')
        elem.set('stroke-width', '1.2')

# ── 5. Serialise modified SVG ────────────────────────────────────────────────

svg_str = ET.tostring(root, encoding='unicode')
# ET adds ns0: prefixes sometimes — strip them back
svg_str = svg_str.replace('ns0:', '').replace(':ns0', '')

# ── 6. Build HTML ─────────────────────────────────────────────────────────────

layout_json = json.dumps(data['elements'], separators=(',', ':'))

html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#1a1a1a; overflow:hidden; }}
  svg {{ display:block; width:100vw; height:100vh; }}
  .apc-el {{ cursor:default; }}
</style>
</head>
<body>
{svg_str}
<script>
const LAYOUT={layout_json};
const elMap={{}};
const uuidMap={{}};
document.querySelectorAll('[data-id]').forEach(e=>{{elMap[e.dataset.id]=e; uuidMap[e.id]=e;}});
document.querySelectorAll('[id]').forEach(e=>{{if(!uuidMap[e.id])uuidMap[e.id]=e;}});

function hit(type,channel,noteOrCC,value){{
  if(value===0)return;
  LAYOUT.filter(el=>{{
    if(el.midi_type!==type)return false;
    const key=type==='note'?el.note:el.cc;
    if(key===undefined||key!==noteOrCC)return false;
    if(el.channel_mode==='per_track')return el.grid_col===channel;
    return true;
  }}).forEach(el=>{{
    const s=elMap[el.id];
    if(!s)return;
    s.style.transition='none';
    s.style.fill='#28D25A';
    s.getBoundingClientRect();
    s.style.transition='fill 800ms ease-out';
    s.style.fill='#000000';
  }});
}}

// Poll TD for MIDI events
let _lastT=0;
setInterval(async ()=>{{
  try{{
    const r=await fetch('/midi');
    const d=await r.json();
    if(d.t && d.t!==_lastT){{
      _lastT=d.t;
      hit(d.type,d.channel,d.num,d.val);
    }}
  }}catch(e){{}}
}},50);

// Poll TD for calibration target (keep lit white)
let _curTarget=null;
setInterval(async ()=>{{
  try{{
    const r=await fetch('/target');
    const d=await r.json();
    if(d.id!==_curTarget){{
      const prev=elMap[_curTarget]||uuidMap[_curTarget];
      if(prev){{prev.style.transition='';prev.style.fill='#000000';}}
      _curTarget=d.id||null;
      const next=elMap[_curTarget]||uuidMap[_curTarget];
      if(next){{next.style.transition='none';next.style.fill='#FFFFFF';}}
    }}
  }}catch(e){{}}
}},100);
</script>
</body>
</html>"""

with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'Written to {OUTPUT_HTML}')
