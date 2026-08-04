import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from matching import normalize, resolve_label


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


if __name__ == "__main__":
    unittest.main()
