import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rebuild_plan import sanitize, is_numeric, channel_name, build_plan


class TestHelpers(unittest.TestCase):
    def test_sanitize(self):
        self.assertEqual(sanitize("Noise 1!"), "noise_1")
        self.assertEqual(sanitize("dQw4w9WgXcQ"), "dqw4w9wgxcq")

    def test_is_numeric(self):
        self.assertTrue(is_numeric("4.5"))
        self.assertTrue(is_numeric(3))
        self.assertTrue(is_numeric(True))
        self.assertTrue(is_numeric(" 0.5 "))
        self.assertFalse(is_numeric("sparse"))
        self.assertFalse(is_numeric("op('ramp1')"))

    def test_is_numeric_rejects_non_finite(self):
        self.assertFalse(is_numeric("nan"))
        self.assertFalse(is_numeric("inf"))
        self.assertFalse(is_numeric("Infinity"))
        self.assertFalse(is_numeric(float("nan")))

    def test_channel_name_prefix_and_cap(self):
        taken = set()
        name = channel_name("x" * 80, "op", "par", taken)
        self.assertTrue(name.startswith("tut_"))
        self.assertLessEqual(len(name), 60)

    def test_channel_collision_gets_suffix(self):
        taken = set()
        a = channel_name("vid", "noise1", "period", taken)
        b = channel_name("vid", "noise1", "period", taken)
        self.assertEqual(a, "tut_vid_noise1_period")
        self.assertNotEqual(a, b)
        self.assertTrue(b.endswith("_2"))


class TestBuildPlan(unittest.TestCase):
    def test_numeric_vs_string_split(self):
        graph = {"ops": [{"id": "noise1", "opType": "noiseTOP",
                          "params": {"period": {"value": "4"},
                                     "type": {"value": "sparse"}}}],
                 "wires": []}
        plan = build_plan(graph, "abc123")
        self.assertEqual(plan["container"], "tutorial_abc123")
        self.assertEqual(plan["bus"], "/project1/master_controls")
        self.assertEqual(len(plan["channels"]), 1)
        self.assertEqual(plan["channels"][0]["value"], 4.0)
        self.assertEqual(plan["channelParams"][0]["expr"],
                         "op('/project1/master_controls')"
                         "['tut_abc123_noise1_period']")
        self.assertEqual(len(plan["directParams"]), 1)
        self.assertEqual(plan["directParams"][0]["value"], "sparse")
        self.assertEqual(plan["blockers"], [])

    def test_layout_follows_wire_depth(self):
        graph = {"ops": [{"id": "b", "opType": "levelTOP", "params": {}},
                         {"id": "a", "opType": "noiseTOP", "params": {}}],
                 "wires": [{"from": "a", "to": "b", "toInlet": 0}]}
        plan = build_plan(graph, "v")
        xs = {c["name"]: c["nodeX"] for c in plan["creates"]}
        self.assertLess(xs["a"], xs["b"])
        self.assertEqual(plan["wires"],
                         [{"from": "a", "to": "b", "toInlet": 0}])
        self.assertEqual(plan["opTypes"], ["levelTOP", "noiseTOP"])

    def test_blockers_for_empty_optype_and_conflicts(self):
        graph = {"ops": [{"id": "noise1", "opType": "noiseTOP", "params": {}},
                         {"id": "bad1", "opType": "", "params": {}}],
                 "wires": [],
                 "conflicts": [{"kind": "duplicate", "detail": "op bad1 dup"}]}
        plan = build_plan(graph, "abc")
        self.assertEqual(plan["blockers"],
                         [{"kind": "empty-optype", "op": "bad1"},
                          {"kind": "unresolved-conflict",
                           "detail": "op bad1 dup"}])
        self.assertEqual(plan["opTypes"], ["noiseTOP"])


if __name__ == "__main__":
    unittest.main()


class TestParamRefsPassthrough(unittest.TestCase):
    def test_param_refs_copied_into_plan(self):
        graph = {"ops": [{"id": "a", "opType": "lfoCHOP", "params": {}},
                         {"id": "b", "opType": "noiseTOP", "params": {}}],
                 "wires": [],
                 "paramRefs": [{"from": "a", "to": "b", "sources": ["c1"]}]}
        plan = build_plan(graph, "v")
        self.assertEqual(plan["paramRefs"], [{"from": "a", "to": "b"}])
        self.assertEqual(plan["wires"], [])
