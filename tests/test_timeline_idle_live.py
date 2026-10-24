"""A connected session quiet for longer than the timeline window still gets its session row (empty segs);
a disconnected one quiet as long yields nothing. Claude (`_tl_sess_row`) and ext CLIs (`_ext_tl`)."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

tl = sidereus("timeline")
te = sidereus("timeline_ext")

CUT, NOW = 1_800_000_000, 1_800_003_600
CWD = "/x/proj"


class ClaudeIdleLive(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.fp = os.path.join(self.d, "sid-1.jsonl")
        with open(self.fp, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "timestamp": "2027-01-01T00:00:00.000Z"}) + "\n")
        os.utime(self.fp, (CUT - 7200, CUT - 7200))           # last record well before the window
        self.saved = {k: getattr(tl, k) for k in ("_sess_segments", "_compacts", "_sess_waits", "clear_of")}
        tl._sess_segments = lambda fp, cut, tok_out=None: ([], 0)
        tl._compacts = lambda fp, cut: []
        tl._sess_waits = lambda fp, cut: []
        tl.clear_of = lambda sid: []

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(tl, k, v)
        shutil.rmtree(self.d)

    def test_live_idle_row_kept(self):
        srow = {"sid": "sid-1", "cwd": CWD, "state": "wait", "ageSec": 9000}
        r = tl._tl_sess_row(self.fp, "sid-1", srow, CUT, CWD, "proj")
        self.assertIsNotNone(r)
        self.assertEqual((r["kind"], r["segs"], r["state"]), ("sess", [], "wait"))
        self.assertGreaterEqual(r["end"], r["start"])

    def test_not_live_idle_dropped(self):
        self.assertIsNone(tl._tl_sess_row(self.fp, "sid-1", None, CUT, CWD, "proj"))


class _Roots:
    def __init__(self, d):
        self.d = d

    def projects_dirs(self, _base):
        return [self.d]


class PickIdleLive(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.dir = os.path.join(self.root, tl._slug(CWD))
        os.makedirs(self.dir)
        for i, sid in enumerate(["old-live", "old-dead", "n1", "n2", "n3"]):   # mtime rises with i
            fp = os.path.join(self.dir, sid + ".jsonl")
            open(fp, "w", encoding="utf-8").close()
            os.utime(fp, (CUT - 9000 + i, CUT - 9000 + i))
        self.saved = tl.claude_roots
        tl.claude_roots = _Roots(self.root)

    def tearDown(self):
        tl.claude_roots = self.saved
        shutil.rmtree(self.root)

    def test_live_older_than_newest3_picked(self):
        got = tl._tl_pick(CUT, [{"sid": "old-live", "cwd": CWD, "project": "proj"}])
        names = sorted(os.path.basename(p)[:-6] for p in got[0][2])
        self.assertEqual(names, ["n1", "n2", "n3", "old-live"])


class ExtIdleLive(unittest.TestCase):
    def setUp(self):
        self.saved = {k: getattr(te, k) for k in ("_ext", "ext_runs")}
        te.ext_runs = lambda: []

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(te, k, v)

    def rows(self, ext, scan):
        te._ext = ext
        return te._ext_tl(CUT, NOW, None, "codex", "cx", "codex exec", "Codex", lambda since: scan)

    def test_live_idle_not_scanned(self):          # rollout older than the window: the scan never returns it
        out = self.rows({("codex", "s1"): {"cwd": CWD, "state": "wait", "lastSeen": CUT - 7200}}, [])
        self.assertEqual([(r["tid"], r["kind"], r["segs"], r["depth"]) for r in out],
                         [("ext:cx|s1", "sess", [], 0)])
        self.assertGreaterEqual(out[0]["end"], out[0]["start"])

    def test_live_idle_scanned_old_acts(self):
        c = {"sid": "s1", "cwd": CWD, "acts": {"k": CUT - 7200}, "msgs": {}}
        out = self.rows({("codex", "s1"): {"cwd": CWD, "state": "wait"}}, [c])
        self.assertEqual([(r["tid"], r["segs"]) for r in out], [("ext:cx|s1", [])])

    def test_not_live_idle_dropped(self):
        c = {"sid": "s1", "cwd": CWD, "acts": {"k": CUT - 7200}, "msgs": {}}
        self.assertEqual(self.rows({}, [c]), [])
        self.assertEqual(self.rows({("codex", "s1"): {"cwd": CWD, "state": "gone"}}, [c]), [])


class HookOnlyPlat(unittest.TestCase):
    """Cursor has no record-file adapter: its row comes from `_ext` alone, bars from hook event times."""
    def setUp(self):
        self.saved = {k: getattr(te, k) for k in ("_ext", "ext_runs", "PLAT_MODS")}
        te.ext_runs = lambda: []
        te.PLAT_MODS = {}

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(te, k, v)

    def test_cursor_row_from_hook_events(self):
        ev = [{"e": "SessionStart", "t": CUT + 10}, {"e": "UserPromptSubmit", "t": CUT + 100},
              {"e": "Stop", "t": CUT + 160}]
        te._ext = {("cursor", "c1"): {"cwd": CWD, "state": "wait", "ev": ev, "lastSeen": CUT + 160}}
        out = te._plat_tl_rows(CUT, NOW)
        self.assertEqual([(r["tid"], r["kind"], r["plat"], r["segs"]) for r in out],
                         [("ext:cu|c1", "sess", "cu", [[CUT + 100, CUT + 160]])])

    def test_cursor_started_only_is_idle_row(self):
        te._ext = {("cursor", "c1"): {"cwd": CWD, "state": "wait", "ev": [{"e": "SessionStart", "t": CUT + 10}],
                                       "lastSeen": CUT + 10}}
        self.assertEqual([(r["tid"], r["segs"]) for r in te._plat_tl_rows(CUT, NOW)], [("ext:cu|c1", [])])


if __name__ == "__main__":
    unittest.main()
