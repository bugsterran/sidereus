"""Hook-less Cursor/Copilot rows (ext_presence): rollout-row shape, hook row wins, work-panel fallback."""
import json
import time
import unittest

from tests._load import sidereus

ext = sidereus("ext")
st = sidereus("ext_store")
pr = sidereus("ext_presence")

NOW = 1800000000.0
SID = "0199aaaa-bbbb-7ccc-8ddd-eeeeffff0042"


def _lstart(t):
    return time.strftime("%a %b %d %H:%M:%S %Y", time.localtime(t))


class Presence(unittest.TestCase):
    def setUp(self):
        self._ext = dict(st._ext)
        st._ext.clear()
        self._ended = dict(st._ext_ended)
        st._ext_ended.clear()
        pr._PRES_MEMO.clear()
        self.cands = {"cursor": [{"sid": SID, "cwd": "/w/cu", "start": NOW - 900, "mtime": NOW - 60}],
                      "copilot": [{"sid": "cp-1", "cwd": "/w/cp", "branch": "main", "start": NOW - 300, "mtime": NOW - 5,
                                   "locks": [(4242, NOW - 300)]}]}
        self._ps = st._pid_start
        self.pstart = {4242: _lstart(NOW - 302)}
        st._pid_start = lambda pid: self.pstart.get(pid, "")
        self._sc, self._sp = pr.plat_cursor.scan, pr.plat_copilot.scan
        pr.plat_cursor.scan = lambda since, n, stat_n: list(self.cands["cursor"])
        pr.plat_copilot.scan = lambda n: list(self.cands["copilot"])
        self._prune = ext._ext_prune_locked
        ext._ext_prune_locked = lambda now: None

    def tearDown(self):
        st._ext.clear()
        st._ext.update(self._ext)
        st._ext_ended.clear()
        st._ext_ended.update(self._ended)
        pr._PRES_MEMO.clear()
        pr.plat_cursor.scan, pr.plat_copilot.scan = self._sc, self._sp
        ext._ext_prune_locked = self._prune
        st._pid_start = self._ps

    def rows(self):
        pr._PRES_MEMO.clear()
        return pr.ext_presence_rows(NOW)

    def test_key_set_matches_rollout_row(self):
        c = {"sid": "cx-1", "cwd": "/w/cx", "start": NOW - 100, "mtime": NOW - 10, "live": True, "kind": ""}
        r0, c0 = ext._rollouts, ext._codex_running
        ext._rollouts, ext._codex_running = (lambda now: [c]), (lambda: True)
        try:
            cx = ext.ext_rollout_rows(NOW)
        finally:
            ext._rollouts, ext._codex_running = r0, c0
        self.assertEqual(len(cx), 1)
        rows = self.rows()
        self.assertEqual({r["plat"] for r in rows}, {"cu", "cp"})
        for r in rows:
            self.assertEqual(set(r), set(cx[0]))
            self.assertTrue(r["rollout"])
            self.assertEqual(r["state"], "unknown")
        json.dumps(rows)

    def test_same_sid_in_store_hidden(self):
        st._ext[("cursor", SID)] = {"cwd": "/elsewhere", "state": "wait"}
        self.assertEqual([r["plat"] for r in self.rows()], ["cp"])

    def test_same_plat_hook_row_same_cwd_hidden(self):
        st._ext[("copilot", "hook-id")] = {"cwd": "/w/cp", "state": "wait"}
        st._ext[("cursor", "other")] = {"cwd": "/w/cp", "state": "wait"}   # other platform: no effect
        self.assertEqual([r["plat"] for r in self.rows()], ["cu"])

    def test_ended_hidden(self):
        st._ext_ended[("copilot", "cp-1")] = NOW - 10
        self.assertEqual([r["plat"] for r in self.rows()], ["cu"])

    def test_dismiss_hides_presence_row(self):
        o = st._ext_save_locked
        st._ext_save_locked = lambda: None
        t0 = st.time.time
        st.time.time = lambda: NOW
        try:
            self.assertEqual(st.ext_dismiss(SID), 1)
        finally:
            st._ext_save_locked, st.time.time = o, t0
        self.assertEqual([r["plat"] for r in self.rows()], ["cp"])

    def test_copilot_pid_reuse(self):
        self.pstart[4242] = _lstart(NOW - 100)                 # process started after the lock: reused pid
        self.assertEqual([r["plat"] for r in self.rows()], ["cu"])

    def test_copilot_start_unknown_freshness(self):
        self.pstart[4242] = None                               # no ps (Windows): freshness bound only
        self.assertIn("cp", [r["plat"] for r in self.rows()])
        self.cands["copilot"][0].update(mtime=NOW - pr.PRES_STALE_S - 10, locks=[(4242, NOW - pr.PRES_STALE_S - 20)])
        self.assertEqual([r["plat"] for r in self.rows()], ["cu"])

    def test_copilot_pid_gone(self):
        self.pstart[4242] = ""
        self.assertEqual([r["plat"] for r in self.rows()], ["cu"])

    def test_work_fallback(self):
        pr._PRES_MEMO.clear()
        w = pr.ext_work_any("cu", SID, NOW)
        self.assertTrue(w["ok"])
        self.assertEqual((w["plat"], w["cwd"], w["state"], w["events"]), ("cu", "/w/cu", "unknown", []))
        self.assertTrue(pr.ext_work_any("copilot", "cp-1", NOW)["ok"])
        self.assertFalse(pr.ext_work_any("cu", "missing", NOW)["ok"])
        self.assertFalse(pr.ext_work_any("cc", SID, NOW)["ok"])

    def test_work_hook_row_first(self):
        st._ext[("cursor", SID)] = {"cwd": "/w/hook", "state": "think", "lastSeen": NOW, "firstSeen": NOW}
        self.assertEqual(pr.ext_work_any("cu", SID, NOW)["cwd"], "/w/hook")


if __name__ == "__main__":
    unittest.main()
