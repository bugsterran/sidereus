"""Hook-less Cursor/Copilot rows (ext_presence): rollout-row shape, hook row wins, work-panel fallback."""
import json
import os
import shutil
import time
import unittest

from tests._load import sidereus

ext = sidereus("ext")
st = sidereus("ext_store")
life = sidereus("ext_life")
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
        self._pp = pr._pi_procs
        pr._pi_procs = lambda now: {}                             # ⚠no live ps snapshot / lsof
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
        pr._pi_procs = self._pp
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

    def test_pi_row_gets_mailbox_id(self):
        # pi rows carry the pi mailbox id (ident.mbox_pi), so a room member logged in from pi maps to this row
        self.cands["pi"] = [{"sid": "pi-1", "cwd": "/w/pi", "start": NOW - 100, "mtime": NOW - 5, "model": "anthropic/m"}]
        mo = pr.mbox_pi
        pr.mbox_pi = lambda cwd: ("pi-id", "identity") if cwd == "/w/pi" else ("", "none")
        try:
            got = {r["plat"]: r["mbox"] for r in self.rows()}
        finally:
            pr.mbox_pi = mo
        self.assertEqual(got.get(pr.EXT_PLAT["pi"]), "pi-id")
        self.assertEqual(got.get("cu"), "")   # other CLIs have no mailbox login

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
            self.assertEqual(life.ext_dismiss(SID), 1)
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

    def test_special_or_oversize_file_is_off_without_reading_it(self):
        import os
        if not hasattr(os, "mkfifo") or not os.path.exists("/dev/zero"):
            self.skipTest("POSIX only")
        os.mkfifo(self.cfg)                       # open() would block without O_NONBLOCK
        self.assertFalse(self.cp.hooks_disabled(self.sub))
        os.remove(self.cfg)
        self.cp._HOOKS_OFF.clear()
        os.symlink("/dev/zero", self.cfg)         # getsize 0, endless read without the fstat check
        self.assertFalse(self.cp.hooks_disabled(self.sub))
        os.remove(self.cfg)
        self.cp._HOOKS_OFF.clear()
        self.put('{"disableAllHooks": true, "pad": "%s"}' % ("x" * self.cp.SETTINGS_MAX), NOW)
        self.assertFalse(self.cp.hooks_disabled(self.sub))

    def test_directory_at_settings_path_closes_fd(self):
        import os
        from unittest import mock
        if os.name == "nt":
            self.skipTest("POSIX only: Windows os.open refuses a directory before any fd exists")
        os.makedirs(self.cfg)                     # fdopen raises EISDIR on a directory fd
        fds, real = [], os.open

        def rec(*a, **k):
            fds.append(real(*a, **k))
            return fds[-1]
        with mock.patch.object(self.cp.os, "open", rec):
            self.assertFalse(self.cp.hooks_disabled(self.sub))
        self.assertEqual(len(fds), 1)
        with self.assertRaises(OSError):
            os.fstat(fds[0])                      # the fd was closed


class PiRunning(unittest.TestCase):
    """Idle pi session stays listed while a `pi` process runs in its cwd (temp sessions dir, patched ps/lsof caches)."""

    def setUp(self):
        import tempfile
        from unittest import mock
        self.tmp = tempfile.mkdtemp(prefix="sidereus-pipres-")
        self.root = os.path.join(self.tmp, "agent")
        self.cwd = "/w/pi-proj"
        lp = pr.live_probe
        self.snap = [("501", "1", "pi"), ("777", "1", "/bin/zsh"), ("888", "1", "node /opt/bin/pi --x")]
        self.cwds = {"501": self.cwd, "777": self.cwd, "888": "/w/other"}
        self.probed = []

        def probe(pids, force=False):
            self.probed.append(set(pids))
            for q in pids:
                pr.term._CWD_CACHE[q] = (NOW, self.cwds.get(q, ""))
        self.p = [mock.patch.object(pr.plat_pi, "root", lambda: self.root),
                  mock.patch.object(lp, "_ps_snap_cache", [NOW - 1, self.snap]),
                  mock.patch.object(pr.term, "_probe_cwd", probe),
                  mock.patch.object(pr.term, "_CWD_CACHE", {}),
                  mock.patch.object(st, "_ext", {}), mock.patch.object(st, "_ext_ended", {})]
        for x in self.p:
            x.start()
        pr._PRES_MEMO.clear()
        pr.plat_pi._cache.clear()

    def tearDown(self):
        for x in self.p:
            x.stop()
        pr._PRES_MEMO.clear()
        pr.plat_pi._cache.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, sid, mtime, cwd=None):
        cwd = cwd or self.cwd
        d = os.path.join(self.root, "sessions", pr.plat_pi.folder(cwd))
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "2026-11-10T00-00-00-000Z_%s.jsonl" % sid)
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "session", "id": sid, "timestamp": "2026-11-10T00:00:00.000Z", "cwd": cwd}) + "\n")
        os.utime(p, (mtime, mtime))
        return p

    def pi_rows(self):
        pr._PRES_MEMO.clear()
        return [r for r in pr.ext_presence_rows(NOW) if r["plat"] == "pi"]

    def test_idle_session_kept_while_process_runs(self):
        self.write("pi-old", NOW - 9000)
        self.write("pi-new", NOW - 2200)                          # idle 37 min, past PRES_WIN_S
        rows = self.pi_rows()
        self.assertEqual([(r["sid"], r["pid"], r["state"]) for r in rows], [("pi-new", 501, "unknown")])
        self.assertEqual(self.probed, [{"501", "888"}])          # only pi argv, never the shell

    def test_no_process_falls_back_to_window(self):
        self.snap[:] = [("777", "1", "/bin/zsh")]
        self.write("pi-new", NOW - 2200)
        self.assertEqual(self.pi_rows(), [])
        self.write("pi-fresh", NOW - 30)
        self.assertEqual([(r["sid"], r["pid"]) for r in self.pi_rows()], [("pi-fresh", 0)])

    def test_unknown_snapshot_is_not_none(self):
        with mock_obj(pr.live_probe, "_ps_snap_cache", [NOW - 600, self.snap]):   # stale snapshot = unknown
            self.write("pi-new", NOW - 2200)
            self.assertEqual(self.pi_rows(), [])
            self.assertEqual(self.probed, [])
            self.assertIsNone(pr._pi_procs(NOW))

    def test_fresh_file_gets_pid_once(self):
        self.write("pi-new", NOW - 20)
        rows = self.pi_rows()
        self.assertEqual([(r["sid"], r["pid"]) for r in rows], [("pi-new", 501)])

    def test_dismissed_stays_hidden(self):
        self.write("pi-new", NOW - 2200)
        st._ext_ended[("pi", "pi-new")] = NOW - 10
        self.assertEqual(self.pi_rows(), [])

    def test_header_cwd_must_match_lossy_folder(self):
        self.write("pi-other", NOW - 2200, cwd="/w/pi/proj")       # same folder name as /w/pi-proj
        self.assertEqual(pr.plat_pi.folder("/w/pi/proj"), pr.plat_pi.folder(self.cwd))
        self.assertEqual(self.pi_rows(), [])

    def test_pi_argv(self):
        for cmd, ok in (("pi", True), ("/usr/local/bin/pi -p x", True), ("node /x/pi", True),
                        ("pip install", False), ("node /x/pi-other", False), ("", False), ("vim pi", False)):
            self.assertEqual(pr._is_pi_argv(cmd), ok, cmd)


def mock_obj(obj, name, val):
    from unittest import mock
    return mock.patch.object(obj, name, val)


if __name__ == "__main__":
    unittest.main()
