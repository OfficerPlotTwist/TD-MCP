"""Pure logic for the colormask webapp: rule validation, stencil codec,
and the TD-side SEND script builder. No I/O, no TD imports — testable anywhere."""
import base64
import zlib

MAX_RULES = 32
RULE_TYPES = ("wand", "bycolor")

CONTAINER = "/project1/cont_colormask"


def validate_rules(rules):
    """Normalize webapp rule dicts to (type_int, r, g, b, tol) tuples.

    type_int: 0 = wand (stencil-gated), 1 = bycolor (frame-wide).
    Colors and tol are normalized floats. Raises ValueError on any problem.
    """
    if not isinstance(rules, list):
        raise ValueError("rules must be a list")
    if len(rules) > MAX_RULES:
        raise ValueError(f"too many rules: {len(rules)} > {MAX_RULES}")
    out = []
    for i, r in enumerate(rules):
        if not isinstance(r, dict):
            raise ValueError(f"rule {i}: must be an object")
        t = r.get("type")
        if t not in RULE_TYPES:
            raise ValueError(f"rule {i}: bad type {t!r}")
        color = r.get("color")
        if (not isinstance(color, (list, tuple)) or len(color) != 3
                or not all(isinstance(c, (int, float)) and 0.0 <= c <= 1.0
                           for c in color)):
            raise ValueError(f"rule {i}: color must be 3 floats in 0..1")
        tol = r.get("tol")
        if not isinstance(tol, (int, float)) or not 0.0 <= tol <= 2.0:
            raise ValueError(f"rule {i}: tol must be a float in 0..2")
        out.append((1 if t == "bycolor" else 0,
                    float(color[0]), float(color[1]), float(color[2]),
                    float(tol)))
    return out


def encode_stencil(raw):
    """bytes -> base64(zlib(bytes)) str, for embedding in the SEND script."""
    return base64.b64encode(zlib.compress(raw)).decode("ascii")


def decode_stencil(b64):
    """Inverse of encode_stencil (used by tests and debugging)."""
    return zlib.decompress(base64.b64decode(b64))


_SEND_TEMPLATE = """\
import base64, zlib
import numpy as np
c = op('{container}')
w, h = {w}, {h}
raw = zlib.decompress(base64.b64decode('{b64}'))
arr = np.flipud(np.frombuffer(raw, dtype=np.uint8).reshape(h, w)).copy()
c.store('colormask_stencil', {{'w': w, 'h': h, 'data': arr}})
c.store('colormask_rules', {rules!r})
op('{container}/script_stencil').cook(force=True)
op('{container}/script_rules').cook(force=True)
print('OK rules={n} stencil=%dx%d' % (w, h))
"""


def build_send_script(rules, w, h, stencil_b64):
    """Build the flat TD-side script that atomically stores stencil + rules
    then force-cooks the two Script TOPs. `rules` is validate_rules() output."""
    return _SEND_TEMPLATE.format(container=CONTAINER, w=w, h=h,
                                 b64=stencil_b64, rules=list(rules),
                                 n=len(rules))
