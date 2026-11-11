"""hooks/pl_flow.py builtin pipelines: the definition stays in the code dir (`proj`), the run is filed under its target
repo (`repo`): runs.json, ledger row, run-end report. Tmp DATA_DIR, MARK_DIR, plreq and code dir; fixed clock."""
import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests import test_pl_flow as F
from tests import test_pl_runs as TPR

H = F.H
N = "security-fix"
SID = "sess-0001"
PIPE = {"v": 1, "name": N, "builtin": True, "stages": [
    {"title": "fix", "agent": "general-purpose"}, {"title": "review", "agent": "general-purpose"}]}


def _key(d):
    return hashlib.sha1(os.path.realpath(d).encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


class BuiltinRepo(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.code = os.path.join(self.tmp, "code")   # = DATA_DIR: owns the builtin definition
        self.target = os.path.join(self.tmp, "admin")
        os.makedirs(os.path.join(self.code, ".claude", "pipelines"))
        os.makedirs(os.path.join(self.target, ".git"))
        os.makedirs(os.path.join(self.target, "src"))
        with open(os.path.join(self.target, "src", "a.py"), "w", encoding="utf-8") as f:
            f.write("x = 1\n")
        self._pipe(PIPE)
        cj = os.path.join(self.tmp, "claude.json")
        with open(cj, "w", encoding="utf-8") as f:
            json.dump({"projects": {self.code: {}}}, f)
        self.t = 1000.0
        self.spawned, self.heads = [], []
        for k, v in (("MARK_DIR", os.path.join(self.code, "plmark")), ("CONFIG_PATH", os.path.join(self.tmp, "cfg.json")),
                     ("_now", lambda: self.t), ("CLAUDE_DIR", os.path.join(self.tmp, "uc")), ("HOME_DIR", self.tmp),
                     ("DIRS_DIR", os.path.join(self.tmp, "plbrief")), ("DATA_DIR", self.code), ("CLAUDE_JSON", cj),
                     ("PROJ_STORE", os.path.join(self.tmp, "none.json")), ("_spawn", self.spawned.append),
                     ("SCORE_SCRIPT", "/x/scripts/pl_eval.py"), ("REPORT_SCRIPT", "/x/scripts/pl_report.py"),
                     ("_head", lambda p: self.heads.append(p) or "")):
            p = mock.patch.object(H, k, v)
            p.start()
            self.addCleanup(p.stop)

    def _pipe(self, body):
        with open(os.path.join(self.code, ".claude", "pipelines", N + ".json"), "w", encoding="utf-8") as f:
            json.dump(body, f)

    def _req(self, repo, at=990.0, **kw):
        with open(os.path.join(self.code, "plreq.json"), "w", encoding="utf-8") as f:
            json.dump({"v": 1, "reqs": [dict({"id": "m1", "repo": repo, "pipeline": N, "sid": SID, "to": "s", "mid": "m1",
                                              "at": at}, **kw)]}, f)

    def _ev(self, event, stage, cwd=None):
        ti = {"description": "[pl:%s/%s] task" % (N, stage), "subagent_type": "general-purpose"}
        ev = {"hook_event_name": event, "tool_name": "Agent", "session_id": SID, "cwd": cwd or self.target, "tool_input": ti}
        if event == "PostToolUse":
            ev["tool_response"] = {"content": [{"type": "text", "text": "ok"}]}
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", io.StringIO()):
            H.main()

    def run_(self):
        with open(os.path.join(self.code, "plmark", SID + ".runs.json"), encoding="utf-8") as f:
            return json.load(f)["runs"][N]

    def _full(self, cwd=None):
        for s in ("fix", "review"):
            self._ev("PreToolUse", s, cwd)
            self.t += 1
            self._ev("PostToolUse", s, cwd)
            self.t += 1

    def _tree(self):
        out = {}
        for dp, dn, fn in os.walk(self.target):
            for n in dn + fn:
                p = os.path.join(dp, n)
                out[os.path.relpath(p, self.target)] = os.path.getmtime(p)
        return out

    def test_plreq_target_files_ledger_and_keeps_first_repo(self):
        other = os.path.join(self.tmp, "other")
        os.makedirs(os.path.join(other, ".git"))
        self._req(self.target)
        self._ev("PreToolUse", "fix", cwd=other)   # plreq wins over the cwd git root
        self.assertEqual(self.run_()["repo"], self.target)
        self.assertEqual(os.path.realpath(self.run_()["proj"]), self.code)   # definition dir unchanged
        self._req(other, at=995.0)   # a newer request does not move an open run
        self.t += 1
        self._ev("PostToolUse", "fix", cwd=other)
        self._ev("PreToolUse", "review", cwd=other)
        self._ev("PostToolUse", "review", cwd=other)
        self.assertEqual(self.run_()["repo"], self.target)
        self.assertTrue(self.run_()["end"])
        self.assertTrue(os.path.isfile(os.path.join(self.code, "eval", _key(self.target), "runs.jsonl")))
        self.assertFalse(os.path.exists(os.path.join(self.code, "eval", _key(self.code))))
        self.assertIn(self.target, self.heads)

    def test_no_plreq_uses_cwd_git_root(self):
        self._ev("PreToolUse", "fix", cwd=os.path.join(self.target, "src"))
        self.assertEqual(self.run_()["repo"], self.target)

    def test_stale_or_stopped_plreq_ignored(self):
        os.makedirs(os.path.join(self.tmp, "elsewhere"))
        for kw in ({"at": -H.FIX_REQ_S}, {"stop": {"mid": "m2", "at": 1.0}}, {"sid": "sess-other"}, {"pipeline": "x"}):
            self.t += 100000   # every round opens a fresh run
            at = self.t - 10 + kw.pop("at", 0)
            self._req(os.path.join(self.tmp, "elsewhere"), at=at, **kw)
            self._ev("PreToolUse", "fix")
            self.assertEqual(self.run_()["repo"], self.target)

    def test_answered_request_not_reused_by_next_run(self):
        # a request older than the end of this sid's previous run was already answered (only security-fix gets `closed`)
        other = os.path.join(self.tmp, "other")
        os.makedirs(os.path.join(other, ".git"))
        self._req(self.target)
        self._full()
        self.assertEqual(self.run_()["repo"], self.target)
        self.t += 600   # same sid, same pipeline, started by itself in another repo
        self._ev("PreToolUse", "fix", cwd=other)
        self.assertEqual(self.run_()["repo"], other)

    def test_non_builtin_has_no_repo(self):
        self._pipe(dict(PIPE, builtin=False))
        self._req(self.target)
        self._ev("PreToolUse", "fix")
        self.assertNotIn("repo", self.run_())

    def test_target_tree_unchanged(self):
        self._req(self.target)
        before = self._tree()
        self._full()
        self.assertEqual(self._tree(), before)

    def test_autoscore_report_only_with_target_and_code_pf(self):
        self._req(self.target)
        os.makedirs(os.path.join(self.code, "eval", _key(self.target)))
        open(os.path.join(self.code, "eval", _key(self.target), "seeds.json"), "w", encoding="utf-8").close()   # pl_eval would run otherwise
        self._full()
        pf = os.path.join(self.code, ".claude", "pipelines", N + ".json")
        self.assertEqual([a[1:] for a in self.spawned],
                         [["/x/scripts/pl_report.py", "--repo", self.target, "--pipeline", pf, "--auto", "--data-dir", self.code]])


class PlRunsRepo(TPR.PlModel):
    pass


for _k in [k for k in dir(TPR.PlModel) if k.startswith("test")]:   # fixtures only, not PlModel's tests
    setattr(PlRunsRepo, _k, None)


def _repo_row(self):
    self._file({N: self._r(repo="/w/admin")})
    self.assertEqual(TPR.PR.pl_model(TPR.SID, self.sd, [], None, TPR.NOW)[0]["proj"], "/w/admin")
    self._file({N: self._r(repo="rel/admin")})   # invalid repo falls back to the definition dir
    self.assertEqual(TPR.PR.pl_model(TPR.SID, self.sd, [], None, TPR.NOW)[0]["proj"], "/Users/x/proj")


PlRunsRepo.test_proj_from_repo = _repo_row


class HarnessFlowRepo(unittest.TestCase):
    """sidereus/harness_flow._disk_runs files a builtin run under `repo`, like the pl_runs row."""

    def setUp(self):
        from tests._load import sidereus
        self.HF = sidereus("harness_flow")
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.code, self.target = os.path.join(self.tmp, "code"), os.path.join(self.tmp, "admin")
        p = mock.patch.object(self.HF, "HF_DIR", self.tmp)
        p.start()
        self.addCleanup(p.stop)

    def test_repo_over_proj(self):
        now = 2000000.0
        r = {"proj": self.code, "repo": self.target, "t0": now - 50, "t1": now - 10, "end": now - 10, "cur": "fix",
             "st": {"fix": {"s": "done", "t0": now - 50, "t1": now - 10, "n": 1}}}
        fp = os.path.join(self.tmp, "aaaaaaaa1111.runs.json")
        with open(fp, "w", encoding="utf-8") as f:
            json.dump({"v": 1, "runs": {N: r}}, f)
        os.utime(fp, (now, now))
        self.assertEqual(len(self.HF._disk_runs({self.target}, now)), 1)
        self.assertEqual(self.HF._disk_runs({self.code}, now), [])   # not under the definition dir


if __name__ == "__main__":
    unittest.main()
