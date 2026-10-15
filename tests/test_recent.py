"""«최근 끝난 세션» (sidereus/recent.py + web/js/41b-sesrecent.js): window, live exclusion, cap, cache, metadata only, shell quoting."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unittest

from tests._load import sidereus, js_all
from tests._node import node_e

R = sidereus("recent")
NOW = 1_790_000_000.0


class _Clock:
    def __init__(self, t):
        self.t = t

    def time(self):
        return self.t


def _sid(i):
    return "%08x-1111-2222-3333-444455556666" % (0xab000000 + i)


class RecentList(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-recent-")
        self.files, self.saved = {}, {}
        self.live_snap, self.alive, self.sess_calls = [], set(), [0]
        self.refresh = [0]
        self.clock = _Clock(NOW)

        def fake_sessions():            # counts helper calls; the helper itself never runs sessions() here
            self.sess_calls[0] += 1
            return []
        patches = {
            "_uidx": {"files": self.files}, "_uidx_lock": threading.Lock(),
            "_uidx_refresh": lambda: self.refresh.__setitem__(0, self.refresh[0] + 1),
            "sessions_rows": lambda **k: fake_sessions() or self.live_snap or [],
            "sid_alive": lambda s: s in self.alive, "_wt_of": lambda cwd: None,
            "_cwd_from_slug": lambda sl: "", "_ctx_window": lambda m, c: (1_000_000 if c > 200_000 else 200_000, "x"),
            "time": self.clock, "_recent_cache": {}, "_probe_memo": sidereus("memo").BoundedMemo(64),
        }
        for k, v in patches.items():
            self.saved[k] = getattr(R, k)
            setattr(R, k, v)

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(R, k, v)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def add(self, i, age_s, cwd="/w/p", ctx=50_000, body="SECRET-PROMPT", sub_tok=0):
        sid = _sid(i)
        fp = os.path.join(self.tmp, "-w-p", sid + ".jsonl")
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        lines = [{"type": "user", "cwd": cwd, "sessionId": sid, "gitBranch": "feat/x", "timestamp": "2026-09-20T01:00:00Z",
                  "message": {"content": body}},
                 {"type": "assistant", "cwd": cwd, "sessionId": sid, "timestamp": "2026-09-20T01:00:05Z",
                  "message": {"model": "claude-opus-4-1", "content": [{"type": "text", "text": body}],
                              "usage": {"input_tokens": 10, "cache_read_input_tokens": ctx, "cache_creation_input_tokens": 0}}}]
        with open(fp, "w") as f:
            f.write("\n".join(json.dumps(x) for x in lines) + "\n")
        sz = os.path.getsize(fp)
        self.files[fp] = {"sl": "-w-p", "mt": NOW - age_s, "sz": sz, "br": "old-br",
                          "h": {"1789990000": {"claude-opus-4-1": [100, 20, 3, 7]}}}
        if sub_tok:
            sp = os.path.join(self.tmp, "-w-p", sid, "subagents", "agent-a1.jsonl")
            self.files[sp] = {"sl": "-w-p", "mt": NOW - age_s, "sz": 1, "h": {"1789990000": {"m": [sub_tok, 0, 0, 0]}}}
        return sid

    def test_window_order_live_and_shape(self):
        a = self.add(1, 3600)
        b = self.add(2, 60, ctx=300_000, sub_tok=1000)
        self.add(3, 8 * 86400)                       # outside 7 days
        c = self.add(4, 120)
        d = self.add(5, 30)
        self.alive.add(c)                            # confirmed live by id
        self.live_snap = [{"sid": d, "state": "wait", "plat": "cc"}, {"sid": a, "state": "done", "plat": "cc"}]
        out = R.recent_sessions(7)
        self.assertTrue(out["ok"])
        self.assertEqual([r["sid"] for r in out["rows"]], [b, a])
        r = out["rows"][0]
        self.assertEqual((r["cwd"], r["branch"], r["name"], r["pct"]), ("/w/p", "feat/x", "p", 30))
        # only the keys 41b-sesrecent.js reads
        self.assertEqual(set(r), {"sid", "cwd", "name", "branch", "model", "endedAt", "pct", "gone", "agentDesc"})
        self.assertEqual(r["agentDesc"], "")             # no Agent call in this transcript
        self.assertEqual(r["endedAt"], int(NOW - 60))
        self.assertTrue(r["gone"])                   # /w/p does not exist here
        self.assertNotIn("SECRET-PROMPT", json.dumps(out))
        self.assertFalse({"title", "task", "prompt", "reply"} & set(r))
        self.assertEqual(self.sess_calls[0], 1)          # one snapshot-helper call per list build

    def test_agent_desc_is_the_only_tool_input_kept(self):
        sid = self.add(1, 60)
        fp = next(k for k in self.files if sid in k)
        msgs = [{"type": "assistant", "message": {"content": [
                    {"type": "tool_use", "name": "Agent", "input": {"description": "old  task", "prompt": "SECRET-A"}}]}},
                {"type": "assistant", "message": {"content": [
                    {"type": "tool_use", "name": "Agent", "input": {"description": "  fix\nthe  chat ", "prompt": "SECRET-B"}},
                    {"type": "tool_use", "name": "Bash", "input": {"command": "SECRET-C", "description": "SECRET-D"}}]}}]
        with open(fp, "a") as f:
            f.write("\n".join(json.dumps(x) for x in msgs) + "\n")
        self.files[fp]["sz"] = os.path.getsize(fp)
        out = R.recent_sessions(7)
        self.assertEqual(out["rows"][0]["agentDesc"], "fix the chat")   # newest Agent call, whitespace folded
        self.assertNotIn("SECRET", json.dumps(out))

    def test_no_snapshot_lists_via_snapshot_helper(self):
        self.live_snap = None                       # helper returned [] (no snapshot): nothing is live
        self.add(1, 60)
        self.assertEqual(R.recent_sessions(7)["n"], 1)
        self.assertEqual(self.sess_calls[0], 1)

    def test_cap_and_total(self):
        for i in range(R.RECENT_CAP + 5):
            self.add(i, 100 + i)
        out = R.recent_sessions(7)
        self.assertEqual((out["n"], out["total"]), (R.RECENT_CAP, R.RECENT_CAP + 5))
        self.assertEqual(out["rows"][0]["sid"], _sid(0))

    def test_cache_30s(self):
        self.add(1, 60)
        R.recent_sessions(7)
        self.add(2, 50)
        self.clock.t = NOW + 10
        self.assertEqual(R.recent_sessions(7)["n"], 1)
        self.assertEqual(self.refresh[0], 1)
        self.clock.t = NOW + R.RECENT_TTL_S + 1
        self.assertEqual(R.recent_sessions(7)["n"], 2)

    def test_days_clamped_and_bad_sid_skipped(self):
        self.files[os.path.join(self.tmp, "x", "not a sid.jsonl")] = {"sl": "x", "mt": NOW - 5, "sz": 0, "h": {}}
        self.add(1, 60)
        out = R.recent_sessions("junk")
        self.assertEqual((out["days"], out["n"]), (7, 1))
        self.assertEqual(R.recent_sessions(999)["days"], R.RECENT_MAX_DAYS)


class ShellQuote(unittest.TestCase):
    """srecCmd() output run through /bin/sh must land in the exact path, including spaces and quotes."""

    def _cmd(self, cwd, sid):
        src = js_all()
        fns = re.search(r"^function shq\(.*$\n", src, re.M).group(0)          # shared helpers live in 40b
        fns += re.search(r"^function resumeCmd\(.*?^}\n", src, re.M | re.S).group(0)
        fns += re.search(r"^function srecCmd\(r\).*$\n", src, re.M).group(0)
        js = fns + "process.stdout.write(JSON.stringify(srecCmd(%s)));" % json.dumps({"cwd": cwd, "sid": sid})
        return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True).stdout)

    def test_paths_round_trip(self):
        base = tempfile.mkdtemp(prefix="sidereus-shq-")
        try:
            for name in ("plain", "with space", "it's", "a'b\"c $HOME `x` \\n"):
                d = os.path.join(base, name)
                os.makedirs(d)
                cmd = self._cmd(d, _sid(1))
                self.assertTrue(cmd.endswith(" && claude --resume " + _sid(1)), cmd)
                probe = cmd.replace("claude --resume " + _sid(1), "pwd -P")
                got = subprocess.run(["/bin/sh", "-c", probe], capture_output=True, text=True, check=True).stdout.rstrip("\n")
                self.assertEqual(got, os.path.realpath(d))
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_bad_sid_gives_no_command(self):
        self.assertEqual(self._cmd("/w", "x; rm -rf /"), "")
        self.assertEqual(self._cmd("", _sid(2)), "claude --resume " + _sid(2))


class DemoRecent(unittest.TestCase):
    def test_three_synthetic_rows(self):
        demo = sidereus("demo")
        w = demo.World(anchor=1_790_000_000, page_build="x", now=1_790_000_000)

        class U:
            query = "days=7"
        code, out = demo.respond(w, "/api/sessions/recent", U())
        self.assertEqual((code, out["n"]), (200, 3))
        self.assertTrue(all(r["cwd"].startswith("/home/demo/") for r in out["rows"]))


if __name__ == "__main__":
    unittest.main()
