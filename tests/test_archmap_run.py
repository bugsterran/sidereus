"""arch_map.runs: `/api/state` `archRun` from session rows + a temp store (store dir, Sidereus root and stage titles patched)."""
import json
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
        with open(fp, "w", encoding="utf-8") as f:
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

    def test_hookless_marker_needs_result_newer_than_its_stage(self):
        # Codex-shaped row: no plrun, only the shell [pl:] marker (age = seconds since that stage started)
        self.put("verify.json", NOW - 3000)                                     # older run's gate result
        s = self.row(plm={"name": "arch-map", "title": "모듈 그리기", "age": 10})
        self.assertEqual(AM.runs([s], NOW)[self.repo]["stage"], "모듈 그리기")
        self.put("verify.json", NOW + 5)                                        # this run's gate, after the last sign
        self.assertEqual(AM.runs([dict(s, plm=dict(s["plm"], age=15))], NOW + 10), {})

    def test_verified_store_not_pending(self):
        self.put("plan.json", NOW - 300)
        self.put("verify.json", NOW - 200)
        self.assertEqual(AM._pending_at(self.repo), 0.0)

    def store_dir(self, plan):
        d = os.path.join(self.store, AV.repo_key(self.repo), C1)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "plan.json"), "w", encoding="utf-8") as f:
            f.write(plan)
        return d

    def test_store_dir_cwd_resolves_to_plan_repo(self):
        d = self.store_dir(json.dumps({"v": 1, "repo": self.repo, "commit": C1}))   # json.dumps escapes Windows backslashes
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

    def test_requested_sidereus_repo_is_the_target(self):
        # the home exclusion applies to cwd/repos guesses, never to the repo the page asked for
        s = self.row(cwd=self.home, repos=[self.home, self.repo], sub=[{"lab": "[pl:arch-map/흐름 그리기] x", "min": 1}])
        with mock.patch.object(AM, "_REQ_SRC", lambda sid, pl, now: self.home):
            self.assertEqual(AM._target(s, NOW), (self.home, 0.0))
            self.assertEqual(list(AM.runs([s], NOW)), [self.home])

    def test_newer_request_takes_the_run_from_the_older(self):
        PL, sid = sidereus("pl_reqs"), "5024a7e1-0000-4000-8000-000000000001"
        mem = [{"id": "m2", "repo": self.home, "pipeline": "arch-map", "sid": sid, "to": "o", "mid": "m2", "at": NOW - 300},
               {"id": "m1", "repo": self.repo, "pipeline": "arch-map", "sid": sid, "to": "o", "mid": "m1", "at": NOW - 600}]
        pr = [{"name": "arch-map", "end": 0, "cur": "흐름 그리기", "t0": NOW - 200, "t1": NOW - 10}]
        s = self.row(sid=sid, cwd=self.home, repos=[self.home, self.repo], plrun=pr)
        with mock.patch.object(PL, "PLREQ_PATH", None), mock.patch.object(PL, "PLSTOP_DIR", None), \
                mock.patch.object(PL, "_MEM", mem), mock.patch.object(PL, "_now", lambda: NOW), \
                mock.patch.object(AM, "_REQ_SRC", PL.req_repo):
            arch = AM.runs([s], NOW)
            v = PL.view([s], arch, {}, NOW)
        self.assertEqual(list(arch), [self.home])
        self.assertEqual(v[self.home][0]["state"], "run")
        self.assertNotEqual(v[self.repo][0]["state"], "run")


SEC_TITLES = ["보안 검사", "위협 모델 리뷰"]


