"""sidereus/proc_load.py: srvLoad.top from a synthetic ps snapshot — tree sums, outermost claude owner, pid-1 orphans,
decimal commas, garbage pcpu, argv never in the output, stale snapshot, request path serves cache only.

No live processes, clock or repos: live_probe's caches are replaced, `_now`/`_proj_root` patched on proc_load and
subprocess on live_probe; the background refresh runs inline (memo.run_inline)."""
import json
import unittest
from unittest import mock

from tests._load import sidereus

pl = sidereus("proc_load")
lp = sidereus("live_probe")
memo = sidereus("memo")

NOW = 50_000.0
ROWS = [
    ("1", "0", "/sbin/launchd"),
    ("100", "1", "/usr/local/bin/claude --resume abc"),
    ("110", "100", "/bin/zsh -c npm test --token secret"),
    ("120", "110", "/usr/local/bin/node /r/jest.js --token secret"),
    ("121", "110", "/usr/local/bin/node /r/jest.js"),
    ("130", "100", "/usr/local/bin/claude -p nested"),        # nested claude: sums into 100
    ("131", "130", "/usr/local/bin/node w.js"),
    ("200", "1", "/usr/local/bin/claude"),
    ("210", "200", "/bin/cat"),
    ("300", "1", "/usr/local/bin/node orphan.js --token secret"),   # pid-1 orphan
]
RES = {"1": ("0,5", "1024"), "100": ("1.0", "102400"), "110": ("0.0", "2048"), "120": ("40,5", "204800"),
       "121": ("abc", "204800"), "130": ("2.0", "1024"), "131": ("3.0", "1024"), "200": ("5.0", "1024"),
       "210": ("1.0", "1024"), "300": ("7.5", "10240")}
CWD = {"100": "/w/proj-a/sub", "200": "/w/proj-b"}


class _Base(unittest.TestCase):
    def setUp(self):
        self.roots = []

        def proj_root(cwd):
            self.roots.append(cwd)
            return {"/w/proj-a/sub": "/w/proj-a"}.get(cwd, cwd)
        for mod, name, val in ((pl, "_now", lambda: NOW), (pl, "_proj_root", proj_root),
                               (pl, "_top_cache", [0.0, None, 0.0]),
                               (lp, "_ps_snap_cache", [NOW - 1, list(ROWS)]), (lp, "_ps_res", [NOW - 1, dict(RES)]),
                               (lp, "_live_pid_cwd", [NOW - 1, dict(CWD)]),
                               (lp, "subprocess", mock.Mock(side_effect=AssertionError("no subprocess"))),
                               (memo._PROBE_BG, "spawn", memo.run_inline)):
            p = mock.patch.object(mod, name, val)
            p.start()
            self.addCleanup(p.stop)


class TopTest(_Base):
    def test_tree_sum_outermost_owner_and_unowned(self):
        t = pl.top()
        self.assertEqual(t["repo"], "proj-a")
        self.assertEqual(t["cpu"], 46.5)            # 1.0 + 0 + 40.5 + (abc skipped) + 2.0 nested + 3.0
        self.assertEqual(t["n"], 6)
        self.assertEqual(t["rssMb"], round((102400 + 2048 + 204800 * 2 + 1024 * 2) / 1024.0))
        self.assertEqual(t["exe"], [["node", 3], ["claude", 2], ["zsh", 1]])
        self.assertEqual(t["unowned"], {"cpu": 8.0, "rssMb": 11})   # launchd 0,5 + orphan 7.5

    def test_argv_never_in_output(self):
        out = json.dumps(pl.top())
        for s in ("secret", "--token", "jest", "resume", "/usr/local"):
            self.assertNotIn(s, out)

    def test_unknown_cwd_session_skipped(self):
        lp._live_pid_cwd[1] = {"200": "/w/proj-b"}
        t = pl.top()
        self.assertEqual((t["repo"], t["cpu"], t["n"]), ("proj-b", 6.0, 2))

    def test_no_attributable_session_is_none(self):
        lp._live_pid_cwd[1] = {}
        self.assertIsNone(pl.top())

    def test_stale_snapshot_is_none(self):
        lp._ps_res[0] = NOW - lp.LIVE_STALE_S
        self.assertIsNone(pl.top())

    def test_exe_name_filtered_and_capped(self):
        self.assertEqual(pl._exe("/opt/x/we!rd$name" + "a" * 40 + " --token secret"), ("werdname" + "a" * 40)[:32])
        self.assertEqual(pl._exe(""), "")

    def test_request_path_serves_cache_without_proj_root_or_spawn(self):
        with mock.patch.object(memo._PROBE_BG, "spawn", lambda fn: None):   # refresh never runs
            with memo.request_path():
                self.assertIsNone(pl.top())                 # cold cache = unknown
            self.assertEqual(self.roots, [])
            pl._top_cache[:] = [NOW - 1, {"repo": "proj-a"}, NOW - 1]
            with memo.request_path():
                self.assertEqual(pl.top(), {"repo": "proj-a"})
            self.assertEqual(self.roots, [])

    def test_request_path_refresh_runs_off_path(self):
        with memo.request_path():
            t = pl.top()
        self.assertEqual(t["repo"], "proj-a")


if __name__ == "__main__":
    unittest.main()
