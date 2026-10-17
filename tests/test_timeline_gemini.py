"""Gemini chat files on the agent timeline — synthetic files in a temp dir, no live ~/.gemini."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

from tests._load import sidereus

tl = sidereus("timeline")
te = sidereus("timeline_ext")
ext = sidereus("ext")
GM = ext.PLAT_MODS["gemini"]
pg = sidereus("plat_gemini")

T0 = 1_790_000_000


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _gem(mid, t, n, model="gemini-3.8-flash"):
    return {"id": mid, "timestamp": _iso(t), "type": "gemini", "content": "x", "model": model,
            "tokens": {"input": n, "output": 10, "cached": 0, "thoughts": 5, "tool": 0, "total": n + 15}}


class GeminiTimeline(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.saved = (pg._real_home, te._ext, te.ext_runs)
        pg._real_home = lambda: self.root
        te._ext = {}
        te.ext_runs = lambda parent=None: []     # ⚠live ext-runs.json (real ask-gemini runs) would turn chats into child rows
        pg._cache.clear()
        pdir = os.path.join(self.root, ".gemini", "tmp", "proj")
        os.makedirs(os.path.join(pdir, "chats"))
        with open(os.path.join(pdir, ".project_root"), "w", encoding="utf-8") as f:
            f.write("/w/proj")
        self.chats = os.path.join(pdir, "chats")

    def tearDown(self):
        pg._real_home, te._ext, te.ext_runs = self.saved
        pg._cache.clear()
        shutil.rmtree(self.root)

    def write(self, name, lines, mtime):
        p = os.path.join(self.chats, name)
        with open(p, "w", encoding="utf-8") as f:
            for o in lines:
                f.write(json.dumps(o) + "\n")
        os.utime(p, (mtime, mtime))
        return p

    def hdr(self, sid, t):
        return {"sessionId": sid, "projectHash": "h", "startTime": _iso(t), "lastUpdated": _iso(t), "kind": "main"}

    def test_segments_and_dedupe(self):
        g = te.SEG_GAP
        self.write("session-a.jsonl", [
            self.hdr("sid-a", T0),
            {"$set": {"messages": [{"id": "u0", "type": "user", "timestamp": _iso(T0)}]}},
            {"id": "u1", "type": "user", "timestamp": _iso(T0 + 5)},
            _gem("m1", T0 + 8, 100),
            _gem("m1", T0 + 8, 100),                                  # rewritten copy -> counted once
            {"$set": {"lastUpdated": _iso(T0 + 9)}},
            {"id": "i1", "type": "info", "timestamp": _iso(T0 + 50)},    # info: not activity
            {"id": "u2", "type": "user", "timestamp": _iso(T0 + 8 + g + 1)},
            _gem("m2", T0 + 8 + g + 3, 200),
        ], T0 + g + 20)
        rows = te._plat_rows(GM, T0 - 3600, T0 + 3600)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["segs"], [[T0, T0 + 8], [T0 + 8 + g + 1, T0 + 8 + g + 3]])
        self.assertEqual(r["tk"], 115 + 215)
        self.assertEqual((r["plat"], r["kind"], r["cwd"], r["tid"]), ("gm", "sess", "/w/proj", "ext:gm|sid-a"))
        self.assertEqual(r["model"], "gemini-3.8-flash")

    def test_short_run_kept(self):
        self.write("session-p.jsonl", [self.hdr("sid-p", T0), {"id": "u", "type": "user", "timestamp": _iso(T0)},
                                       _gem("m", T0 + 20, 50)], T0 + 20)
        r = te._plat_rows(GM, T0 - 60, T0 + 60)[0]
        self.assertEqual(r["segs"], [[T0, T0 + 20]])

    def test_window_cut(self):
        self.write("session-old.jsonl", [self.hdr("old", T0 - 9000), _gem("o", T0 - 9000, 10)], T0 - 9000)
        self.write("session-mix.jsonl", [self.hdr("mix", T0 - 9000), _gem("a", T0 - 9000, 10),
                                         _gem("b", T0 + 10, 20)], T0 + 10)
        rows = te._plat_rows(GM, T0 - 60, T0 + 60)
        self.assertEqual([r["tid"] for r in rows], ["ext:gm|mix"])
        self.assertEqual((rows[0]["segs"], rows[0]["tk"]), ([[T0 + 10, T0 + 10]], 35))

    def test_incremental_append(self):
        p = self.write("session-i.jsonl", [self.hdr("inc", T0), _gem("a", T0, 10)], T0)
        self.assertEqual(te._plat_rows(GM, T0 - 60, T0 + 60)[0]["tk"], 25)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(_gem("a", T0, 10)) + "\n" + json.dumps(_gem("b", T0 + 30, 20)) + "\n")
        os.utime(p, (T0 + 30, T0 + 30))
        self.assertEqual(te._plat_rows(GM, T0 - 60, T0 + 60)[0]["tk"], 60)


class ClaudeRowsUnchanged(unittest.TestCase):
    """A Gemini row joins `rows` but leaves the Claude rows and the Claude-only token strip as they were."""

    def test_golden_rows_same(self):
        from tests import test_golden_burn_timeline as g
        case = g.AgentsTimelineGolden("test_golden")
        case.setUp()
        try:
            base = tl.agents_timeline(12)
            gm = {"tid": "ext:gm|z", "type": "p", "desc": "", "segs": [[int(g.NOW - 100), int(g.NOW - 90)]],
                  "comp": [], "seen": 0, "start": int(g.NOW - 100), "end": int(g.NOW - 90), "run": False,
                  "state": "", "idle": 0, "blocked": "", "proj": "p", "cwd": "/w/a", "depth": 0, "kind": "sess",
                  "plat": "gm", "model": "m", "tk": 9, "_tk": [(g.NOW - 95, 9)], "last": ""}
            case.p.set(tl, "_plat_tl_rows", lambda cut, now, pcwd=None: [dict(gm, _tk=list(gm["_tk"]))])
            got = tl.agents_timeline(12)
        finally:
            case.tearDown()
        self.assertEqual([r for r in got["rows"] if not r.get("plat")], base["rows"])
        self.assertEqual(got["tok"], base["tok"])
        self.assertEqual([r["tks"] for r in got["rows"] if r.get("plat")], [[9]])


if __name__ == "__main__":
    unittest.main()
