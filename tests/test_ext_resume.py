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


class Resume(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = (st._ext_save_locked, st.EXT_RUNS_FILE, dict(ext._ext), dict(ext._runs),
                      os.kill, st._pid_start, ext.time.time, gm.scan)
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
        st._pid_start = lambda pid: "Thu Sep 24 20:30:27 2026" if pid in self.alive else ""
        self.clock = [NOW]
        ext.time.time = lambda: self.clock[0]
        gm.scan = lambda cut: []

    def tearDown(self):
        (st._ext_save_locked, st.EXT_RUNS_FILE, e, r, os.kill, st._pid_start, ext.time.time,
         gm.scan) = self.saved
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


if __name__ == "__main__":
    unittest.main()
