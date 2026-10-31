"""Harness «Gate cost» (sidereus/harness_cost.py): tmp plmark dir, tmp pipeline file, fixed clock — no live files."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import load, sidereus

load()
HC = sidereus("harness_cost")
HF = sidereus("harness_flow")
OH = sidereus("otel_hooks")
NOW = 1_800_000_000.0
SID = "aaaaaaaa1111"
_real_policy = HC._policy   # captured before setUp stubs it


def _run(dl, st=None, name="change", sid=SID, t0=NOW - 7200):
    return {"sid": sid, "name": name, "t0": t0, "t1": NOW - 60, "end": NOW - 60, "deny": len(dl), "dl": dl,
            "st": st or {"build": {"s": "done", "t0": t0, "t1": NOW - 60, "n": 1}}}


class CostTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hc-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.proj = os.path.realpath(os.path.join(self.tmp, "proj"))
        os.makedirs(os.path.join(self.proj, ".claude", "pipelines"))
        for obj, k, v in ((HF, "HF_DIR", os.path.join(self.tmp, "plmark")), (HF, "_now", lambda: NOW),
                          (HC, "_now", lambda: NOW), (HC, "_policy", lambda proj: None)):
            p = mock.patch.object(obj, k, v)
            p.start()
            self.addCleanup(p.stop)

    def cost(self, runs, **kw):
        kw.setdefault("stops", [])
        kw.setdefault("hook", {"n": 0, "rows": []})
        return HC.cost(self.proj, runs=runs, **kw)

    def test_r1_stop_in_30m_overridden(self):
        t = NOW - 5000
        c = self.cost([_run([{"c": "jump", "t": t, "title": "review", "r": t + 60}])],
                      stops=[{"sid8": SID[:8], "pipeline": "change", "at": t + 600}, {"sid8": SID[:8], "pipeline": "other", "at": t + 10}])
        self.assertEqual((c["blocked"], c["overridden"], c["unknown"]), (1, 1, 0))
        self.assertEqual(c["ev"]["overridden"][0]["by"], "stop")

    def test_r1_skip_overridden(self):
        t = NOW - 5000
        st = {"review": {"s": "skip", "t0": t + 300, "t1": t + 300, "n": 0}}
        c = self.cost([_run([{"c": "gate", "t": t, "title": "review", "r": t + 60}], st=st)])
        self.assertEqual(c["overridden"], 1)
        self.assertEqual(c["ev"]["overridden"][0]["by"], "skip")

    def test_r1_policy_off_mtime_overridden(self):
        t = NOW - 5000
        fp = os.path.join(self.proj, ".claude", "pipelines", "_policy.json")
        with open(fp, "w", encoding="utf-8") as f:
            f.write('{"enforce": "off"}')
        os.utime(fp, (t + 900, t + 900))
        with mock.patch.object(HC, "_policy", _real_policy):
            c = self.cost([_run([{"c": "gate", "t": t, "title": "review", "r": t + 60}])])
        self.assertEqual(c["overridden"], 1)
        self.assertEqual(c["ev"]["overridden"][0]["by"], "strict_off")
        with open(fp, "w", encoding="utf-8") as f:
            f.write('{"enforce":"writes"}')
        self.assertIsNone(_real_policy(self.proj))   # strict on again: no signal
        os.remove(fp)
        self.assertIsNone(_real_policy(self.proj))   # deleted: no signal

    def test_r1_policy_extra_key_still_strict(self):
        fp = os.path.join(self.proj, ".claude", "pipelines", "_policy.json")
        with open(fp, "w", encoding="utf-8") as f:
            f.write('{"enforce": "writes", "note": "x"}')
        self.assertIsNone(_real_policy(self.proj))

    def test_r1_signal_after_30m_not_overridden(self):
        t = NOW - 9000
        st = {"review": {"s": "skip", "t0": t + 1801, "t1": t + 1801, "n": 0}}
        c = self.cost([_run([{"c": "gate", "t": t, "title": "review", "r": t + 60}], st=st)],
                      stops=[{"sid8": SID[:8], "pipeline": "change", "at": t - 1}], policy=t + 4000)
        self.assertEqual((c["blocked"], c["overridden"], c["unknown"]), (1, 0, 0))   # resumed and the window passed: complied
        self.assertEqual(c["ev"]["blocked"][0]["by"], "")

    def test_r2_no_resume_or_pending_is_unknown(self):
        dl = [{"c": "gate", "t": NOW - 9000, "title": "a"},                      # no resume recorded
              {"c": "jump", "t": NOW - 600, "title": "b", "r": NOW - 500},     # within 30 min
              {"c": "tag", "t": NOW - 8000, "title": "c", "r": "soon"}]        # garbage resume = none
        c = self.cost([_run(dl)])
        self.assertEqual((c["blocked"], c["overridden"], c["unknown"]), (3, 0, 3))
        self.assertEqual(sorted(r["by"] for r in c["ev"]["unknown"]), ["none", "none", "pending"])

    def test_r3_gate_sums_passes_with_loopback(self):
        st = {"check": {"s": "done", "t0": NOW - 5000, "t1": NOW - 1000, "n": 2, "p0": NOW - 2000, "k": 2,
                        "ps": [{"a": NOW - 5000, "b": NOW - 4000, "s": "back"}]},
              "build": {"s": "done", "t0": NOW - 6000, "t1": NOW - 5000, "n": 1}}
        c = self.cost([_run([], st=st)], gates={"change": ["check"]})
        self.assertEqual(c["gate_ms"], 2000 * 1000)
        self.assertFalse(c["gate_lb"])
        self.assertEqual([(r["stage"], r["dur_ms"]) for r in c["ev"]["gate"]], [("check", 2000000)])

    def test_r3_gate_lower_bound_when_passes_dropped(self):
        st = {"check": {"s": "done", "t0": NOW - 5000, "t1": NOW - 1000, "n": 4, "p0": NOW - 2000, "k": 4,
                        "ps": [{"a": NOW - 5000, "b": NOW - 4000, "s": "back"}]}}
        with open(os.path.join(self.proj, ".claude", "pipelines", "change.json"), "w", encoding="utf-8") as f:
            json.dump({"stages": [{"title": "build"}, {"title": "check", "gate": "scripts/check.sh --fast"}]}, f)
        c = self.cost([_run([], st=st)])
        self.assertEqual(c["gate_ms"], 2000 * 1000)
        self.assertTrue(c["gate_lb"])

    def test_r3_no_gate_stage_is_none(self):
        st = {"build": {"s": "done", "t0": NOW - 500, "t1": NOW - 100, "n": 1}}
        c = self.cost([_run([], st=st)], gates={"change": []})
        self.assertIsNone(c["gate_ms"])   # readable file without a gate stage: not measured, not 0
        c = self.cost([_run([], st=st)], gates={"change": ["old-title"]})
        self.assertIsNone(c["gate_ms"])   # renamed gate stage

    def test_r3_pause_union_intervals(self):
        dl = [{"c": "gate", "t": NOW - 9000, "title": "a", "r": NOW - 8000},
              {"c": "jump", "t": NOW - 8500, "title": "a", "r": NOW - 7500},
              {"c": "tag", "t": NOW - 6000, "title": "a", "r": NOW - 5900},
              {"c": "tag", "t": NOW - 5000, "title": "a"}]   # no resume: left out of the time
        c = self.cost([_run(dl)])
        self.assertEqual(c["pause_ms"], (1500 + 100) * 1000)
        self.assertEqual(len(c["ev"]["pause"]), 3)

    def test_r3_missing_data_is_none_not_zero(self):
        c = self.cost([])   # no runs, no pipeline file, no hook data
        for k in ("blocked", "overridden", "unknown", "gate_ms", "hook_ms", "pause_ms"):
            self.assertIsNone(c[k], k)
        c = self.cost([_run([], st={"check": {"s": "done", "t0": NOW - 50, "t1": NOW - 10, "n": 1}})])
        self.assertIsNone(c["gate_ms"])   # pipeline file missing: not measured
        self.assertEqual(c["blocked"], 0)

    def test_r3_hook_overhead_from_oh(self):
        fp = os.path.join(self.tmp, "otel-hooks.json")
        day = OH._ymd(NOW - 3600)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump({"v": 1, "d": {day: {"PreToolUse": [10, 4000, 0], "Stop": [2, 500, 0]}, "1999-01-01": {"Stop": [5, 9999, 0]}}}, f)
        saved = (dict(OH._oh), dict(OH._ohn), dict(OH._ohx), dict(OH._oh_meta))
        for d in (OH._oh, OH._ohn, OH._ohx):
            d.clear()
        OH._oh_meta.update(loaded=False, dirty=False)

        def restore():
            for d, v in zip((OH._oh, OH._ohn, OH._ohx, OH._oh_meta), saved):
                d.clear()
                d.update(v)
        self.addCleanup(restore)
        with mock.patch.object(OH, "OH_FILE", fp):
            c = HC.cost(self.proj, runs=[], stops=[])
        self.assertEqual(c["hook_ms"], 4500)
        self.assertEqual(sorted(r["code"] for r in c["ev"]["hook"]), ["PreToolUse", "Stop"])

    def test_r4_evidence_rows_whitelisted(self):
        t = NOW - 5000
        r = _run([{"c": "gate", "t": t, "title": "review", "r": t + 60, "input": "SECRET", "cmd": "rm -rf"}])
        r["cwd"] = "/secret"
        c = self.cost([r, _run([{"c": "evil", "t": t, "title": "x"}], sid="bbbbbbbb2222")],
                      stops=[{"sid8": SID[:8], "pipeline": "change", "at": t + 5, "body": "SECRET"}])
        self.assertEqual(c["blocked"], 1)   # unknown code dropped
        for rows in c["ev"].values():
            for row in rows:
                self.assertEqual(sorted(row), ["by", "code", "dur_ms", "stage", "ts"])
        self.assertNotIn("SECRET", json.dumps(c))
        self.assertNotIn("/secret", json.dumps(c))


if __name__ == "__main__":
    unittest.main()
