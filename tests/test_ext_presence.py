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
        self.past = {"cursor": {}, "copilot": {}}                          # ended sessions found only by sid
        self._oc, self._op = pr.plat_cursor.one, pr.plat_copilot.one
        pr.plat_cursor.one = lambda sid: self.past["cursor"].get(sid)
        pr.plat_copilot.one = lambda sid: self.past["copilot"].get(sid)
        self._pis, self._pio = pr.plat_pi.scan, pr.plat_pi.one     # ⚠never the live ~/.pi
        self.cands["pi"] = []
        pr.plat_pi.scan = lambda since=0.0: list(self.cands["pi"])
        pr.plat_pi.one = lambda sid: None
        self._prune = ext._ext_prune_locked
        ext._ext_prune_locked = lambda now: None

    def tearDown(self):
        st._ext.clear()
        st._ext.update(self._ext)
        st._ext_ended.clear()
        st._ext_ended.update(self._ended)
        pr._PRES_MEMO.clear()
        pr.plat_cursor.scan, pr.plat_copilot.scan = self._sc, self._sp
        pr.plat_cursor.one, pr.plat_copilot.one = self._oc, self._op
        pr.plat_pi.scan, pr.plat_pi.one = self._pis, self._pio
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

    def test_copilot_row_carries_hooks_off(self):
        hd = pr.plat_copilot.hooks_disabled
        pr.plat_copilot.hooks_disabled = lambda cwd: cwd == "/w/cp"
        try:
            got = {r["plat"]: r["hooksOff"] for r in self.rows()}
        finally:
            pr.plat_copilot.hooks_disabled = hd
        self.assertEqual(got, {"cp": True, "cu": False})   # Cursor never reads the Copilot settings file

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

    def test_work_fallback_ended_session(self):
        self.past["cursor"]["cu-old"] = {"sid": "cu-old", "cwd": "/w/old", "start": NOW - 9000, "mtime": NOW - 8000}
        self.past["copilot"]["cp-old"] = {"sid": "cp-old", "cwd": "/w/cpo", "branch": "", "start": NOW - 9000, "mtime": NOW - 8000}
        w = pr.ext_work_any("cu", "cu-old", NOW)
        self.assertEqual((w["ok"], w["cwd"], w["state"], w["lastSeen"]), (True, "/w/old", "unknown", NOW - 8000))
        self.assertEqual(pr.ext_work_any("copilot", "cp-old", NOW)["cwd"], "/w/cpo")
        self.assertFalse(pr.ext_work_any("cursor", "cp-old", NOW)["ok"])  # resolved by (platform, sid), never across platforms
        self.assertFalse({"cu-old", "cp-old"} & {r["sid"] for r in self.rows()})   # list rows stay live-only

    def test_work_fallback_src_and_tool(self):
        self.cands["pi"] = [{"sid": "pi-1", "cwd": "/w/pi", "start": NOW - 100, "mtime": NOW - 5, "model": "anthropic/m",
                             "tools": [(NOW - 20, "read"), (NOW - 6, "bash")]}]
        pr._PRES_MEMO.clear()
        w = pr.ext_work_any("pi", "pi-1", NOW)
        self.assertEqual((w["ok"], w["src"], w["tool"]), (True, "file", "bash"))
        self.cands["pi"][0]["tools"] = []
        pr._PRES_MEMO.clear()
        self.assertEqual(pr.ext_work_any("pi", "pi-1", NOW)["tool"], "")
        w = pr.ext_work_any("cu", SID, NOW)
        self.assertEqual((w["src"], w["tool"]), ("file", ""))

    def test_work_hook_row_first(self):
        st._ext[("cursor", SID)] = {"cwd": "/w/hook", "state": "think", "lastSeen": NOW, "firstSeen": NOW}
        self.assertEqual(pr.ext_work_any("cu", SID, NOW)["cwd"], "/w/hook")



class HooksOff(unittest.TestCase):
    """Copilot `disableAllHooks` in the repo settings (temp dirs only, never a live repo)."""

    def setUp(self):
        import tempfile
        self.cp = sidereus("plat_copilot")
        self.cp._HOOKS_OFF.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        import os
        os.makedirs(os.path.join(self.repo, ".git"))
        os.makedirs(os.path.join(self.repo, ".github", "copilot"))
        self.sub = os.path.join(self.repo, "web", "app")
        os.makedirs(self.sub)
        self.cfg = os.path.join(self.repo, ".github", "copilot", "settings.json")

    def tearDown(self):
        self.cp._HOOKS_OFF.clear()
        self.tmp.cleanup()

    def put(self, text, mtime):
        import os
        with open(self.cfg, "w", encoding="utf-8") as f:
            f.write(text)
        os.utime(self.cfg, (mtime, mtime))

    def test_key_true_from_subdir(self):
        self.put('\ufeff{"disableAllHooks": true, "other": 1}', NOW)
        self.assertTrue(self.cp.hooks_disabled(self.sub))

    def test_missing_false_or_bad_is_off(self):
        self.assertFalse(self.cp.hooks_disabled(self.sub))          # no file
        self.put('{"disableAllHooks": "true"}', NOW)                 # only the JSON boolean counts
        self.assertFalse(self.cp.hooks_disabled(self.sub))
        self.cp._HOOKS_OFF.clear()
        self.put('{not json', NOW + 1)
        self.assertFalse(self.cp.hooks_disabled(self.sub))
        self.assertFalse(self.cp.hooks_disabled("relative/dir"))

    def test_reread_on_mtime_change(self):
        self.put('{"disableAllHooks": false}', NOW)
        self.assertFalse(self.cp.hooks_disabled(self.sub))
        self.put('{"disableAllHooks": true}', NOW + 5)
        self.assertTrue(self.cp.hooks_disabled(self.sub))


if __name__ == "__main__":
    unittest.main()
