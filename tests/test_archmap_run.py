"""arch_map.runs: `/api/state` `archRun` from session rows + a temp store (store dir, Sidereus root and stage titles patched)."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

AM = sidereus("arch_map")
AV = sidereus("arch_verify")
C1 = "a" * 40
NOW = 1_000_000.0
TITLES = ["읽기 계획", "모듈 그리기", "흐름 그리기", "검증"]


class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-archrun-"))
        self.repo, self.home = os.path.join(self.tmp, "repo"), os.path.join(self.tmp, "sidereus")
        os.makedirs(self.repo)
        os.makedirs(self.home)
        self.store = os.path.join(self.tmp, "store")
        self.p = [mock.patch.object(AM, "ARCH_DIR", self.store), mock.patch.object(AM, "SIDEREUS_ROOT", self.home),
                  mock.patch.object(AM, "_titles", lambda: list(TITLES)), mock.patch.object(AM, "_RUN_SEEN", {})]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, name, mtime):
        d = os.path.join(self.store, AV.repo_key(self.repo), C1)
        os.makedirs(d, exist_ok=True)
        fp = os.path.join(d, name)
        with open(fp, "w") as f:
            f.write("{}")
        os.utime(fp, (mtime, mtime))

    def row(self, **kw):
        return dict({"sid": "s1", "state": "think", "cwd": self.repo, "repos": [self.repo, self.home], "sub": []}, **kw)

    def test_live_subagent_in_target_cwd(self):
        s = self.row(sub=[{"lab": "general-purpose: [pl:arch-map/모듈 그리기] repo map", "min": 2}])
        r = AM.runs([s], NOW)
        self.assertEqual(r, {self.repo: {"stage": "모듈 그리기", "n": 2, "of": 4, "t0": NOW - 120, "sid": "s1"}})

    def test_agent_call_targ_and_sidereus_session_with_pending_store(self):
        self.put("plan.json", NOW - 300)   # plan written, no verify.json yet -> this repo is the target
        s = self.row(cwd=self.home, tool="Agent", targ="[pl:arch-map/검증] repo verify")
        r = AM.runs([s], NOW)
        self.assertEqual(list(r), [self.repo])
        self.assertEqual((r[self.repo]["n"], r[self.repo]["t0"]), (4, NOW - 300))

    def test_stage1_sidereus_cwd_falls_back_to_repo(self):
        # no plan.json yet: the first non-Sidereus candidate is the target, so «Analysing» survives a reload
        s = self.row(cwd=self.home, repos=[self.home, self.repo], sub=[{"lab": "[pl:arch-map/읽기 계획] x", "min": 1}])
        self.assertEqual(list(AM.runs([s], NOW)), [self.repo])

    def test_sidereus_cwd_without_store_is_not_a_target(self):
        s = self.row(cwd=self.home, repos=[self.home], tool="Agent", targ="[pl:arch-map/읽기 계획] x")
        self.assertEqual(AM.runs([s], NOW), {})

    def test_gap_between_stages_then_ends(self):
        tagged = self.row(sub=[{"lab": "[pl:arch-map/읽기 계획] x", "min": 0}])
        AM.runs([tagged], NOW)
        self.assertIn(self.repo, AM.runs([self.row()], NOW + 30))                 # main thinking between stages
        self.assertEqual(AM.runs([self.row()], NOW + 30 + AM.ARCH_RUN_GAP_S + 1), {})   # no sign past the gap
        AM.runs([tagged], NOW)
        self.assertEqual(AM.runs([self.row(state="done")], NOW + 5), {})           # session ended

    def test_stage1_guess_not_carried_beside_real_target(self):
        # stage 1 guesses the cwd; once plan.json names another repo, the same session's run moves, never shows twice
        other = os.path.join(self.tmp, "other")
        os.makedirs(other)
        s = self.row(cwd=other, repos=[other, self.repo, self.home], sub=[{"lab": "[pl:arch-map/읽기 계획] x", "min": 0}])
        self.assertEqual(list(AM.runs([s], NOW)), [other])
        self.put("plan.json", NOW + 5)
        s2 = dict(s, sub=[{"lab": "[pl:arch-map/모듈 그리기] x", "min": 0}])
        self.assertEqual(list(AM.runs([s2], NOW + 10)), [self.repo])

    def test_open_plrun_needs_fresh_or_busy(self):
        pr = [{"name": "arch-map", "end": 0, "cur": "검증", "t0": NOW - 900, "t1": NOW - 600}]
        self.assertEqual(AM.runs([self.row(state="wait", plrun=pr)], NOW), {})              # abandoned: idle, stale run
        self.assertIn(self.repo, AM.runs([self.row(state="think", plrun=pr)], NOW))         # session busy
        AM._RUN_SEEN.clear()
        old = [dict(pr[0], t1=NOW - AM.ARCH_BUSY_S - 1)]
        self.assertEqual(AM.runs([self.row(state="tool", plrun=old)], NOW), {})              # busy on other work, run long idle
        AM._RUN_SEEN.clear()
        fresh = [dict(pr[0], t1=NOW - 30)]
        self.assertEqual(AM.runs([self.row(state="wait", plrun=fresh)], NOW)[self.repo]["t0"], NOW - 900)

    def test_done_session_and_other_pipeline_ignored(self):
        self.assertEqual(AM.runs([self.row(state="done", sub=[{"lab": "[pl:arch-map/검증] x"}]),
                                  self.row(sid="s2", sub=[{"lab": "[pl:change/구현] x"}])], NOW), {})

    def test_gate_result_ends_run_despite_busy_session(self):
        pr = [{"name": "arch-map", "end": 0, "cur": "검증", "t0": NOW - 900, "t1": NOW - 60}]
        self.put("plan.json", NOW - 800)
        self.assertEqual(AM.runs([self.row(plrun=pr)], NOW)[self.repo]["n"], 4)     # last stage, gate not written yet
        self.put("verify.json", NOW + 10)
        done = [dict(pr[0], end=NOW + 130)]
        busy = self.row(cwd=self.home, plrun=done, plm={"name": "arch-map", "title": "검증"})
        self.assertEqual(AM.runs([busy], NOW + 140), {})                             # no carry-over
        self.assertEqual(AM.runs([busy], NOW + 150), {})                             # and not resurrected later

    def test_result_with_live_tagged_subagent_and_open_record_still_runs(self):
        self.put("verify.json", NOW - 30)
        pr = [{"name": "arch-map", "end": 0, "cur": "검증", "t0": NOW - 900, "t1": NOW - 60}]
        s = self.row(plrun=pr, sub=[{"lab": "[pl:arch-map/검증] x", "min": 2}])
        self.assertIn(self.repo, AM.runs([s], NOW))
        self.assertEqual(AM.runs([self.row(plrun=pr)], NOW + 5), {})                 # subagent gone: result stands

    def test_older_result_does_not_end_new_run(self):
        self.put("verify.json", NOW - 3000)
        self.put("plan.json", NOW - 300)
        self.assertIn(self.repo, AM.runs([self.row(plm={"name": "arch-map", "title": "검증"})], NOW))
        AM._RUN_SEEN.clear()
        self.assertIn(self.repo, AM.runs([self.row(sub=[{"lab": "[pl:arch-map/읽기 계획] x", "min": 1}])], NOW))

    def test_verified_store_not_pending(self):
        self.put("plan.json", NOW - 300)
        self.put("verify.json", NOW - 200)
        self.assertEqual(AM._pending_at(self.repo), 0.0)

    def store_dir(self, plan):
        d = os.path.join(self.store, AV.repo_key(self.repo), C1)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "plan.json"), "w") as f:
            f.write(plan)
        return d

    def test_store_dir_cwd_resolves_to_plan_repo(self):
        d = self.store_dir('{"v": 1, "repo": "%s", "commit": "%s"}' % (self.repo, C1))
        s = self.row(cwd=d, repos=[d, self.home], sub=[{"lab": "[pl:arch-map/모듈 그리기] x", "min": 1}])
        self.assertEqual(list(AM.runs([s], NOW)), [self.repo])
        self.assertEqual(AM._target(self.row(cwd=os.path.join(d, "sub"), repos=[]), NOW)[0], self.repo)

    def test_store_dir_without_valid_plan_is_never_a_target(self):
        sub = [{"lab": "[pl:arch-map/모듈 그리기] x", "min": 1}]
        for plan in ("not json", "[]", '{"repo": 5}', '{"repo": "rel/path"}', '{"repo": "/nonexistent-sidereus-x"}',
                     '{"repo": "%s"}' % self.home):   # home dir exists but its key does not match this store dir
            d = self.store_dir(plan)
            AM._RUN_SEEN.clear()
            self.assertEqual(AM.runs([self.row(cwd=d, repos=[d, self.home], sub=sub)], NOW), {}, plan)
        os.remove(os.path.join(d, "plan.json"))
        self.assertEqual(AM._target(self.row(cwd=d, repos=[]), NOW), ("", 0.0))
        self.assertEqual(AM._target(self.row(cwd=self.store, repos=[]), NOW), ("", 0.0))   # store root itself

    def test_store_dir_plan_over_cap_ignored(self):
        d = self.store_dir('{"repo": "%s"}' % self.repo)
        with mock.patch.object(AM, "PLAN_MAX", 5):
            self.assertEqual(AM._target(self.row(cwd=d, repos=[]), NOW), ("", 0.0))

    def test_normal_target_choice_unchanged(self):
        other = os.path.join(self.tmp, "other")
        os.makedirs(other)
        self.assertEqual(AM._target(self.row(cwd=self.repo, repos=[other]), NOW), (self.repo, 0.0))   # cwd first
        self.assertEqual(AM._target(self.row(cwd=self.home, repos=[self.home, other]), NOW), (other, 0.0))   # skip Sidereus
        self.put("plan.json", NOW - 300)
        self.assertEqual(AM._target(self.row(cwd=other, repos=[other, self.repo]), NOW), (self.repo, NOW - 300))   # pending wins


if __name__ == "__main__":
    unittest.main()
