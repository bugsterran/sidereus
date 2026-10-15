"""sidereus/sess_clear.py — /clear pairs from a tmp CLEAR_FILE (never the live data dir)."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import load

load()
from sidereus import sess_clear as sc  # noqa: E402

A = "aaaaaaaa-1111-2222-3333-444444444444"
B = "bbbbbbbb-1111-2222-3333-444444444444"
C = "cccccccc-1111-2222-3333-444444444444"


class SessClear(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self._saved = (sc.CLEAR_FILE, sc.CLEAR_MAX, sc.CLEAR_TAIL)
        sc.CLEAR_FILE = os.path.join(self.d, "clears.jsonl")
        sc._clr_cache["key"] = None

    def tearDown(self):
        sc.CLEAR_FILE, sc.CLEAR_MAX, sc.CLEAR_TAIL = self._saved
        sc._clr_cache["key"] = None
        shutil.rmtree(self.d, ignore_errors=True)

    def write(self, lines):
        with open(sc.CLEAR_FILE, "w", encoding="utf-8") as f:
            for x in lines:
                f.write((x if isinstance(x, str) else json.dumps(x)) + "\n")

    def test_missing_file(self):
        self.assertEqual(sc.clear_links(), [])
        self.assertEqual(sc.clear_of(A), [])

    def test_links_and_clear_of(self):
        self.write([{"at": 10, "pid": "77", "old": A, "new": B}, {"at": 20, "pid": 77, "old": B, "new": C}])
        self.assertEqual(sc.clear_links(), [{"pid": "77", "old": A, "new": B, "at": 10},
                                            {"pid": "77", "old": B, "new": C, "at": 20}])
        self.assertEqual(sc.clear_of(C), [{"pid": "77", "old": B, "new": C, "at": 20}])
        self.assertEqual(sc.clear_of(A), [])
        self.assertEqual(sc.clear_of(""), [])

    def test_corrupt_lines_skipped(self):
        self.write(["{not json", {"at": 1, "pid": "x", "old": A, "new": B}, {"at": 1, "pid": "5", "old": "../x",
                                                                            "new": B},
                    {"at": 1, "pid": "5", "old": A}, {"at": 3, "pid": "5", "old": A, "new": B}])
        self.assertEqual(sc.clear_links(), [{"pid": "5", "old": A, "new": B, "at": 3}])

    def test_cap_holds(self):
        sc.CLEAR_MAX = 3
        self.write([{"at": i, "pid": "5", "old": A, "new": "sid-%08d" % i} for i in range(10)])
        got = sc.clear_links()
        self.assertEqual([x["at"] for x in got], [7, 8, 9])

    def test_tail_drops_partial_line(self):
        sc.CLEAR_TAIL = 200
        self.write([{"at": i, "pid": "5", "old": A, "new": B} for i in range(20)])
        got = sc.clear_links()
        self.assertTrue(got and got[-1]["at"] == 19 and len(got) < 20)

    def test_cache_returns_copies(self):
        self.write([{"at": 1, "pid": "5", "old": A, "new": B}])
        sc.clear_links()[0]["old"] = "mutated"
        self.assertEqual(sc.clear_links()[0]["old"], A)


if __name__ == "__main__":
    unittest.main()
