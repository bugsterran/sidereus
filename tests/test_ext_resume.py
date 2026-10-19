"""Gemini --resume: SessionStart under a fresh sid, later hooks under the resumed sid — one row per process."""
import errno
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

ext = sidereus("ext")
st = sidereus("ext_store")   # store internals are patched on their owner
gm = sidereus("plat_gemini")

NOW = 1790000000.0


def _alive_via(kill, pid):
    """config.pid_alive's POSIX branch over a fake kill."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    try:
        kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class Resume(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = (st._ext_save_locked, st.EXT_RUNS_FILE, dict(ext._ext), dict(ext._runs),
                      os.kill, st._pid_start, ext.time.time, gm.scan, st.pid_alive)
        self.saves = []
        st._ext_save_locked = lambda: self.saves.append(1)
        st.EXT_RUNS_FILE = os.path.join(self.tmp, "ext-runs.json")
        ext._ext.clear()
        ext._runs.clear()
        self.alive = {4242}

        def kill(pid, sig):
            if sig != 0:
                raise AssertionError("only signal 0 is allowed")
            if pid not in self.alive:
                raise ProcessLookupError(errno.ESRCH, "no such process")
        os.kill = kill
        # ⚠Windows config.pid_alive uses OpenProcess, not os.kill: drive the store's own name through the fake kill.
        st.pid_alive = lambda pid: _alive_via(kill, pid)
        st._pid_start = lambda pid: "Thu Sep 24 20:30:27 2026" if pid in self.alive else ""
        self.clock = [NOW]
        ext.time.time = lambda: self.clock[0]
        gm.scan = lambda cut: []

    def tearDown(self):
        (st._ext_save_locked, st.EXT_RUNS_FILE, e, r, os.kill, st._pid_start, ext.time.time,
         gm.scan, st.pid_alive) = self.saved
        ext._ext.clear(); ext._ext.update(e)
        ext._runs.clear(); ext._runs.update(r)
        shutil.rmtree(self.tmp)

    def feed(self, ev, t, sid, pid=4242, pstart="Thu Sep 24 20:30:27 2026", **kw):
        req = {"platform": "gemini", "session_id": sid, "event": ev, "cwd": "/tmp/scratch", "ts": t,
               "pid": pid, "pstart": pstart, "host": st._HOST}
        req.update(kw)
        return ext.ext_ingest(req)

    def sids(self):
        return sorted(r["sid"] for r in ext.ext_rows())

    def test_resume_keeps_one_row(self):
        self.feed("SessionStart", NOW - 20, "fresh")
        self.feed("UserPromptSubmit", NOW - 9, "resumed")
        self.feed("PreToolUse", NOW - 5, "resumed", tool_name="run_shell_command")
        self.assertEqual(self.sids(), ["resumed"])
        v = ext._ext[("gemini", "resumed")]
        self.assertEqual(v["state"], "tool")
        self.assertEqual(v["firstSeen"], NOW - 20)          # run time counts from the process start

    def test_saved_duplicates_collapse_to_latest(self):
        base = {"pid": 4242, "pstart": "Thu Sep 24 20:30:27 2026", "cwd": "/tmp/scratch"}
        ext._ext[("gemini", "a")] = dict(base, state="wait", firstSeen=NOW - 30, lastSeen=NOW - 30)
        ext._ext[("gemini", "b")] = dict(base, state="tool", firstSeen=NOW - 20, lastSeen=NOW - 2)
        self.assertEqual(self.sids(), ["b"])
        self.assertTrue(self.saves)

    def test_different_processes_stay_apart(self):
        self.alive.add(4343)
        self.feed("SessionStart", NOW - 20, "one")
        self.feed("SessionStart", NOW - 10, "two", pid=4343)
        self.feed("SessionStart", NOW - 5, "three", pstart="Thu Sep 24 21:00:00 2026")
        self.assertEqual(sorted(k[1] for k in ext._ext), ["one", "three", "two"])

    def test_no_pstart_is_not_merged(self):
        self.feed("SessionStart", NOW - 20, "x", pstart="")
        self.feed("SessionStart", NOW - 10, "y", pstart="")
        self.assertEqual(sorted(k[1] for k in ext._ext), ["x", "y"])

    def test_other_platform_same_pid_kept(self):
        self.feed("SessionStart", NOW - 20, "g")
        self.feed("SessionStart", NOW - 10, "c", platform="codex")
        self.assertEqual(sorted(ext._ext), [("codex", "c"), ("gemini", "g")])

    def test_codex_shared_app_server_pid_not_merged_and_jumps(self):
        # Two Codex TUIs report the same app-server pid; both rows must stay and each must reach its own tab.
        self.feed("SessionStart", NOW - 20, "c1", platform="codex", cwd="/w/one")
        self.feed("UserPromptSubmit", NOW - 10, "c2", platform="codex", cwd="/w/two")
        rows = ext.ext_rows()
        self.assertEqual(sorted(r["sid"] for r in rows), ["c1", "c2"])
        term = sidereus("term")
        ps = {"4242": "4242 ?? codex app-server", "501": "501 ttys005 codex TERM_PROGRAM=iTerm.app",
              "502": "502 ttys006 codex TERM_PROGRAM=iTerm.app"}
        cwd = {"501": "/w/one", "502": "/w/two"}

        def run(argv, **kw):
            pids = argv[-1].split(",")
            out = {"ps": "\n".join(ps[p] for p in pids if p in ps) + "\n",
                   "lsof": "".join("p%s\nn%s\n" % (p, cwd[p]) for p in pids if p in cwd)}.get(argv[0], "ok\n")
            calls.append(argv)
            return type("R", (), {"stdout": out, "stderr": ""})()
        calls = []
        old = (term.IS_MAC, term._TTY_CACHE, term.subprocess.run, term._ps_snap, term.term_cfg, term.warn_once,
               term._CWD_CACHE)
        term.IS_MAC, term._TTY_CACHE, term.subprocess.run, term._CWD_CACHE = True, {}, run, {}
        term._ps_snap = lambda: [("4242", "1", "/x/codex app-server"), ("501", "1", "/x/codex"), ("502", "1", "/x/codex")]
        term.term_cfg, term.warn_once = (lambda: "auto"), (lambda *a, **k: None)
        try:
            out = term.term_focus("c2", rows)[1]
        finally:
            (term.IS_MAC, term._TTY_CACHE, term.subprocess.run, term._ps_snap, term.term_cfg, term.warn_once,
             term._CWD_CACHE) = old
        self.assertEqual((out["how"], out["cmd"], calls[-1][3]), ("focused", "codex resume c2", "/dev/ttys006"))


if __name__ == "__main__":
    unittest.main()
