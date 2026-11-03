"""Background-job term: a transient lookup failure keeps the last good spawner tab. No real ps/files."""
import unittest

from tests._load import sidereus

term = sidereus("term")
SID = "aa11aa11-1111-4111-8111-111111111111"
SID2 = "bb22bb22-2222-4222-8222-222222222222"
GOOD = {"app": "iterm", "tty": "ttys002", "bg": True}
BG = {"app": "bg", "tty": None}
DAEMON = ("64603", "1", '/x/claude.exe daemon run --origin transient --spawned-by {"label":"claude","cwd":"/r","pid":68658}')
HOST = ("64614", "64603", "/x/claude.exe --bg-pty-host /tmp/cc-daemon-501/a/pty/5a49e0bd.sock 140 36 -- /x/claude.exe")
JOB = ("64636", "64614", "claude --resume " + SID)
SPAWNER = ("68658", "1", "claude --resume " + SID2)


class _Run:
    def __init__(self, out):
        self.out, self.calls = out, []

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        return type("R", (), {"stdout": self.out, "stderr": ""})()


class BgLastGood(unittest.TestCase):
    def patch(self, mod, name, val):
        old = getattr(mod, name)
        setattr(mod, name, val)
        self.addCleanup(setattr, mod, name, old)

    def setUp(self):
        self.patch(term, "IS_MAC", True)
        self.patch(term, "_TTY_CACHE", {})
        self.patch(term, "_TTY_FAIL", [0.0])
        self.patch(term, "_BG_LAST", {})
        self.patch(term, "_av_cache", [0.0, {}])
        self.patch(term.subprocess, "run", _Run("64636 ttys006 claude HOME=/h\n"
                                                "68658 ttys002 claude TERM_PROGRAM=iTerm.app LC_TERMINAL=iTerm2\n"))

    def _attach(self, snap):
        self.patch(term, "_ps_snap_cache", [0.0, snap])
        rows = [{"sid": SID, "state": "wait"}]
        term.term_attach(rows)
        return rows[0]["term"]

    def _good_first(self):
        self.assertEqual(self._attach([DAEMON, HOST, JOB, SPAWNER]), GOOD)

    def test_daemon_respawn_gap_keeps_last_good(self):
        self._good_first()
        self.assertEqual(self._attach([HOST, JOB, SPAWNER]), GOOD)        # daemon missing -> spawner None

    def test_skipped_probe_keeps_last_good(self):
        self._good_first()
        term._TTY_CACHE.clear()                                           # spawner entry gone
        term._TTY_FAIL[0] = 9e18                                          # poll path probe is skipped
        self.assertEqual(self._attach([DAEMON, HOST, JOB, SPAWNER]), GOOD)

    def test_job_pid_gone_or_changed_drops(self):
        self._good_first()
        job2 = ("64700", "64614", "claude --resume " + SID)
        self.assertEqual(self._attach([HOST, job2, SPAWNER]), BG)          # different job pid: no reuse
        self.assertNotIn("64636", term._BG_LAST)                          # gone pid pruned
        self.assertEqual(self._attach([HOST, JOB, SPAWNER]), BG)          # came back: entry already dropped

    def test_dead_or_foreign_spawner_drops(self):
        self._good_first()
        self.assertEqual(self._attach([DAEMON, HOST, JOB]), BG)           # spawner exited: real answer
        self.assertEqual(self._attach([HOST, JOB, SPAWNER]), BG)          # and it does not come back

    def test_fresh_good_replaces(self):
        self._good_first()
        term._TTY_CACHE.clear()
        self.patch(term.subprocess, "run", _Run("68658 ttys005 claude TERM_PROGRAM=Apple_Terminal\n"))
        new = {"app": "apple", "tty": "ttys005", "bg": True}
        self.assertEqual(self._attach([DAEMON, HOST, JOB, SPAWNER]), new)
        self.assertEqual(self._attach([HOST, JOB, SPAWNER]), new)

    def test_cap_drops_oldest(self):
        self.patch(term, "BG_LAST_MAX", 2)
        self.patch(term, "_ps_snap_cache", [0.0, None])                    # no snapshot: no pruning
        for k in ("1", "2", "3"):
            term._BG_LAST[k] = ("9", GOOD)
        term.term_attach([])
        self.assertEqual(list(term._BG_LAST), ["2", "3"])


if __name__ == "__main__":
    unittest.main()
