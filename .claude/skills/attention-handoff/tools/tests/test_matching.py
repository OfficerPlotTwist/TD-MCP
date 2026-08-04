import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from matching import normalize, resolve_label, build_graph


class TestResolveLabel(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize("  Noise1 "), "noise1")

    def test_exact_match_case_insensitive(self):
        self.assertEqual(resolve_label("Noise1", ["noise1", "level1"]),
                         ("noise1", None))

    def test_unique_prefix_match(self):
        self.assertEqual(resolve_label("noi", ["noise1", "level1"]),
                         ("noise1", None))

    def test_ambiguous_prefix_is_conflict(self):
        name, conflict = resolve_label("no", ["noise1", "noise2"])
        self.assertIsNone(name)
        self.assertEqual(conflict["kind"], "ambiguous-name")
        self.assertIn("noise1", conflict["detail"])

    def test_no_match_returns_label_as_new_name(self):
        self.assertEqual(resolve_label("blur1", ["noise1"]), ("blur1", None))


def cap(cid, t, ctype="param", pair_id=None, role=None):
    return {"id": cid, "t": t, "type": ctype, "bbox": [0, 0, 10, 10],
            "file": "crops/%s.png" % cid, "pairId": pair_id, "role": role}


class TestBuildGraph(unittest.TestCase):
    def test_param_latest_wins_history_kept(self):
        captures = [cap("c1", 88.2), cap("c2", 214.6)]
        readings = {
            "c1": {"kind": "param", "opName": "noise1", "opType": "noiseTOP",
                   "params": {"period": "1"}},
            "c2": {"kind": "param", "opName": "noise1", "opType": "noiseTOP",
                   "params": {"period": "4"}},
        }
        g = build_graph(captures, readings)
        self.assertEqual(g["stats"]["opCount"], 1)
        slot = g["ops"][0]["params"]["period"]
        self.assertEqual(slot["value"], "4")
        self.assertEqual(slot["history"], [{"value": "1", "t": 88.2}])
        self.assertIn("param-changed", [c["kind"] for c in g["conflicts"]])

    def test_wire_union_dedupe_across_grabs(self):
        captures = [cap("c1", 10), cap("c2", 20),
                    cap("c3", 30, "network"), cap("c4", 40, "network")]
        readings = {
            "c1": {"kind": "param", "opName": "noise1", "opType": "noiseTOP",
                   "params": {}},
            "c2": {"kind": "param", "opName": "level1", "opType": "levelTOP",
                   "params": {}},
            "c3": {"kind": "network",
                   "nodes": [{"label": "noi"}, {"label": "lev"}],
                   "wires": [{"from": "noi", "to": "lev", "toInlet": 0}]},
            "c4": {"kind": "network",
                   "nodes": [{"label": "noise1"}, {"label": "level1"}],
                   "wires": [{"from": "noise1", "to": "level1", "toInlet": 0}]},
        }
        g = build_graph(captures, readings)
        self.assertEqual(g["stats"]["opCount"], 2)
        self.assertEqual(g["stats"]["wireCount"], 1)
        self.assertEqual(sorted(g["wires"][0]["sources"]), ["c3", "c4"])

    def test_pair_override_beats_ambiguous_prefix(self):
        captures = [cap("c1", 10), cap("c2", 20),
                    cap("c3", 30, "pair", "p1", "op"),
                    cap("c4", 31, "pair", "p1", "param"),
                    cap("c5", 40, "network")]
        readings = {
            "c1": {"kind": "param", "opName": "noise1", "opType": "noiseTOP",
                   "params": {}},
            "c2": {"kind": "param", "opName": "noise2", "opType": "noiseTOP",
                   "params": {}},
            "c3": {"kind": "opnode", "label": "no"},
            "c4": {"kind": "param", "opName": "noise2", "opType": "noiseTOP",
                   "params": {}},
            "c5": {"kind": "network", "nodes": [{"label": "no"}], "wires": []},
        }
        g = build_graph(captures, readings)
        # 'no' is ambiguous by prefix (noise1/noise2) but the pair pins it
        self.assertEqual(g["stats"]["opCount"], 2)
        self.assertEqual([c for c in g["conflicts"]
                          if c["kind"] == "ambiguous-name"], [])

    def test_unreadable_and_unknown_optype_conflicts(self):
        captures = [cap("c1", 10), cap("c2", 20, "network")]
        readings = {
            "c1": {"kind": "unreadable"},
            "c2": {"kind": "network", "nodes": [{"label": "mystery1"}],
                   "wires": []},
        }
        g = build_graph(captures, readings)
        kinds = [c["kind"] for c in g["conflicts"]]
        self.assertIn("unreadable", kinds)
        self.assertIn("unknown-optype", kinds)

    def test_wire_endpoint_creates_missing_op(self):
        captures = [cap("c1", 10, "network")]
        readings = {
            "c1": {"kind": "network", "nodes": [],
                   "wires": [{"from": "a1", "to": "b1", "toInlet": 2}]},
        }
        g = build_graph(captures, readings)
        self.assertEqual(g["stats"]["opCount"], 2)
        self.assertEqual(g["wires"][0]["toInlet"], 2)


if __name__ == "__main__":
    unittest.main()
