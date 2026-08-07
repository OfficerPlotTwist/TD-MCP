import base64
import os
import sys
import zlib

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "webapp"))
import protocol


def test_validate_rules_ok():
    rules = [
        {"type": "wand", "color": [1.0, 0.0, 0.25], "tol": 0.1},
        {"type": "bycolor", "color": [0, 0.5, 1], "tol": 0.3},
    ]
    out = protocol.validate_rules(rules)
    assert out == [(0, 1.0, 0.0, 0.25, 0.1), (1, 0.0, 0.5, 1.0, 0.3)]


def test_validate_rules_empty_ok():
    assert protocol.validate_rules([]) == []


@pytest.mark.parametrize("bad", [
    "not a list",
    [{"type": "lasso", "color": [0, 0, 0], "tol": 0.1}],
    [{"type": "wand", "color": [0, 0], "tol": 0.1}],
    [{"type": "wand", "color": [0, 0, 2.0], "tol": 0.1}],
    [{"type": "wand", "color": [0, 0, 0], "tol": -0.1}],
    [{"type": "wand", "color": [0, 0, 0], "tol": 3.0}],
])
def test_validate_rules_rejects(bad):
    with pytest.raises(ValueError):
        protocol.validate_rules(bad)


def test_validate_rules_cap():
    rules = [{"type": "wand", "color": [0, 0, 0], "tol": 0.1}] * 33
    with pytest.raises(ValueError):
        protocol.validate_rules(rules)


def test_stencil_roundtrip():
    raw = bytes(range(256)) * 16          # 4096 bytes, all values
    b64 = protocol.encode_stencil(raw)
    assert protocol.decode_stencil(b64) == raw
    # it really is zlib+base64, not passthrough
    assert zlib.decompress(base64.b64decode(b64)) == raw


def test_build_send_script_contents():
    rules = protocol.validate_rules(
        [{"type": "bycolor", "color": [1, 0, 0], "tol": 0.2}])
    b64 = protocol.encode_stencil(bytes(64 * 64))
    script = protocol.build_send_script(rules, 64, 64, b64)
    assert "colormask_rules" in script
    assert "colormask_stencil" in script
    assert "(1, 1.0, 0.0, 0.0, 0.2)" in script
    assert "np.flipud" in script
    assert "script_stencil').cook(force=True)" in script
    assert "script_rules').cook(force=True)" in script
    assert b64 in script


def test_build_send_script_empty_rules():
    script = protocol.build_send_script([], 1, 1, protocol.encode_stencil(b"\x00"))
    assert "colormask_rules', [])" in script
