"""«Recent session folders» row of the «+ Add project» picker: sidereus/pipeline_projects.recent_dirs + GET ?recent=1.

⚠Home is a tmp dir (`USER_HOME` patched); `history`, `project_list`, `CODE_DIR` patched — never live files or the clock.
"""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import load, sidereus
from tests.test_prefs import get

cs = load()
PP = sidereus("pipeline_projects")

NOW = 1_800_000_000


def _row(cwd, to, plat="cc", **kw):
    r = {"cwd": cwd, "to": to, "plat": plat, "title": "secret title", "model": "opus", "sid": "s-" + str(to)}
    r.update(kw)
    return r


class RecentDirs(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.home = os.path.join(self.tmp, "home")
        for i in range(12):
            os.makedirs(os.path.join(self.home, "p%02d" % i))
        os.makedirs(os.path.join(self.home, "added"))
        os.makedirs(os.path.join(self.home, "sidereus"))
        os.makedirs(os.path.join(self.tmp, "outside"))
        self.rows, self.blocks, self.added = [], {}, [os.path.join(self.home, "added")]
        for name, val in (("USER_HOME", self.home), ("CODE_DIR", os.path.join(self.home, "sidereus")),
                          ("history", self._hist), ("project_list", lambda: (list(self.added), ""))):
            p = mock.patch.object(PP, name, val)
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _hist(self, days=7):
        self.days = days
        day = {"date": "2027-01-15", "rows": list(self.rows)}
        day.update(self.blocks)
        return {"ok": True, "at": NOW, "list": [day, {"date": "2027-01-14", "rows": []}]}

    def p(self, n):
        return os.path.join(self.home, n)

    def test_r1_order_cap_and_merge_across_platforms(self):
        # R1: newest first, at most 8, Claude + Codex + Gemini rows merged, one entry per folder (latest time wins)
        self.rows = [_row(self.p("p%02d" % i), NOW - 1000 * i) for i in range(10)]
        self.rows.append(_row(self.p("p05"), NOW - 50))                     # same folder, later session
        self.blocks = {"cx": {"n": 1, "rows": [_row(self.p("p10"), NOW - 10, "cx")]},
                       "gm": {"n": 1, "rows": [_row(self.p("p11"), NOW - 20, "gm"), _row(self.p("p00"), NOW - 5000, "gm")]}}
        out = PP.recent_dirs()
        self.assertEqual(self.days, PP.RECENT_DIRS_DAYS)
        self.assertEqual([x["path"] for x in out],
                         [self.p(n) for n in ("p00", "p10", "p11", "p05", "p01", "p02", "p03", "p04")])
        self.assertEqual(len(out), PP.RECENT_DIRS_MAX)
        self.assertEqual([x["plat"] for x in out[:4]], ["cc", "cx", "gm", "cc"])
        self.assertEqual(out[3]["at"], NOW - 50)

    def test_r1_future_to_clipped_to_now(self):
        self.rows = [_row(self.p("p01"), NOW + 3600)]
        self.assertEqual(PP.recent_dirs()[0]["at"], NOW)

    def test_r2_exclusions(self):
        # R2: already added, outside home, gone, Sidereus itself, home itself
        os.symlink(self.p("added"), self.p("alias"))                        # realpath = an added project
        self.rows = [_row(self.p("added"), NOW), _row(self.p("alias"), NOW), _row(os.path.join(self.tmp, "outside"), NOW),
                     _row(self.p("gone"), NOW), _row(self.p("sidereus"), NOW), _row(self.home, NOW), _row("", NOW),
                     _row(None, NOW), _row("rel/dir", NOW), _row(self.p("p01"), NOW - 1)]
        self.assertEqual([x["path"] for x in PP.recent_dirs()], [self.p("p01")])

    def test_r2_empty(self):
        self.rows = [_row(self.p("added"), NOW)]
        self.assertEqual(PP.recent_dirs(), [])
        self.rows = []
        self.assertEqual(PP.recent_dirs(), [])

    def test_r4_metadata_only_keys(self):
        # R4: folder name, path, time (+ platform logo key) only — never title/model/sid
        self.rows = [_row(self.p("p01"), NOW, extra="x")]
        out = PP.recent_dirs()
        self.assertEqual(out, [{"name": "p01", "path": self.p("p01"), "at": NOW, "plat": "cc"}])

    def test_history_failure_is_empty(self):
        with mock.patch.object(PP, "history", side_effect=RuntimeError("boom")):
            self.assertEqual(PP.recent_dirs(), [])

    def test_r1_route_recent(self):
        self.rows = [_row(self.p("p02"), NOW)]
        code, out = get("/api/pipelines/projects/dirs?recent=1")[:2]
        self.assertEqual((code, out["ok"], [x["path"] for x in out["recent"]]), (200, True, [self.p("p02")]))
        self.assertNotIn("title", out["recent"][0])


if __name__ == "__main__":
    unittest.main()
