"""sidereus/live_probe.py decision logic with synthetic inputs: ps snapshot parsing and caches, agent_view
success / stale fallback / negative cache, tool_busy, _blocked, sid transcript lookups and sid_alive.

No live processes, clock or transcripts: subprocess, time, IS_MAC, warn_once, bin_path, rich_env and
CLAUDE_PROJECTS are replaced on the live_probe module; the sid tests use a temp projects dir.
"""
import json
import os
import shutil
import subprocess as _real_sp
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

lp = sidereus("live_probe")
_REAL_SIG = lp._av_registry_sig     # captured before _Base patches it out


class _Clock:
    def __init__(self, t=10_000.0):
        self.t = t

    def time(self):
        return self.t


class _Sub:
    """subprocess stand-in: `outs` maps argv[0] to stdout text or an exception instance."""
    TimeoutExpired = _real_sp.TimeoutExpired

    def __init__(self, outs):
        self.outs, self.calls = outs, []

    def run(self, argv, **kw):
        self.calls.append(list(argv))
        v = self.outs[argv[0]]
        if isinstance(v, BaseException):
            raise v
        return mock.Mock(stdout=v)


class _Base(unittest.TestCase):
    def setUp(self):
        self.clock = _Clock()
        self.warns = []
        self.sub = _Sub({})
        for name, val in (("time", self.clock), ("subprocess", self.sub), ("IS_MAC", True),
                          ("warn_once", lambda key, msg, **kw: self.warns.append(key)),
                          ("bin_path", lambda n: n), ("bin_forget", lambda n: None), ("rich_env", lambda: {}),
                          ("_slow_why", lambda en=False: ""), ("_av_registry_sig", lambda d: None)):
            p = mock.patch.object(lp, name, val)
            p.start()
            self.addCleanup(p.stop)
        lists = (lp._av_cache, lp._av_fail, lp._ps_snap_cache, lp._ps_snap_fail,
                 lp._sid_file, lp._sid_stale, lp._live_sids)
        saved = [list(x) for x in lists]
        busy, stale = lp._busy_cache, dict(lp._stale)

        def restore():
            for x, old in zip(lists, saved):
                x[:] = old
            lp._busy_cache = busy
            lp._stale.clear()
            lp._stale.update(stale)
        self.addCleanup(restore)
        lp._av_cache[:] = [0.0, None]
        lp._av_fail[:] = [0.0]
        lp._ps_snap_cache[:] = [0.0, None]
        lp._ps_snap_fail[:] = [0.0, None]
        lp._busy_cache = (0.0, {})
        lp._stale.clear()


class PsSnapTest(_Base):
    def test_parses_and_skips_short_lines(self):
        self.sub.outs["ps"] = "  1   0 /sbin/launchd\n 42 1 claude --resume x y\n\n 7 3\n"
        self.assertEqual(lp._ps_snap(), [("1", "0", "/sbin/launchd"), ("42", "1", "claude --resume x y")])

    def test_reused_within_ttl_then_retaken(self):
        self.sub.outs["ps"] = "1 0 a\n"
        lp._ps_snap()
        self.clock.t += 1.0
        lp._ps_snap()
        self.assertEqual(len(self.sub.calls), 1)
        self.clock.t += lp.PS_SNAP_TTL
        lp._ps_snap()
        self.assertEqual(len(self.sub.calls), 2)

    def test_failure_negative_cached_then_recovers(self):
        self.sub.outs["ps"] = _real_sp.TimeoutExpired("ps", 4)
        with self.assertRaises(_real_sp.TimeoutExpired):
            lp._ps_snap()
        self.clock.t += lp.PS_SNAP_FAIL_TTL - 0.5
        with self.assertRaises(_real_sp.TimeoutExpired):
            lp._ps_snap()
        self.assertEqual(len(self.sub.calls), 1, "a cached failure must not fork ps again")
        self.clock.t += 1.0
        self.sub.outs["ps"] = "5 1 x\n"
        self.assertEqual(lp._ps_snap(), [("5", "1", "x")])
        self.assertEqual(lp._ps_snap_fail, [0.0, None])

    def test_non_mac_is_empty_without_ps(self):
        lp.IS_MAC = False
        self.assertEqual(lp._ps_snap(), [])
        self.assertEqual(self.sub.calls, [])


