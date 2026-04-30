import json
import os

LAYOUT_JSON = r'C:\Users\nik\Documents\AI\MCP\Rhino_MCP\apc40mk2_layout.json'
OUTPUT_HTML  = r'C:\Users\nik\Documents\AI\TD MCP\apc40_monitor.html'
CW, CH = 1200, 700


def el_to_svg(el):
    cx = el['norm_x'] * CW
    cy = el['norm_y'] * CH
    eid = el['id']
    etype = el['type']
    sub = el.get('subtype', '')

    if etype == 'pad':
        w, h, rx = 58, 58, 6
    elif etype == 'button':
        w, h, rx = 44, 20, 3
    elif etype == 'knob':
        return (f'<circle data-id="{eid}" class="apc-el"'
                f' cx="{cx:.1f}" cy="{cy:.1f}" r="17"/>')
    elif etype == 'fader':
        if sub == 'horizontal':
            w, h, rx = 78, 12, 3
        else:
            w, h, rx = 10, 52, 3
    else:
        return ''

    x, y = cx - w / 2, cy - h / 2
    return (f'<rect data-id="{eid}" class="apc-el"'
            f' x="{x:.1f}" y="{y:.1f}" width="{w}" height="{h}" rx="{rx}"/>')


with open(LAYOUT_JSON, encoding='utf-8') as f:
    data = json.load(f)

svg_els = '\n'.join(el_to_svg(e) for e in data['elements'])
layout_json = json.dumps(data['elements'], separators=(',', ':'))

html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#1a1a1a; overflow:hidden; }}
  svg {{ display:block; }}
  .apc-el {{ fill:#28D25A; }}
</style>
</head>
<body>
<svg width="{CW}" height="{CH}" viewBox="0 0 {CW} {CH}">
{svg_els}
</svg>
<script>
const LAYOUT={layout_json};
const elMap={{}};
document.querySelectorAll('[data-id]').forEach(e=>elMap[e.dataset.id]=e);

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
    s.style.fill='#FFFFFF';
    s.getBoundingClientRect();
    s.style.transition='fill 800ms ease-out';
    s.style.fill='#28D25A';
  }});
}}
</script>
</body>
</html>"""

with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'Written {len(data["elements"])} elements to {OUTPUT_HTML}')
