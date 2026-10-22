"""#16 [pl-none:<cat>] per-project log: hooks/pl_flow.py _none_log (R1, R2) and pl_runs.pl_none_counts (R3).
Tmp dirs only, fixed clock."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from tests import test_pl_flow_none as N   # ⚠not `from … import PlNone`: its tests would run again here
from tests._load import sidereus

H = N.H
R = sidereus("pl_runs")
DAY = 86400


class NoneLog(unittest.TestCase):
    setUp = N.PlNone.setUp
    _ev = N.PlNone._ev
    bash = N.PlNone.bash
    denied = N.PlNone.denied

    def lines(self):
        p = os.path.join(self.marks, H.NONE_LOG)
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [json.loads(x) for x in f.read().splitlines()]

    def test_r1_declaration_appends_one_line_and_keeps_session_file(self):
        self.bash("ls", "[pl-none:small-fix] why")
        self.t = 1005.0
        self.bash("ls", "[pl-none:explore] why")
        self.assertEqual(self.lines(), [{"v": 1, "proj": self.proj, "cat": "small-fix", "t": 1000.0},
                                        {"v": 1, "proj": self.proj, "cat": "explore", "t": 1005.0}])
        with open(self.nf, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"v": 1, "cat": "explore", "t": 1005.0})   # per-session overwrite unchanged

    def test_r1_no_project_or_bad_category_appends_nothing(self):
        self.bash("ls", "[pl-none:small-fix] why", cwd=self.bare)
        self.bash("ls", "[pl-none:bogus] why")
        self.assertEqual(self.lines(), [])

    def test_r2_log_holds_no_description(self):
        self.bash("ls -la /secret/dir", "[pl-none:other] secret reason text")
        with open(os.path.join(self.marks, H.NONE_LOG), encoding="utf-8") as f:
            raw = f.read()
        self.assertNotIn("secret", raw)
        self.assertEqual(set(json.loads(raw)), {"v", "proj", "cat", "t"})

    def test_r1_log_failure_never_blocks(self):
        with mock.patch.object(H.os, "open", side_effect=OSError("disk")):
            H._none_log(self.proj, "other", 1000.0)   # no raise
        with mock.patch.object(H, "_none_log", side_effect=RuntimeError("x")):
            self.assertFalse(self.denied(self.bash("ls", "[pl-none:other] x")))   # fail-open even if logging raised

    def test_r1_trim_drops_old_lines_and_caps_size(self):
        os.makedirs(self.marks, exist_ok=True)
        p = os.path.join(self.marks, H.NONE_LOG)
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps({"v": 1, "proj": self.proj, "cat": "other", "t": 0}) + "\n")
        now = 100 * DAY
        H._none_log(self.proj, "explore", now)
        self.assertEqual([x["t"] for x in self.lines()], [now])   # older than 90 d gone
        with mock.patch.object(H, "NONE_LOG_MAX", 400):
            for i in range(20):
                H._none_log(self.proj, "explore", now + i)
            self.assertLessEqual(os.path.getsize(p), 400)
        self.assertEqual(self.lines()[-1]["t"], now + 19)   # newest kept


class NoneNudge(unittest.TestCase):
    setUp = N.PlNone.setUp
    _ev = N.PlNone._ev
    bash = N.PlNone.bash
    denied = N.PlNone.denied

    def nofit(self, n, step=DAY):
        o = None
        for _ in range(n):
            o = self.bash("ls", "[pl-none:no-fit] secret reason text")
            self.t += step
        return o

    def test_r1_third_no_fit_in_7_days_adds_context_not_deny(self):
        self.assertIsNone(self.nofit(2))
        o = self.nofit(1)
        self.assertFalse(self.denied(o))
        txt = o["additionalContext"]
        self.assertIn("%s had 3 [pl-none:no-fit] declarations in the last 7 days" % self.proj, txt)
        self.assertIn("only after the user agrees", txt)

    def test_r2_once_per_project_per_7_days(self):
        self.assertIsNotNone(self.nofit(3))
        self.assertIsNone(self.nofit(1))   # same window: quiet
        with open(os.path.join(self.marks, H.NONE_NUDGE), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {self.proj: 1000.0 + 2 * DAY})
        self.t = 1000.0 + 2 * DAY + 7 * DAY
        self.assertIn("had 3 ", self.nofit(1)["additionalContext"])   # quiet period over; rows at day 2, 3 + this one

    def test_r2_other_categories_old_rows_and_subagents_never_fire(self):
        for c in ("small-fix", "explore", "other"):
            for _ in range(3):
                self.assertIsNone(self.bash("ls", "[pl-none:%s] x" % c))
        self.assertIsNone(self.nofit(2, step=8 * DAY))   # earlier ones fall out of the window
        self.assertIsNone(self.nofit(1))
        self.assertIsNone(self.bash("ls", "[pl-none:no-fit] x", agent="a1"))
        self.assertFalse(os.path.exists(os.path.join(self.marks, H.NONE_NUDGE)))

    def test_r3_text_has_no_description_and_failure_is_silent(self):
        o = self.nofit(3)
        self.assertNotIn("secret", json.dumps(o))
        with mock.patch.object(H, "_none_save", side_effect=OSError("disk")), \
                mock.patch.object(H, "_NONE_NOTE", ["nudge", "/p2", self.t]):
            self.assertEqual(H._none_emit(""), "")   # stamp failed: nothing printed
        self.t += 8 * DAY
        self.nofit(2, step=1)
        with mock.patch.object(H, "_none_nudge", side_effect=RuntimeError("x")):
            self.assertFalse(self.denied(self.bash("ls", "[pl-none:no-fit] x")))   # tool still runs

    def stamp(self):
        return os.path.exists(os.path.join(self.marks, H.NONE_NUDGE))

    def test_r3_deny_from_flow_unchanged_and_not_stamped(self):
        self.nofit(2)
        with mock.patch.object(H, "_flow", lambda plat, ev: H._deny("other") or True):
            o = self.nofit(1)   # json.loads in _ev fails on two objects
        self.assertEqual(o, {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                             "permissionDecisionReason": "other"})
        self.assertFalse(self.stamp())
        self.assertIn("had 4 ", self.nofit(1)["additionalContext"])   # not lost: next no-fit nudges

    def test_r3_flow_context_merged_into_one_object_and_stamped(self):
        self.nofit(2)

        def flow(plat, ev):
            sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                                "additionalContext": "Pipeline run x is open"}}))
        with mock.patch.object(H, "_flow", flow):
            o = self.nofit(1)
        self.assertEqual(set(o), {"hookEventName", "additionalContext"})
        self.assertTrue(o["additionalContext"].startswith("Pipeline run x is open\n\n"))
        self.assertIn("had 3 [pl-none:no-fit]", o["additionalContext"])
        self.assertTrue(self.stamp())

    def test_r3_unparseable_flow_output_unchanged_and_not_stamped(self):
        with mock.patch.object(H, "_NONE_NOTE", ["nudge", self.proj, self.t]):
            for raw in ("not json", "{}", '{"hookSpecificOutput": {"hookEventName": "PreToolUse", '
                        '"additionalContext": "a", "permissionDecision": "deny"}}'):
                self.assertEqual(H._none_emit(raw), raw)
        self.assertFalse(self.stamp())


class NoneCounts(unittest.TestCase):
    def setUp(self):
        self.d0 = R.PLR_DIR
        R.PLR_DIR = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, R.PLR_DIR)
        self.addCleanup(setattr, R, "PLR_DIR", self.d0)

    def _put(self, rows):
        with open(os.path.join(R.PLR_DIR, R.PLR_NONE_LOG), "w", encoding="utf-8") as f:
            for r in rows:
                f.write((r if isinstance(r, str) else json.dumps(r)) + "\n")

    def test_r3_counts_per_project_and_category_within_days(self):
        now = 50 * DAY
        self._put([{"v": 1, "proj": "/a", "cat": "small-fix", "t": now - 1},
                   {"v": 1, "proj": "/a", "cat": "small-fix", "t": now - 2 * DAY},
                   {"v": 1, "proj": "/a", "cat": "explore", "t": now - 3},
                   {"v": 1, "proj": "/b", "cat": "no-fit", "t": now - 6 * DAY},
                   {"v": 1, "proj": "/b", "cat": "no-fit", "t": now - 8 * DAY},   # outside 7 d
                   {"v": 1, "proj": "/b", "cat": "refactor", "t": now},          # not allow-listed
                   {"v": 1, "proj": "rel", "cat": "other", "t": now},            # not absolute
                   {"v": 1, "proj": "/b", "cat": "other", "t": True},
                   "not json", "[1]"])
        self.assertEqual(R.pl_none_counts(7, now), {"/a": {"small-fix": 2, "explore": 1}, "/b": {"no-fit": 1}})
        self.assertEqual(R.pl_none_counts(1, now), {"/a": {"small-fix": 1, "explore": 1}})

    def test_r3_missing_file_and_byte_cap(self):
        self.assertEqual(R.pl_none_counts(7, 0), {})
        self._put([{"v": 1, "proj": "/a", "cat": "other", "t": 10}] * 50)
        with mock.patch.object(R, "PLR_NONE_LOG_MAX", 200):
            n = R.pl_none_counts(7, 10)["/a"]["other"]
        self.assertTrue(0 < n < 50)   # bounded tail read, cut first line skipped


if __name__ == "__main__":
    unittest.main()