class AgentViewTest(_Base):
    def test_success_keys_by_pid_string(self):
        self.sub.outs["claude"] = json.dumps([{"pid": 12, "sessionId": "a"}, {"pid": None}, "junk", {"x": 1}])
        out = lp.agent_view()
        self.assertEqual(out, {"12": {"pid": 12, "sessionId": "a"}})
        self.assertEqual(self.sub.calls[0], ["claude", "agents", "--json"])
        self.clock.t += lp.AGENTS_TTL - 1
        self.assertIs(lp.agent_view(), out)
        self.assertEqual(len(self.sub.calls), 1)

    def test_empty_stdout_is_empty_view(self):
        self.sub.outs["claude"] = ""
        self.assertEqual(lp.agent_view(), {})
        self.assertEqual(self.warns, [])

    def test_non_list_without_prev_is_unknown_and_negative_cached(self):
        self.sub.outs["claude"] = '{"pid": 1}'
        self.assertIsNone(lp.agent_view())
        self.assertEqual(self.warns, ["agents"])
        self.assertNotIn("agents", lp._stale)
        self.clock.t += lp.AGENTS_FAIL_TTL - 1
        self.assertIsNone(lp.agent_view(ttl=0))
        self.assertEqual(len(self.sub.calls), 1, "failure within AGENTS_FAIL_TTL must not fork again")

    def test_failure_with_fresh_prev_falls_back_and_marks_stale(self):
        prev = {"1": {"pid": 1}}
        lp._av_cache[:] = [self.clock.t - 20, prev]
        self.sub.outs["claude"] = _real_sp.TimeoutExpired("claude", 6)
        self.assertIs(lp.agent_view(ttl=0), prev)
        self.assertEqual(self.warns, ["agents-slow"])
        self.assertIn("agents", lp._stale)
        self.clock.t += 1
        self.assertIs(lp.agent_view(ttl=0), prev)          # negative cache still serves the fallback
        self.assertEqual(len(self.sub.calls), 1)

    def test_failure_with_old_prev_is_unknown(self):
        lp._av_cache[:] = [self.clock.t - lp.AGENTS_STALE_S - 1, {"1": {}}]
        self.sub.outs["claude"] = ValueError("x")
        self.assertIsNone(lp.agent_view(ttl=0))
        self.assertEqual(lp._av_cache, [0.0, None])
        self.assertEqual(self.warns, ["agents"])

    def test_recovery_lifts_negative_cache_and_stale(self):
        lp._av_fail[0] = self.clock.t - lp.AGENTS_FAIL_TTL - 1
        lp._stale["agents"] = (1.0, 2.0)
        self.sub.outs["claude"] = "[]"
        self.assertEqual(lp.agent_view(ttl=0), {})
        self.assertEqual(lp._av_fail, [0.0])
        self.assertNotIn("agents", lp._stale)


