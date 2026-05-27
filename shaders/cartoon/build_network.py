"""
Build cartoon_fx baseCOMP in /project1.
Shader files must exist in SHADER_DIR.
All shaders use procedural noise/paper — max 3 TOP inputs per GLSL TOP.
"""
import os

PARENT_PATH = '/project1'
COMP_NAME   = 'cartoon_fx'
SHADER_DIR  = r'C:\Users\nik\Documents\AI\MCP\TD MCP\shaders\cartoon'

def read(name):
    with open(os.path.join(SHADER_DIR, name)) as f:
        return f.read()

# ── Tear down existing ────────────────────────────────────────────────────────
for e in op(PARENT_PATH).findChildren(name=COMP_NAME, maxDepth=1):
    e.destroy()

base = op(PARENT_PATH).create(containerCOMP, COMP_NAME)
base.nodeX, base.nodeY = 0, 0

# ── Source operators ──────────────────────────────────────────────────────────
in_color  = base.create(inTOP, 'in_color')
in_normal = base.create(inTOP, 'in_normal')
in_color.nodeX,  in_color.nodeY  = -600, 200
in_normal.nodeX, in_normal.nodeY = -600, 0
in_color.par.connectorder  = 0
in_normal.par.connectorder = 1

# ── CMYK decompose pre-pass ───────────────────────────────────────────────────
code_cmyk = base.create(textDAT, 'code_cmyk')
code_cmyk.text = read('cmyk_decompose.glsl')
code_cmyk.nodeX, code_cmyk.nodeY = -400, 200

glsl_cmyk = base.create(glslTOP, 'glsl_cmyk')
glsl_cmyk.par.pixeldat = code_cmyk.name
glsl_cmyk.nodeX, glsl_cmyk.nodeY = -200, 200
glsl_cmyk.setInputs([in_color])

# ── GLSL cartoon shaders ──────────────────────────────────────────────────────
def make_glsl(code_name, inputs_list, nx, ny):
    dat = base.create(textDAT, 'code_' + code_name)
    dat.text = read(code_name + '.glsl')
    dat.nodeX, dat.nodeY = nx, ny + 120

    g = base.create(glslTOP, 'glsl_' + code_name)
    g.par.pixeldat = dat.name
    g.nodeX, g.nodeY = nx, ny
    g.setInputs(inputs_list)
    return g

# i/iii/vi: 2 inputs  |  ii/iv/v: 3 inputs
glsl_i   = make_glsl('cartoon_i',   [in_color, in_normal],              0,   400)
glsl_ii  = make_glsl('cartoon_ii',  [in_color, in_normal, glsl_cmyk],   220, 400)
glsl_iii = make_glsl('cartoon_iii', [in_color, in_normal],              440, 400)
glsl_iv  = make_glsl('cartoon_iv',  [in_color, in_normal, glsl_cmyk],   660, 400)
glsl_v   = make_glsl('cartoon_v',   [in_color, in_normal, glsl_cmyk],   880, 400)
glsl_vi  = make_glsl('cartoon_vi',  [in_color, in_normal],              1100, 400)

# ── Switch TOP ────────────────────────────────────────────────────────────────
sw = base.create(switchTOP, 'switch_out')
sw.nodeX, sw.nodeY = 500, 0
for i, src in enumerate([glsl_i, glsl_ii, glsl_iii, glsl_iv, glsl_v, glsl_vi]):
    sw.inputConnectors[i].connect(src)
sw.par.index.expr = "parent().par.Shader"

# ── Output ────────────────────────────────────────────────────────────────────
out_op = base.create(outTOP, 'out1')
out_op.nodeX, out_op.nodeY = 700, 0
out_op.inputConnectors[0].connect(sw)

# ── Custom parameters ─────────────────────────────────────────────────────────
page = base.appendCustomPage('Cartoon FX')

page.appendMenu('Shader', label='Shader')
base.par.Shader.menuNames  = ['0','1','2','3','4','5']
base.par.Shader.menuLabels = ['I – Hatching','II – CMYK','III – Lines+Dots',
                               'IV – Full CMYK','V – Full CMYK B','VI – Cel+Dots']
base.par.Shader.val = '0'

page.appendRGB('Inkcolor', label='Ink Color')
base.par.Inkcolorr.val = 0.0; base.par.Inkcolorg.val = 0.0; base.par.Inkcolorb.val = 0.0

def fp(name, label, lo, hi, default):
    page.appendFloat(name, label=label)
    p = getattr(base.par, name)
    p.normMin = lo; p.normMax = hi; p.default = default; p.val = default

