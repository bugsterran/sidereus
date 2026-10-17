"""History tab: Gemini rows from synthetic chat files, kept in a separate `gm` block (Claude output unchanged)."""
import hashlib
import json
import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timezone
from unittest import mock

from tests._load import sidereus

ext = sidereus("ext")
H = sidereus("history")
us = sidereus("usage")
pg = sidereus("plat_gemini")


class _Clock:
    """Real `time` module with `time()` pinned — patched onto the module under test only."""
    def __init__(self, t):
        self.t = t

    def time(self):
        return self.t

    def __getattr__(self, name):
        return getattr(time, name)


NOW = time.mktime((2026, 9, 24, 12, 30, 0, 0, 0, -1))   # local 12:30 — g1/g2 never straddle an hour or midnight


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _msg(mid, t, inp, out, model="gemini-2.5-flash"):
    return {"id": mid, "timestamp": _iso(t), "type": "gemini", "content": "SECRET body text", "model": model,
            "tokens": {"input": inp, "output": out, "cached": 0, "thoughts": 0, "tool": 0}}


class HistGemini(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.g = os.path.join(self.home, ".gemini")
        self._home, pg._real_home = pg._real_home, (lambda: self.home)
        pg._cache.clear()
        H._hist_cache.clear()
        self.now = NOW
        self.patch(H, time=_Clock(NOW))

    def patch(self, mod, **kw):
        for k, v in kw.items():
            self.addCleanup(setattr, mod, k, getattr(mod, k))
            setattr(mod, k, v)

    def tearDown(self):
        pg._real_home = self._home
        pg._cache.clear()
        H._hist_cache.clear()
        shutil.rmtree(self.home, ignore_errors=True)

    def _chat(self, dirname, sid, lines, root=None, phash=""):
        d = os.path.join(self.g, "tmp", dirname, "chats")
        os.makedirs(d, exist_ok=True)
        if root is not None:
            with open(os.path.join(self.g, "tmp", dirname, ".project_root"), "w", encoding="utf-8") as f:
                f.write(root + "\n")
        p = os.path.join(d, "session-2026-09-24T05-00-%s.jsonl" % sid[:8])
        head = {"sessionId": sid, "projectHash": phash, "startTime": _iso(self.now - 7200),
                "lastUpdated": _iso(self.now), "kind": "main"}
        with open(p, "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(o) + "\n" for o in [head] + lines))
        os.utime(p, (self.now, self.now))                         # plat_gemini filters by mtime
        return p

    def test_scan_dedupe_project_and_cache(self):
        t = self.now - 600
        self._chat("proj-a", "aaaaaaaa-1", [
            {"id": "u1", "timestamp": _iso(t), "type": "user", "content": "SECRET prompt"},
            _msg("g1", t, 100, 10),
            {"$set": {"messages": [_msg("g1", t, 100, 20)]}},       # same id rewritten → counted once
            _msg("g2", t + 60, 50, 5)], root="/work/proj-a")
        c = pg.chats(0)
        self.assertEqual(len(c), 1)
        self.assertEqual((c[0]["sid"], c[0]["cwd"], c[0]["project"]), ("aaaaaaaa-1", "/work/proj-a", "proj-a"))
        self.assertEqual(sorted(c[0]["msgs"]), ["g1", "g2"])
        self.assertEqual(c[0]["msgs"]["g1"][1], 20)
        self.assertNotIn("SECRET", json.dumps(c, default=str))
        with mock.patch.object(pg, "read", side_effect=AssertionError("rescanned")):
            pg.chats(0)                                                  # unchanged (size, mtime) → cache
        self.assertEqual(pg.chats(self.now + 3600), [])          # mtime older than window → skipped

    def test_project_hash_mapping(self):
        path = "/work/hashed-proj"
        h = hashlib.sha256(path.encode()).hexdigest()
        os.makedirs(self.g, exist_ok=True)
        with open(os.path.join(self.g, "projects.json"), "w", encoding="utf-8") as f:
            json.dump({"projects": {path: "hashed-proj"}}, f)
        self._chat(h, "bbbbbbbb-2", [_msg("g1", self.now - 60, 1, 1)], phash=h)
        c = pg.chats(0)
        self.assertEqual((c[0]["cwd"], c[0]["project"]), (path, "hashed-proj"))

    def _hist(self):
        H._hist_cache.clear()
        return H.history(2)

    def test_history_gm_block_and_claude_unchanged(self):
        hour = int(self.now // 3600 * 3600)
        files = {"/p/-x/c1.jsonl": {"sl": "-x", "h": {str(hour): {"claude-opus-5": [100, 50, 0, 0]}}}}
        with mock.patch.object(H, "_uidx_refresh", lambda: None), \
                mock.patch.dict(H._uidx, {"files": files}):
            with mock.patch.object(pg, "scan", return_value=[]):
                base = self._hist()
            self._chat("proj-a", "aaaaaaaa-1", [_msg("g1", self.now - 30, 1000, 200),
                                                _msg("g2", self.now - 20, 3000, 100, model="unpriced-x")],
                       root="/work/proj-a")
            got = self._hist()
        strip = lambda o: [{k: v for k, v in d.items() if k != "gm"} for d in o["list"]]
        self.assertEqual(strip(got), base["list"])                       # Claude rows/totals untouched
        today = got["list"][0]
        self.assertEqual(today["n"], 1)
        gm = today["gm"]
        self.assertEqual((gm["n"], gm["tok"], gm["costMiss"]), (1, 4300, 1))
        r = gm["rows"][0]
        self.assertEqual((r["plat"], r["project"], r["hours"], r["cost"], r["title"]), ("gm", "proj-a", 1, 0, ""))
        self.assertAlmostEqual(r["estCost"], round((1000 * 0.30 + 200 * 2.50) / 1e6, 4))
        self.assertTrue(all(x["plat"] == "cc" for x in today["rows"]))

    def test_broken_scanner_keeps_claude(self):
        with mock.patch.object(H, "_uidx_refresh", lambda: None), \
                mock.patch.dict(H._uidx, {"files": {}}), \
                mock.patch.object(pg, "scan", side_effect=RuntimeError("boom")):
            self.assertTrue(self._hist()["ok"])


if __name__ == "__main__":
    unittest.main()