class AgentViewSignatureTest(_Base):
    """Registry-signature mode: spawn only on a signature change, at AGENTS_MAX_AGE, or after the failure backoff."""

    def setUp(self):
        super().setUp()
        self.cfg = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.cfg, True)
        os.mkdir(os.path.join(self.cfg, "sessions"))
        self.alive = {"11"}
        for name, val in (("_av_registry_sig", _REAL_SIG), ("pid_alive", lambda pid: str(pid) in self.alive),
                          ("_av_accounts", lambda: [("", self.cfg, True)])):
            p = mock.patch.object(lp, name, val)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(lp._av_sigs, clear=True)
        p.start()
        self.addCleanup(p.stop)
        self.reg(11, "s1")
        self.sub.outs["claude"] = json.dumps([{"pid": 11, "sessionId": "s1"}])

    def reg(self, pid, sid, status="idle"):
        fp = os.path.join(self.cfg, "sessions", "%d.json" % pid)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump({"pid": pid, "sessionId": sid, "cwd": "/w", "status": status}, f)
        os.utime(fp, ns=(self.clock_ns(), self.clock_ns()))

    def clock_ns(self):
        self._ns = getattr(self, "_ns", 10 ** 18) + 10 ** 9
        return self._ns

    def test_unchanged_signature_within_max_age_does_not_spawn(self):
        lp.agent_view()
        self.reg(11, "s1", status="busy")          # status churn is not part of the signature
        self.clock.t += lp.AGENTS_MAX_AGE - 1
        lp.agent_view()
        self.assertEqual(len(self.sub.calls), 1)

    def test_signature_change_spawns_at_once(self):
        lp.agent_view()
        self.clock.t += 1
        self.reg(11, "s2")                         # /clear: same pid, new sessionId
        lp.agent_view()
        self.assertEqual(len(self.sub.calls), 2)
        self.reg(12, "s3")                         # a new session starts
        lp.agent_view()
        self.assertEqual(len(self.sub.calls), 3)
        self.alive.discard("11")                   # a crash leaves the file but the pid is gone
        lp.agent_view()
        self.assertEqual(len(self.sub.calls), 4)
        lp.agent_view()
        self.assertEqual(len(self.sub.calls), 4)

    def test_max_age_spawns(self):
        lp.agent_view()
        self.clock.t += lp.AGENTS_MAX_AGE
        lp.agent_view()
        self.assertEqual(len(self.sub.calls), 2)

    def test_failure_backoff_kept_despite_signature_change(self):
        self.sub.outs["claude"] = _real_sp.TimeoutExpired("claude", 6)
        self.assertIsNone(lp.agent_view())
        self.reg(12, "s3")
        self.clock.t += lp.AGENTS_FAIL_TTL - 1
        self.assertIsNone(lp.agent_view())
        self.assertEqual(len(self.sub.calls), 1, "a signature change must not bypass the negative cache")
        self.clock.t += 2
        self.sub.outs["claude"] = "[]"
        self.assertEqual(lp.agent_view(), {})
        self.assertEqual(len(self.sub.calls), 2)

    def test_no_registry_falls_back_to_plain_ttl(self):
        shutil.rmtree(os.path.join(self.cfg, "sessions"))
        lp.agent_view()
        self.clock.t += lp.AGENTS_TTL - 1
        lp.agent_view()
        self.assertEqual(len(self.sub.calls), 1)
        self.clock.t += 1
        lp.agent_view()
        self.assertEqual(len(self.sub.calls), 2)