fp('Scale',     'Scale',     0.1, 5.0,   1.0)
fp('Thickness', 'Thickness', 0.1, 10.0,  1.0)
fp('Noisiness', 'Noisiness', 0.0, 1.0,   0.5)
fp('Angle',     'Angle',     0.0, 6.283, 0.0)
fp('Contour',   'Contour',   0.5, 10.0,  3.0)
fp('Border',    'Border',    0.0, 2.0,   1.0)
fp('Boost',     'Edge Boost',0.5, 3.0,   1.0)
fp('Dark',      'Dark Thresh',0.0,1.0,   0.4)
fp('Mid',       'Mid Thresh', 0.0,1.0,   0.7)
fp('Light',     'Light Thresh',0.0,1.0,  0.7)

page.appendRGB('Darkink',   label='Dark Ink')
base.par.Darkinkr.val=0.; base.par.Darkinkg.val=0.; base.par.Darkinkb.val=0.
page.appendRGB('Brightink', label='Bright Ink')
base.par.Brightinkr.val=1.; base.par.Brightinkg.val=1.; base.par.Brightinkb.val=1.

fp('Fill',            'Fill',           0.0, 1.0, 1.0)
fp('Stroke',          'Stroke',         0.0, 1.0, 1.0)
fp('Darkintensity',   'Dark Intensity', 0.0, 1.0, 0.3)
fp('Brightintensity', 'Bright Intensity',0.0,1.0, 0.3)
fp('Levels',          'Levels',         1.0,20.0, 5.0)
fp('Minluma',         'Min Luma',       0.0, 1.0, 0.0)
fp('Maxluma',         'Max Luma',       0.0, 1.0, 1.0)
fp('Minlight',        'Min Light',      0.0, 0.5, 0.05)
fp('Lightboost',      'Light Boost',    0.0, 3.0, 1.0)
fp('Explight',        'Exp Light',      0.0, 1.0, 0.1)

# ── Uniform updater (runs every frame) ────────────────────────────────────────
exec_dat = base.create(executeDAT, 'exec_uniforms')
exec_dat.nodeX, exec_dat.nodeY = -200, -300
exec_dat.par.framestart = True
exec_dat.par.active = True
exec_dat.text = r"""
def frameStart(frame):
    p   = me.parent()
    ink = [p.par.Inkcolorr.val, p.par.Inkcolorg.val, p.par.Inkcolorb.val]
    sc  = p.par.Scale.val;      th  = p.par.Thickness.val
    noi = p.par.Noisiness.val;  ang = p.par.Angle.val
    con = p.par.Contour.val;    brd = p.par.Border.val

    def u(name, **kw):
        g = op(name)
        if g is None: return
        for k, v in kw.items(): g.setUniform(k, v)

    u('glsl_cartoon_i',   inkColor=ink, scale=sc, thickness=th, noisiness=noi, angle=ang)
    u('glsl_cartoon_ii',  inkColor=ink, scale=sc, thickness=th, noisiness=noi, angle=ang,
                          contour=con, border=brd)
    u('glsl_cartoon_iii', inkColor=ink, scale=sc, thickness=th, contour=con,
                          boost=p.par.Boost.val, dark=p.par.Dark.val,
                          mid=p.par.Mid.val, light=p.par.Light.val)
    dink = [p.par.Darkinkr.val, p.par.Darkinkg.val, p.par.Darkinkb.val]
    bink = [p.par.Brightinkr.val, p.par.Brightinkg.val, p.par.Brightinkb.val]
    for name in ('glsl_cartoon_iv', 'glsl_cartoon_v'):
        u(name, darkInk=dink, brightInk=bink, scale=sc, thickness=th,
          noisiness=noi, angle=ang, contour=con, border=brd,
          fill=p.par.Fill.val, stroke=p.par.Stroke.val,
          darkIntensity=p.par.Darkintensity.val,
          brightIntensity=p.par.Brightintensity.val)
    u('glsl_cartoon_vi', inkColor=ink, scale=sc, levels=p.par.Levels.val,
      thickness=th, contour=con, minLuma=p.par.Minluma.val,
      maxLuma=p.par.Maxluma.val, minLight=p.par.Minlight.val,
      lightBoost=p.par.Lightboost.val, expLight=p.par.Explight.val)
"""

print('[cartoon_fx] built at', base.path)
print('[cartoon_fx] Input 0 = color TOP, Input 1 = normal TOP')
