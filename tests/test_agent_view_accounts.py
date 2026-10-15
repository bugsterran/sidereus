"""agent_view() asks every signed-in account (CLAUDE_CONFIG_DIR) and merges by pid; a failing account is
reported by agent_view_unknown() instead of hiding the others. Single account = one call, env unchanged.

No live processes, clock or account dirs: subprocess, time, warn_once, bin_path, rich_env and claude_roots are
replaced on the live_probe module.
"""
import json
import os
import subprocess as _real_sp
import types
import unittest
from unittest import mock

from tests._load import sidereus

lp = sidereus("live_probe")

HOME = "/nohome"
PRIM = HOME + "/.claude-main"
WORK = HOME + "/.claude-work"
DEFAULT = HOME + "/.claude"


class _Clock:
    def __init__(self, t=50_000.0):
        self.t = t

    def time(self):
        return self.t


class _Sub:
    """subprocess stand-in keyed by the CLAUDE_CONFIG_DIR the call carries ("" = unset)."""
    TimeoutExpired = _real_sp.TimeoutExpired

    def __init__(self, outs):
        self.outs, self.calls = outs, []

    def run(self, argv, env=None, **kw):
        d = (env or {}).get("CLAUDE_CONFIG_DIR", "")
        self.calls.append((list(argv), dict(env or {})))
        v = self.outs[d]
        if isinstance(v, BaseException):
            raise v
        return mock.Mock(stdout=v)


def _rows(*pids):
    return json.dumps([{"pid": p, "sessionId": "s%d" % p} for p in pids])


class AgentViewAccounts(unittest.TestCase):
    def setUp(self):
        self.clock = _Clock()
        self.sub = _Sub({})
        self.accs = [{"dir": PRIM, "label": "main", "primary": True}]
        roots = types.SimpleNamespace(accounts=lambda: [dict(a) for a in self.accs], SCAN_HOME=HOME)
        base_env = {"PATH": "/bin", "CLAUDE_CONFIG_DIR": PRIM}
        for name, val in (("time", self.clock), ("subprocess", self.sub), ("claude_roots", roots),
                          ("warn_once", lambda key, msg, **kw: None), ("bin_path", lambda n: n),
                          ("bin_forget", lambda n: None), ("rich_env", lambda: dict(base_env)),
                          ("_slow_why", lambda: [])):
            p = mock.patch.object(lp, name, val)
            p.start()
            self.addCleanup(p.stop)
        saved = (list(lp._av_cache), list(lp._av_fail), dict(lp._av_acct), set(lp._av_unknown), dict(lp._stale))

        def restore():
            lp._av_cache[:], lp._av_fail[:] = saved[0], saved[1]
            lp._av_acct.clear(), lp._av_acct.update(saved[2])
            lp._av_unknown.clear(), lp._av_unknown.update(saved[3])
            lp._stale.clear(), lp._stale.update(saved[4])
        self.addCleanup(restore)
        lp._av_cache[:] = [0.0, None]
        lp._av_fail[:] = [0.0]
        lp._av_acct.clear()
        lp._av_unknown.clear()

    def two(self):
        self.accs.append({"dir": WORK, "label": "work", "primary": False})

    def test_single_account_one_call_env_unchanged(self):
        self.sub.outs[PRIM] = _rows(1)
        self.assertEqual(set(lp.agent_view()), {"1"})
        self.assertEqual(len(self.sub.calls), 1)
        self.assertEqual(self.sub.calls[0][1], {"PATH": "/bin", "CLAUDE_CONFIG_DIR": PRIM})
        self.assertEqual(lp.agent_view_unknown(), set())

    def test_union_of_accounts(self):
        self.two()
        self.sub.outs[PRIM] = _rows(1)
        self.sub.outs[WORK] = _rows(2, 3)
        self.assertEqual(set(lp.agent_view()), {"1", "2", "3"})
        self.assertEqual(lp.agent_view_unknown(), set())
        self.assertEqual(lp._av_cache[1], lp.agent_view())   # term.py reads the merged view here

    def test_duplicate_realpath_asked_once(self):
        self.accs.append({"dir": PRIM, "label": "again", "primary": False})
        self.sub.outs[PRIM] = _rows(1)
        lp.agent_view()
        self.assertEqual(len(self.sub.calls), 1)

    def test_one_failing_keeps_others_and_is_negative_cached(self):
        self.two()
        self.sub.outs[PRIM] = _rows(1)
        self.sub.outs[WORK] = _real_sp.TimeoutExpired("claude", 6)
        self.assertEqual(set(lp.agent_view()), {"1"})
        self.assertEqual(lp.agent_view_unknown(), {"work"})
        n = len(self.sub.calls)
        self.clock.t += lp.AGENTS_TTL + 1                      # primary refreshes, dead account does not fork
        lp.agent_view()
        self.assertEqual([c[1].get("CLAUDE_CONFIG_DIR") for c in self.sub.calls[n:]], [PRIM])

    def test_all_failing_is_none(self):
        self.two()
        self.sub.outs[PRIM] = ValueError("x")
        self.sub.outs[WORK] = ValueError("x")
        self.assertIsNone(lp.agent_view())
        self.assertEqual(lp.agent_view_unknown(), {"", "work"})

    def test_default_dir_runs_without_config_var(self):
        self.accs.append({"dir": DEFAULT, "label": "default", "primary": False})
        self.sub.outs[PRIM] = _rows(1)
        self.sub.outs[""] = _rows(9)
        self.assertEqual(set(lp.agent_view()), {"1", "9"})
        self.assertNotIn("CLAUDE_CONFIG_DIR", self.sub.calls[1][1])


if __name__ == "__main__":
    unittest.main()