class ToolBusyTest(_Base):
    PS = [("100", "1", "/usr/local/bin/claude --resume s"), ("200", "100", "/bin/zsh -c source ~/.claude/shell-snapshot-x"),
          ("101", "1", "claude"), ("300", "101", "node mcp-server.js"), ("400", "1", "zsh -c shell-snapshot orphan")]

    def setUp(self):
        super().setUp()
        self.ps = list(self.PS)
        p = mock.patch.object(lp, "_ps_snap", lambda ttl=None: self._snap())
        p.start()
        self.addCleanup(p.stop)

    def _snap(self):
        if isinstance(self.ps, BaseException):
            raise self.ps
        return self.ps

    def test_only_claude_with_shell_child_is_busy(self):
        self.sub.outs["lsof"] = "p100\nn/work/a\n"
        self.assertEqual(lp.tool_busy(ttl=0), {"/work/a": True})
        (argv,) = self.sub.calls
        self.assertEqual(argv[-1], "100")                  # 101 has only an MCP child; 400's parent is not claude

    def test_nothing_busy_skips_lsof(self):
        self.ps = [r for r in self.PS if "shell-snapshot" not in r[2]]
        self.assertEqual(lp.tool_busy(ttl=0), {})
        self.assertEqual(self.sub.calls, [])

    def test_lsof_without_cwd_is_failure_not_empty(self):
        # Busy pids but no cwd from lsof = failed probe; {} would flag every Bash session as awaiting approval.
        self.sub.outs["lsof"] = ""
        self.assertIsNone(lp.tool_busy(ttl=0))
        self.assertEqual(self.warns, ["busy"])

    def test_non_mac_is_unknown(self):
        lp.IS_MAC = False
        self.assertIsNone(lp.tool_busy(ttl=0))
        self.assertEqual(self.sub.calls, [])

    def test_cached_within_ttl(self):
        self.sub.outs["lsof"] = "p100\nn/w\n"
        lp.tool_busy()
        self.clock.t += 1
        lp.tool_busy()
        self.assertEqual(len(self.sub.calls), 1)

    def test_failure_uses_fresh_prev_then_unknown(self):
        lp._busy_cache = (self.clock.t - 5, {"/w": True})
        self.ps = OSError("ps died")
        self.assertEqual(lp.tool_busy(ttl=0), {"/w": True})
        self.assertEqual(self.warns, ["busy-slow"])
        self.assertIn("busy", lp._stale)
        lp._busy_cache = (self.clock.t - lp.BUSY_STALE_S - 1, {"/w": True})
        self.assertIsNone(lp.tool_busy(ttl=0))            # past BUSY_STALE_S: unknown, never the ghost set
        self.assertEqual(self.warns, ["busy-slow", "busy"])
        self.assertNotIn("busy", lp._stale)
        self.assertIsNone(lp._busy_cache[1])


class BlockedTest(_Base):
    def setUp(self):
        super().setUp()
        self.busy = {"/other": True}
        p = mock.patch.object(lp, "tool_busy", lambda ttl=2: self.busy)
        p.start()
        self.addCleanup(p.stop)

    def test_not_tool_or_too_young_or_no_tool(self):
        g = lp.BLOCK_GRACE_S
        self.assertEqual(lp._blocked("think", "Edit", g + 1, "/c", 0), "")
        self.assertEqual(lp._blocked("tool", "Edit", g - 0.1, "/c", 0), "")
        self.assertEqual(lp._blocked("tool", "", g + 1, "/c", 0), "")

    def test_fast_tool_is_approval_wait(self):
        for t in ("Edit", "Write", "Read", "Grep"):
            self.assertEqual(lp._blocked("tool", t, 60, "/c", 0), t + " waiting for approval")

    def test_mcp_and_slow_tools_never_asserted(self):
        self.assertEqual(lp._blocked("tool", "mcp__srv__Edit", 600, "/c", 0), "")
        self.assertEqual(lp._blocked("tool", "Agent", 600, "/c", 0), "")
        self.assertEqual(lp._blocked("tool", "WebFetch", 600, "/c", 0), "")

    def test_bash_depends_on_running_processes(self):
        self.assertEqual(lp._blocked("tool", "Bash", 60, "/c", 0), "Bash waiting for approval")
        self.busy = {"/c": True}
        self.assertEqual(lp._blocked("tool", "Bash", 60, "/c", 0), "")
        self.busy = None                                   # unknown -> no badge
        self.assertEqual(lp._blocked("tool", "Bash", 60, "/c", 0), "")
        self.busy = {}                                     # probe ran, nothing running anywhere -> waiting
        self.assertEqual(lp._blocked("tool", "Bash", 60, "/c", 0), "Bash waiting for approval")

    def test_bash_with_background_job_not_asserted(self):
        self.assertEqual(lp._blocked("tool", "Bash", 60, "/c", 1), "")

    def test_permission_mode_x_bash_edit(self):
        want = {"bypassPermissions": ("", ""), "auto": ("", ""), "dontAsk": ("", ""),
                "acceptEdits": ("Bash waiting for approval", ""),
                "default": ("Bash waiting for approval", "Edit waiting for approval"), "plan": ("Bash waiting for approval", "Edit waiting for approval"),
                "": ("Bash waiting for approval", "Edit waiting for approval")}
        for m, (b, e) in want.items():
            self.assertEqual(lp._blocked("tool", "Bash", 60, "/c", 0, m), b, m)
            self.assertEqual(lp._blocked("tool", "Edit", 60, "/c", 0, m), e, m)
        self.assertEqual(lp._blocked("tool", "Read", 60, "/c", 0, "acceptEdits"), "Read waiting for approval")


