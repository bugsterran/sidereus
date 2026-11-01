"""npm-installed Claude Code runs as `claude.exe`: the session counts, daemon / pty host / spare helpers do not. No live files."""
import types
import unittest

from tests._load import sidereus

lv = sidereus("live")
lp = sidereus("live_probe")

EXE = "/opt/homebrew/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe"
SID = "5a49e0bd-4bba-4d70-ac6a-fbcb75395c75"
PROJ = "/Users/x/proj"
HOME = "/Users/x"
SPARE_CWD = "/private/tmp/cc-daemon-501/3ba0a137/spare"
DAEMON = ("10", "1", EXE + ' daemon run --origin transient --spawned-by {"label":"claude","cwd":"/Users/x/proj","pid":9}')
SPARE = ("20", "10", "claude bg-pty-host --bg-pty-host /tmp/cc-daemon-501/3ba0a137/spare/93010bcf.pty.sock 200 50 -- "
         + EXE + " --bg-spare")
PTY = ("30", "10", EXE + " --bg-pty-host /tmp/cc-daemon-501/3ba0a137/pty/5a49e0bd.sock 140 36 -- " + EXE)
JOB = ("40", "30", EXE + " --session-id %s --fork-session --resume /p/old.jsonl" % SID)
CWDS = {"10": HOME, "20": SPARE_CWD, "30": SPARE_CWD, "40": PROJ}


def _lsof(cwds):
    # Answers only the pids passed with -p, like the real lsof.
    def run(argv, **_k):
        pids = argv[argv.index("-p") + 1].split(",")
        return types.SimpleNamespace(stdout="".join("p%s\nn%s\n" % (p, cwds[p]) for p in pids if p in cwds))
    return types.SimpleNamespace(run=run)


class Predicate(unittest.TestCase):
    def test_argvs(self):
        self.assertTrue(lp.is_claude_argv(JOB[2]))
        self.assertTrue(lp.is_claude_argv("claude --resume " + SID))
        self.assertTrue(lp.is_claude_argv(r"C:\npm\claude-code\bin\Claude.EXE"))
        for helper in (DAEMON, SPARE, PTY):
            self.assertFalse(lp.is_claude_argv(helper[2]))
        self.assertFalse(lp.is_claude_argv(""))
        self.assertFalse(lp.is_claude_argv("/usr/bin/claudex --resume"))


class LiveClaudeExe(unittest.TestCase):
    def setUp(self):
        self._saved = {k: getattr(lv, k) for k in
                       ("_ps_snap", "agent_view", "subprocess", "IS_MAC", "_sid_transcript", "_sid_claim_stale")}
        self._cache = lv._live_cache
        self._pcwd = list(lp._live_pid_cwd)
        lv._live_cache = (0.0, set())
        lp._live_pid_cwd[0], lp._live_pid_cwd[1] = 0.0, {}
        lv.IS_MAC = True
        lv._sid_transcript = lambda sid: "/t/%s.jsonl" % sid
        lv._sid_claim_stale = lambda sid, cwd: True   # keep the job in path counting so its cwd is visible
        lv.subprocess = _lsof(CWDS)

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(lv, k, v)
        lv._live_cache = self._cache
        lp._live_pid_cwd[0], lp._live_pid_cwd[1] = self._pcwd

    def run_with(self, snap, av=None):
        lv._ps_snap = lambda ttl=None: snap
        lv.agent_view = lambda ttl=None: av
        return lv.live_cwds(ttl=0)

    def test_job_counts_once_helpers_do_not(self):
        self.assertEqual(self.run_with([DAEMON, SPARE, PTY, JOB]), {PROJ: 1})

    def test_exe_only_snapshot_is_not_empty(self):
        self.assertEqual(self.run_with([DAEMON, PTY, JOB]), {PROJ: 1})

    def test_official_job_is_alive(self):
        live = self.run_with([DAEMON, SPARE, PTY, JOB], {"40": {"sessionId": SID, "cwd": PROJ}})
        self.assertEqual(live, {})
        self.assertTrue(lv.sid_alive(SID))


class ToolBusyExe(unittest.TestCase):
    def setUp(self):
        self._saved = {k: getattr(lp, k) for k in ("_ps_snap", "subprocess", "IS_MAC", "_busy_cache", "_busy_shells")}
        lp.IS_MAC = True
        lp._busy_cache = (0.0, {})
        shell = ("50", "40", "/bin/zsh -c source /Users/x/.claude/shell-snapshots/snapshot-zsh-1.sh && ls")
        lp._ps_snap = lambda ttl=None: [DAEMON, SPARE, PTY, JOB, shell]
        lp.subprocess = _lsof(CWDS)

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(lp, k, v)

    def test_busy_sees_exe_job(self):
        self.assertEqual(lp.tool_busy(ttl=0), {PROJ: True})


if __name__ == "__main__":
    unittest.main()
