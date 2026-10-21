"""R4: pl_runs.pl_none reads plmark/<sid>.none.json — allow-listed cat, nudge-only -> {"u": 1}, else None.
⚠PLR_DIR points at a temp dir; no live files."""
import json
import os
import tempfile
import unittest

from tests._load import sidereus

R = sidereus("pl_runs")
SID = "abcd1234-0000"


class PlNone(unittest.TestCase):
    def setUp(self):
        self.d0 = R.PLR_DIR
        R.PLR_DIR = tempfile.mkdtemp()

    def tearDown(self):
        R.PLR_DIR = self.d0

    def _put(self, doc, sid=SID):
        with open(os.path.join(R.PLR_DIR, sid + ".none.json"), "w", encoding="utf-8") as f:
            f.write(doc if isinstance(doc, str) else json.dumps(doc))

    def test_allow_list(self):
        for c in R.PLR_NONE_CATS:
            self._put({"v": 1, "cat": c, "t": 5, "extra": "secret"})
            self.assertEqual(R.pl_none(SID), {"cat": c})   # no other field leaks

    def test_nudge_only(self):
        self._put({"v": 1, "nudge": 9})
        self.assertEqual(R.pl_none(SID), {"u": 1})
        self._put({"v": 1, "cat": "explore", "nudge": 9})
        self.assertEqual(R.pl_none(SID), {"cat": "explore"})   # declaration wins

    def test_bad_cat(self):
        for c in ("refactor", "", 3, None, "<b>"):
            self._put({"v": 1, "cat": c})
            self.assertIsNone(R.pl_none(SID))
        self._put({"v": 1, "cat": "bogus", "nudge": 9})
        self.assertIsNone(R.pl_none(SID))

    def test_bad_sid_missing_unparsable(self):
        self._put({"cat": "explore"})
        for sid in ("", None, "../x", "short", "a/b12345678", SID + ".x"):
            self.assertIsNone(R.pl_none(sid))
        self.assertIsNone(R.pl_none("ffff1234-0000"))   # missing
        self._put("{not json")
        self.assertIsNone(R.pl_none(SID))
        self._put([1, 2])
        self.assertIsNone(R.pl_none(SID))

    def test_oversize(self):
        self._put(json.dumps({"cat": "explore", "pad": "x" * R.PLR_NONE_MAX}))
        self.assertIsNone(R.pl_none(SID))


if __name__ == "__main__":
    unittest.main()
