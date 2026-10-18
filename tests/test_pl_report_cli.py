"""scripts/pl_report.py: dated report under eval/<key>/reports, --auto weekly cadence, same sentences as pl_outcome.
In-process; pl_outcome `_git`/`OC_EVAL_DIR`, `harness_evidence.EV_FILE` and the script's `_now`/`_gate` are patched."""
import importlib.util
import io
import json
import os
import shutil
import stat
import tempfile
import time
import unittest
from unittest import mock

from tests._load import ROOT, load, sidereus

load()
OC = sidereus("pl_outcome")
EV = sidereus("harness_evidence")
TR = sidereus("harness_trail")
_spec = importlib.util.spec_from_file_location("pl_report_t", os.path.join(ROOT, "scripts", "pl_report.py"))
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)
NOW = time.mktime((2026, 10, 18, 12, 0, 0, 0, 0, -1))


class Report(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pl-rep-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.proj = os.path.realpath(os.path.join(self.tmp, "proj"))
        self.pf = os.path.join(self.proj, ".claude", "pipelines", "flow.json")
        os.makedirs(os.path.dirname(self.pf))
        with open(self.pf, "w", encoding="utf-8") as f:
            json.dump({"name": "flow", "stages": [{"title": "build", "agent": "a"}, {"title": "review", "agent": "reviewer"}]}, f)
        with open(os.path.join(self.tmp, "evidence.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"v": 1, "kind": "check", "repo": self.proj, "ts": NOW - 100, "mode": "fast", "rc": 0,
                                "head": "a" * 7, "dirty": False, "steps": []}) + "\n")
        key = OC.repo_key(self.proj)
        os.makedirs(os.path.join(self.tmp, "eval", key))
        with open(os.path.join(self.tmp, "eval", key, "runs.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"name": "flow", "t0": NOW - 200, "end": NOW - 50, "lb": [{"f": "review", "g": "build", "n": 1}],
                                "dc": {"jump": 1}}) + "\n")
        self.rep = os.path.join(self.tmp, "eval", key, "reports")
        log = "\x1e%s\x1f%d\n\na.py\n\x1e%s\x1f%d\n\na.py\nb.py\n" % ("b" * 40, NOW - 10, "a" * 40, NOW - 150)
        out = {"rev-parse": "f" * 40 + "\n", "log": log, "rev-list": "b" * 40 + "\n"}   # rev-list: b descends from a
        git = lambda repo, args: (0, out[args[0]]) if args[0] in out else None
        trgit = lambda repo, args: (0, "f" * 40 + "\n") if args[0] == "rev-parse" else (0, "")   # head an ancestor, no rollback
        for mod, k, v in ((OC, "OC_EVAL_DIR", os.path.join(self.tmp, "eval")), (OC, "_git", git),
                          (EV, "EV_FILE", os.path.join(self.tmp, "evidence.jsonl")), (TR, "_git", trgit),
                          (R, "_now", lambda: self.now), (R, "_gate", lambda P, name, repo, now: {"n": 1, "m": 2})):
            p = mock.patch.object(mod, k, v)
            p.start()
            self.addCleanup(p.stop)
        OC._OC_MEMO.clear()
        self.now = NOW

    def run_(self, *extra):
        with mock.patch("sys.stdout", io.StringIO()):
            return R.main(["--repo", self.proj, "--pipeline", self.pf] + list(extra))

    def test_dated_file_and_sentences(self):
        self.assertEqual(self.run_(), 0)
        path = os.path.join(self.rep, "2026-10-18.md")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        oc = OC.outcome(self.proj, "flow", ["review"], NOW)
        want = OC.sentences({"n": 1, "m": 2}, oc)
        self.assertEqual([ln[2:] for ln in text.splitlines() if ln.startswith("- ")], want)
        self.assertIn("Result: 0 of 1 passes broke later, fix followed 1", want)
        self.assertIn("| aaaaaaaaaaaa | no | yes | `a.py`, `b.py` |", text)
        self.assertEqual(os.listdir(self.rep), ["2026-10-18.md"])   # no temp file left

    def test_auto_cadence(self):
        os.makedirs(self.rep)
        open(os.path.join(self.rep, "2026-10-12.md"), "w", encoding="utf-8").close()   # 6 days old
        self.assertEqual(self.run_("--auto"), 0)
        self.assertEqual(os.listdir(self.rep), ["2026-10-12.md"])
        self.now = NOW + 2 * 86400   # 8 days
        self.assertEqual(self.run_("--auto"), 0)
        self.assertIn("2026-10-20.md", os.listdir(self.rep))

    def test_bad_args(self):
        with mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(R.main(["--repo", self.proj, "--pipeline", os.path.join(self.tmp, "x.json")]), 2)
            self.assertEqual(R.main(["--repo", self.proj, "--pipeline", self.pf, "--data-dir", "rel"]), 2)
        self.assertFalse(os.path.exists(self.rep))


if __name__ == "__main__":
    unittest.main()
