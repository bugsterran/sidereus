"""Main agent's [pl:] stage marker (sidereus/agents.py plm_of): fresh -> {name, title, age}, stale/bad -> None."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus


class PlmOf(unittest.TestCase):
    def setUp(self):
        self.ag = sidereus("agents")
        self.tmp = tempfile.mkdtemp()
        self.old = self.ag.PLM_DIR
        self.ag.PLM_DIR = self.tmp

    def tearDown(self):
        self.ag.PLM_DIR = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, sid, body):
        with open(os.path.join(self.tmp, sid + ".json"), "w") as f:
            f.write(body if isinstance(body, str) else json.dumps(body))

    def test_fresh_present_only_three_fields(self):
        self._w("abcd1234-ef", {"name": "bugfix", "title": "수정", "t": 1000, "cwd": "/secret"})
        self.assertEqual(self.ag.plm_of("abcd1234-ef", 1100), {"name": "bugfix", "title": "수정", "age": 100})

    def test_stale_absent(self):
        self._w("abcd1234-ef", {"name": "bugfix", "title": "수정", "t": 1000})
        self.assertIsNone(self.ag.plm_of("abcd1234-ef", 1000 + self.ag.PLM_LIVE_S + 1))

    def test_bad_json_missing_or_bad_sid_ignored(self):
        self._w("abcd1234-ef", "{not json")
        self._w("abcd1234-gh", '["x"]')
        self.assertIsNone(self.ag.plm_of("abcd1234-ef", 1000))
        self.assertIsNone(self.ag.plm_of("abcd1234-gh", 1000))
        self.assertIsNone(self.ag.plm_of("nofile-12345", 1000))
        self.assertIsNone(self.ag.plm_of("../../etc/x", 1000))

    def test_hold_mark_lives_until_hold_cap(self):
        self._w("abcd1234-ef", {"name": "bugfix", "title": "수정", "t": 1000, "hold": 1})
        self.assertEqual(self.ag.plm_of("abcd1234-ef", 1121)["age"], 121)
        self.assertIsNotNone(self.ag.plm_of("abcd1234-ef", 1000 + self.ag.PLM_HOLD_S))
        self.assertIsNone(self.ag.plm_of("abcd1234-ef", 1000 + self.ag.PLM_HOLD_S + 1))

    def test_non_hold_mark_unchanged(self):
        self._w("abcd1234-ef", {"name": "bugfix", "title": "수정", "t": 1000, "hold": 0})
        self.assertIsNotNone(self.ag.plm_of("abcd1234-ef", 1120))
        self.assertIsNone(self.ag.plm_of("abcd1234-ef", 1121))


class ExtRowPlm(unittest.TestCase):
    """Non-Claude CLI rows carry the same `plm` key as Claude rows (web 48-pipeline.js reads x.plm)."""
    NOW = 1_800_000_000.0

    def setUp(self):
        ext = self.ext = sidereus("ext")
        names = ("_ext", "time", "ext_gone_check", "_ext_prune_locked", "ext_tok_refresh", "ext_tok", "plm_of")
        self._saved = {n: getattr(ext, n) for n in names}
        now = self.NOW
        ext._ext = {}
        ext.time = type("T", (), {"time": staticmethod(lambda: now)})
        ext.ext_gone_check = lambda now: None
        ext._ext_prune_locked = lambda now: None
        ext.ext_tok_refresh = lambda plat, sid, tp: None
        ext.ext_tok = lambda plat, sid: {}
        ext.plm_of = lambda sid, now: {"name": "bugfix", "title": "수정", "age": 5} if sid == "s-live-1234" else None

    def tearDown(self):
        for n, v in self._saved.items():
            setattr(self.ext, n, v)

    def test_row_carries_plm_only_when_live(self):
        t = self.NOW - 10
        self.ext._ext[("gemini", "s-live-1234")] = {"cwd": "/w/p", "state": "run", "lastSeen": t, "firstSeen": t}
        self.ext._ext[("gemini", "s-none-1234")] = {"cwd": "/w/p", "state": "run", "lastSeen": t, "firstSeen": t}
        rows = {r["sid"]: r for r in self.ext.ext_rows()}
        self.assertEqual(rows["s-live-1234"]["plm"], {"name": "bugfix", "title": "수정", "age": 5})
        self.assertNotIn("plm", rows["s-none-1234"])


if __name__ == "__main__":
    unittest.main()