class PmodeParseTest(unittest.TestCase):
    def test_latest_permission_mode_wins(self):
        parse = sidereus("parse")
        rows = [json.dumps({"type": "user", "permissionMode": "default"}), "not json",
                json.dumps({"type": "user", "permissionMode": "auto"}), json.dumps({"type": "assistant"})]
        self.assertEqual(parse._tail_pmode(rows), "auto")
        self.assertEqual(parse._tail_pmode([json.dumps({"type": "user"})]), "")


class SidProbeTest(_Base):
    def setUp(self):
        super().setUp()
        self.proj = tempfile.mkdtemp(prefix="sidereus-lp-")
        self.addCleanup(shutil.rmtree, self.proj, True)
        p = mock.patch.object(lp, "CLAUDE_PROJECTS", self.proj)
        p.start()
        self.addCleanup(p.stop)
        lp._sid_file[:] = [0.0, {}]
        lp._sid_stale[:] = [0.0, {}]

    def _tx(self, slug, sid, mtime):
        d = os.path.join(self.proj, slug)
        os.makedirs(d, exist_ok=True)
        fp = os.path.join(d, sid + ".jsonl")
        with open(fp, "w", encoding="utf-8"):
            pass
        os.utime(fp, (mtime, mtime))
        return fp

    def test_transcript_lookup_and_miss_cached(self):
        fp = self._tx("-a", "s1", 100)
        self.assertEqual(lp._sid_transcript("s1"), fp)
        self.assertEqual(lp._sid_transcript("nope"), "")
        self._tx("-b", "nope", 100)
        self.assertEqual(lp._sid_transcript("nope"), "", "miss is cached for SID_FILE_TTL")
        self.clock.t += lp.SID_FILE_TTL + 1
        self.assertTrue(lp._sid_transcript("nope"))

    def test_missing_transcript_is_stale(self):
        self.assertTrue(lp._sid_claim_stale("ghost"))

    def test_newest_in_dir_is_not_stale(self):
        self._tx("-a", "s1", 200)
        self._tx("-a", "older", 100)
        self.assertFalse(lp._sid_claim_stale("s1"))

    def test_newer_sibling_is_stale(self):
        self._tx("-a", "s1", 100)
        self._tx("-a", "s2", 200)
        self.assertTrue(lp._sid_claim_stale("s1"))

    def test_newer_file_in_cwd_slug_dir_is_stale(self):
        cwd = "/Users/x/proj"
        self._tx("-elsewhere", "s1", 100)
        self._tx(lp._slug(cwd), "succ", 200)
        self.assertFalse(lp._sid_claim_stale("s1"))
        self.assertTrue(lp._sid_claim_stale("s1", cwd))

    def test_missing_cwd_dir_is_not_evidence(self):
        self._tx("-a", "s1", 100)
        self.assertFalse(lp._sid_claim_stale("s1", "/no/such/dir"))

    def test_sid_alive_windows(self):
        lp._live_sids[:] = [self.clock.t - 1, {"s1"}]
        self.assertTrue(lp.sid_alive("s1"))
        self.assertFalse(lp.sid_alive_stale("s1"))
        self.assertFalse(lp.sid_alive("s2"))
        self.assertFalse(lp.sid_alive(""))
        lp._live_sids[0] = self.clock.t - lp.LIVE_STALE_S
        self.assertFalse(lp.sid_alive("s1"))
        self.assertTrue(lp.sid_alive_stale("s1"))


if __name__ == "__main__":
    unittest.main()