class SecRunTest(RunTest):
    """sec_runs: `/api/state` `secRun` — same tracking as archRun for security-checks; the run ends on the security log
    (review / mark records) or on the run record closing, never on stage 1's checks-security.json."""
    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.home, ".claude", "pipelines"))
        with open(os.path.join(self.home, ".claude", "pipelines", "security-checks.json"), "w", encoding="utf-8") as f:
            json.dump({"stages": [{"title": t} for t in SEC_TITLES]}, f)
        for p in (mock.patch.object(AM, "_SEC_SEEN", {}), mock.patch.object(AM, "_SEC_LOG_CACHE", {})):
            p.start()
            self.p.append(p)

    def log(self, src, at, repo=None):
        d = os.path.join(self.store, AV.repo_key(repo or self.repo))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, AM.SEC_LOG_FILE), "a", encoding="utf-8") as f:
            f.write(json.dumps({"v": 1, "at": at, "commit": C1, "src": src, "items": []}) + "\n")

    def test_r1_claude_subagent_stage_and_elapsed(self):
        s = self.row(sub=[{"lab": "general-purpose: [pl:security-checks/위협 모델 리뷰] review", "min": 3}])
        self.assertEqual(AM.sec_runs([s], NOW), {self.repo: {"stage": "위협 모델 리뷰", "n": 2, "of": 2, "t0": NOW - 180, "sid": "s1"}})
        self.assertEqual(AM.runs([s], NOW), {})                                   # arch-map map untouched
        AM._SEC_SEEN.clear()
        arch = self.row(sub=[{"lab": "[pl:arch-map/검증] x", "min": 1}])
        self.assertEqual(AM.sec_runs([arch], NOW), {})                            # and the other way round

    def test_r4_codex_shell_marker(self):
        s = self.row(plm={"name": "security-checks", "title": "보안 검사", "age": 40})
        self.assertEqual(AM.sec_runs([s], NOW)[self.repo], {"stage": "보안 검사", "n": 1, "of": 2, "t0": NOW - 40, "sid": "s1"})

    def test_r2_scan_does_not_end_but_log_does(self):
        self.put("checks-security.json", NOW + 5)                                 # stage 1 wrote its scan
        self.log("scan", NOW + 5)                                                 # and appended a scan record
        pr = [{"name": "security-checks", "end": 0, "cur": "보안 검사", "t0": NOW - 20, "t1": NOW + 6}]
        s = self.row(plrun=pr)                                                    # between stages: no live tagged agent
        self.assertIn(self.repo, AM.sec_runs([s], NOW + 10))
        self.assertEqual(AM.result_at(AM.SEC_PL, self.repo), 0.0)                 # request records ignore scans too
        self.log("review", NOW + 20)                                              # review stage logged: run over
        self.assertEqual(AM.sec_runs([s], NOW + 30), {})
        self.assertEqual(AM.result_at(AM.SEC_PL, self.repo), NOW + 20)

    def test_mark_record_ends_and_cache_follows_log(self):
        self.log("mark", NOW - 5)
        self.assertEqual(AM._sec_final_at(self.repo), NOW - 5)
        self.log("review", NOW + 7)                                               # append changes size: re-read
        self.assertEqual(AM._sec_final_at(self.repo), NOW + 7)

    def test_sidereus_repo_itself_is_a_security_target(self):
        s = self.row(cwd=self.home, repos=[self.home], sub=[{"lab": "[pl:security-checks/보안 검사] x", "min": 1}])
        self.assertEqual(list(AM.sec_runs([s], NOW)), [self.home])
        self.assertEqual(AM.runs([dict(s, sub=[{"lab": "[pl:arch-map/검증] x", "min": 1}])], NOW), {})   # arch-map exclusion kept

    def test_r2_closed_record_ends_without_gap(self):
        pr = [{"name": "security-checks", "end": 0, "cur": "위협 모델 리뷰", "t0": NOW - 300, "t1": NOW - 10}]
        self.assertIn(self.repo, AM.sec_runs([self.row(plrun=pr)], NOW))
        done = [dict(pr[0], end=NOW + 5)]                                         # no threat model: nothing logged, record closed
        self.assertEqual(AM.sec_runs([self.row(plrun=done)], NOW + 10), {})

    def test_r3_stalled_or_dead_session_drops_run(self):
        tagged = self.row(sub=[{"lab": "[pl:security-checks/보안 검사] x", "min": 0}])
        AM.sec_runs([tagged], NOW)
        self.assertIn(self.repo, AM.sec_runs([self.row()], NOW + 30))            # stage gap
        self.assertEqual(AM.sec_runs([self.row()], NOW + 30 + AM.ARCH_RUN_GAP_S + 1), {})   # stalled past the gap
        AM.sec_runs([tagged], NOW)
        self.assertEqual(AM.sec_runs([self.row(state="gone")], NOW + 5), {})      # disconnected


if __name__ == "__main__":
    unittest.main()
