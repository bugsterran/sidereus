"""Gemini CLI subagent chats (`chats/<parent sid>/<id>.jsonl`) — synthetic files in a temp dir, no live ~/.gemini."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

from tests._load import sidereus
from tests._node import node_e

te = sidereus("timeline_ext")
ext = sidereus("ext")
H = sidereus("history")
pg = sidereus("plat_gemini")

T0 = 1_790_000_000
PAR = "d6dd36b4-0000-4000-8000-000000000001"
SUB = "d507b66b-0000-4000-8000-000000000002"


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _gem(mid, t, n):
    return {"id": mid, "timestamp": _iso(t), "type": "gemini", "content": "SECRET body", "model": "gemini-3.8-flash",
            "tokens": {"input": n, "output": 0, "cached": 0, "thoughts": 0, "tool": 0}}


class GeminiSubagent(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.saved = (pg._real_home, te._ext, te.ext_runs)
        pg._real_home = lambda: self.root
        te._ext = {}
        te.ext_runs = lambda parent=None: []
        pg._cache.clear()
        pdir = os.path.join(self.root, ".gemini", "tmp", "proj")
        self.chats = os.path.join(pdir, "chats")
        os.makedirs(os.path.join(self.chats, PAR))
        with open(os.path.join(pdir, ".project_root"), "w", encoding="utf-8") as f:
            f.write("/w/proj")
        self.write("session-2026-10-01T05-52-d6dd36b4.jsonl", PAR, "main",
                   [{"id": "u1", "type": "user", "content": "SECRET prompt", "timestamp": _iso(T0)},
                    _gem("m1", T0 + 5, 100)])
        self.write(os.path.join(PAR, SUB + ".jsonl"), SUB, "subagent",
                   [{"id": "s1", "type": "user", "content": "SECRET task", "timestamp": _iso(T0 + 10)},
                    _gem("s2", T0 + 20, 40)])

    def tearDown(self):
        pg._real_home, te._ext, te.ext_runs = self.saved
        pg._cache.clear()
        shutil.rmtree(self.root)

    def write(self, name, sid, kind, lines):
        p = os.path.join(self.chats, name)
        head = {"sessionId": sid, "projectHash": "h", "startTime": _iso(T0), "lastUpdated": _iso(T0), "kind": kind}
        with open(p, "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(o) + "\n" for o in [head] + lines))
        os.utime(p, (T0 + 30, T0 + 30))

    def test_scan_finds_subagent_with_parent(self):
        got = {c["sid"]: c for c in pg.scan(0)}
        self.assertEqual(set(got), {PAR, SUB})
        self.assertEqual((got[SUB]["parent"], got[SUB]["kind"], got[SUB]["cwd"]), (PAR, "subagent", "/w/proj"))
        self.assertEqual((got[PAR]["parent"], got[PAR]["kind"], got[PAR]["cwd"]), ("", "main", "/w/proj"))
        self.assertEqual(set(got[PAR]["msgs"]), {"m1"})                 # parent file keeps only its own usage
        self.assertNotIn("SECRET", json.dumps(list(got.values())))
        self.assertTrue(pg.used_since(T0 + 1))

    def test_timeline_child_under_cli_parent(self):
        rows = {r["tid"]: r for r in te._plat_rows(ext.PLAT_MODS["gemini"], T0 - 60, T0 + 3600)}
        head, kid = rows["ext:gm|" + PAR], rows["ext:gm|" + SUB]
        self.assertEqual((head["kind"], head["depth"], head["sid"]), ("sess", 0, PAR))
        self.assertEqual((kid["depth"], kid["parent"], kid["type"], kid["cwd"], kid["tk"]),
                         (1, PAR, "subagent", "/w/proj", 40))
        self.assertEqual((kid["aid"], kid["desc"]), (SUB, "gemini-3.8-flash"))     # label via tlAgLab: model + chip
        self.assertEqual(head["tk"], 100)                                             # head = parent file only
        self.assertNotIn("SECRET", json.dumps(list(rows.values()), default=str))

    def test_history_folds_into_parent(self):
        days = H._plat_days("0000-00-00", 0, pg.scan, "gm")
        rows = [r for d in days.values() for r in (d["rows"] if isinstance(d, dict) else d)]
        self.assertEqual([(r["sid"], r["tok"]) for r in rows], [(PAR, 140)])

    def test_usage_counts_tokens_not_sessions(self):
        with mock.patch.object(ext, "PLAT_MODS", {"gemini": pg}), mock.patch.dict(ext._tok, {}, clear=True):
            u = ext.ext_usage_today(now=T0 + 60)
        gm = u[ext.EXT_PLAT["gemini"]]
        self.assertEqual((gm["tok"], gm["n_sessions"]), (140, 1))

    def test_usage_today_zero_for_session_without_tokens(self):
        live = {("cursor", "c1"): {"cwd": "/w/p", "lastSeen": T0 + 30},
                ("codex", "old"): {"cwd": "/w/p", "lastSeen": T0 - 3 * 86400}}
        with mock.patch.object(ext, "PLAT_MODS", {"gemini": pg}), mock.patch.dict(ext._tok, {}, clear=True), \
                mock.patch.dict(ext._ext, live, clear=True):
            u = ext.ext_usage_today(now=T0 + 60)
        self.assertEqual((u["cu"]["tok"], u["cu"]["n_sessions"]), (0, 1))
        self.assertNotIn("cx", u)                                   # last seen before today: no entry
        self.assertEqual(u["gm"]["tok"], 140)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class JsBucket(unittest.TestCase):
    def test_cli_kid_before_head_keeps_plat_bucket(self):
        import subprocess
        from tests._load import js_fn
        kid = {"sess": False, "plat": "gm", "cwd": "/w/p", "type": "subagent",
               "items": [{"parent": PAR, "segs": [[1, 2]], "start": 1, "end": 2}]}
        gmh = {"sess": True, "plat": "gm", "cwd": "/w/p", "items": [{"sid": PAR, "segs": [[1, 2]], "start": 1, "end": 2}]}
        js = "\n".join(["let SESS = [];", js_fn("tlLiveOf"), js_fn("tlSessions"),
                        "const r = tlSessions(" + json.dumps([kid, gmh]) + ", 0, 10);"
                        "console.log(JSON.stringify(r.sessOrder.map(v => [v.cwd, v.plat, !!v.head, v.kids.length])));"])
        p = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout), [["/w/p", "gm", True, 1]])


if __name__ == "__main__":
    unittest.main()
