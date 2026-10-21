"""Borrowed pipelines (sidereus/pipeline.py runs_here/borrowed): a run on a project of a pipeline defined in another one
shows there read-only, resolved from the owning project; gone when the run is gone.

⚠Projects live in a tmp dir: `allowed_projects`/`project_list`/`_proj_ok`/`CODE_DIR` are patched on pipeline — never live files.
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

PL = sidereus("pipeline")
P = {"v": 1, "name": "arch-map", "title": "Map", "rules": "r", "defaults": {"model": "inherit", "retry": 0},
     "stages": [{"title": "설계", "agent": "designer"}]}


def _mk(root, name, P_=None):
    d = os.path.join(root, ".claude", "pipelines")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(dict(P_ or P, name=name), f)


def _read(root):
    with open(os.path.join(root, ".claude", "pipelines", "arch-map.json"), encoding="utf-8") as f:
        return f.read()


class Borrow(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.here, self.sidereus, self.other = (os.path.join(self.tmp, n) for n in ("here", "sidereus", "other"))
        for p in (self.here, self.sidereus, self.other):
            os.makedirs(p)
        _mk(self.here, "bugfix")
        _mk(self.sidereus, "arch-map")
        projs = [self.sidereus, self.here, self.other]
        for k, v in (("allowed_projects", lambda: projs), ("project_list", lambda: (projs, "")), ("_proj_ok", lambda p: p in projs), ("CODE_DIR", self.sidereus),
                     ("default_tasks", lambda: {}), ("suggest", lambda *a, **k: []), ("apply_get", lambda p: {}),
                     ("skill_names", lambda p: [])):
            m = mock.patch.object(PL, k, v)
            m.start()
            self.addCleanup(m.stop)

    def _arch_runs(self, repos=()):
        rows = [{"sid": "s1", "cwd": self.tmp, "repos": list(repos)}]
        return PL.runs_here(self.here, rows, {self.here: {"sid": "s1"}}, "arch-map")

    def test_builtin_hidden_from_list_and_borrowed(self):
        _mk(self.sidereus, "security-checks", dict(P, builtin=True))
        _mk(self.sidereus, "hidden", dict(P, builtin=True, use="x" * 200))   # schema-breaking too: still hidden
        _mk(self.here, "mine", dict(P, builtin=True))                     # ⚠key honoured only in the Sidereus repo (CODE_DIR)
        _mk(self.other, "theirs", dict(P, builtin=True))
        rows = [{"sid": "s1", "cwd": self.here, "repos": [self.sidereus, self.other], "plrun": [{"name": "security-checks"}, {"name": "theirs"}]}]
        code, out = PL.pipelines(self.here, PL.runs_here(self.here, rows, {}, "arch-map"))
        self.assertEqual(code, 200)
        self.assertEqual([r["name"] for r in out["pipelines"]], ["bugfix", "mine"])
        self.assertEqual([r["name"] for r in out["borrowed"]], ["theirs"])
        code, out = PL.pipelines(self.sidereus)
        self.assertEqual([r["name"] for r in out["pipelines"]], ["arch-map"])
        with mock.patch.object(PL, "_remembered", lambda: []):   # ⚠never the live project store
            code, out = PL.pipelines("")
        self.assertEqual({p["path"]: p["n"] for p in out["projects"]}, {self.sidereus: 1, self.here: 2, self.other: 1})
        self.assertTrue(os.path.isfile(os.path.join(self.sidereus, ".claude", "pipelines", "security-checks.json")))   # file stays for the hooks

    def test_shown_only_while_run_exists(self):
        code, out = PL.pipelines(self.here, self._arch_runs())
        self.assertEqual(code, 200)
        self.assertEqual([r["name"] for r in out["pipelines"]], ["bugfix"])          # own list untouched
        b = out["borrowed"]
        self.assertEqual([(r["name"], r["from"], r["why"], r["builtin"]) for r in b], [("arch-map", self.sidereus, "first", True)])
        self.assertTrue(b[0]["ok"])
        self.assertEqual(b[0]["stages"][0]["title"], "설계")
        self.assertEqual(PL.pipelines(self.here, [])[1]["borrowed"], [])          # run aged out
        self.assertEqual(PL.pipelines(self.here)[1]["borrowed"], [])

    def test_owner_prefers_run_session(self):
        _mk(self.other, "arch-map")
        out = PL.pipelines(self.here, self._arch_runs())[1]["borrowed"]
        self.assertEqual((out[0]["from"], out[0]["why"]), (self.sidereus, "first"))   # sorted first known
        out = PL.pipelines(self.here, self._arch_runs(repos=[self.other]))[1]["borrowed"]
        self.assertEqual((out[0]["from"], out[0]["why"], out[0]["builtin"]), (self.other, "run", False))

    def test_plrun_cwd_only_and_own_name_skipped(self):
        _mk(self.other, "deploy")
        rows = [{"sid": "a", "cwd": self.here, "plrun": [{"name": "deploy", "proj": self.other}, {"name": "bugfix", "proj": self.here}]},
                {"sid": "b", "cwd": self.tmp, "repos": [self.here], "plrun": [{"name": "arch-map", "proj": self.sidereus}]}]
        out = PL.pipelines(self.here, PL.runs_here(self.here, rows, {}, "arch-map"))[1]["borrowed"]
        self.assertEqual([(r["name"], r["from"], r["why"]) for r in out], [("deploy", self.other, "run")])

    def test_not_editable_from_borrowing_project(self):
        before = _read(self.sidereus)
        code, out = PL.save({"proj": self.here, "name": "arch-map", "dry": True, "stages": P["stages"]})
        self.assertNotEqual(code, 200)
        self.assertFalse(os.path.exists(os.path.join(self.here, ".claude", "pipelines", "arch-map.json")))
        self.assertEqual(_read(self.sidereus), before)

    def test_unknown_owner_or_bad_name_dropped(self):
        out = PL.pipelines(self.here, [("nowhere", []), ("../x", []), (5, [])])[1]["borrowed"]
        self.assertEqual(out, [])

    def test_no_runs_skips_project_scan(self):
        def boom():
            raise AssertionError("allowed_projects must not run without runs")
        with mock.patch.object(PL, "allowed_projects", boom):
            self.assertEqual(PL.borrowed(self.here, None), [])
            self.assertEqual(PL.borrowed(self.here, []), [])


if __name__ == "__main__":
    unittest.main()
