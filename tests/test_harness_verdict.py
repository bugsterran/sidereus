"""Harness check (sidereus/harness_verdict.py): every why code, priority, counts, ids, metadata-only args;
harness._hook_rows `miss`/`ch` fields. Plain dicts only — no live files."""
import os
import tempfile
import unittest

from tests._load import load, sidereus

load()
V = sidereus("harness_verdict")
H = sidereus("harness")


def _hook(**kw):
    h = {"src": "user", "scope": "user", "matcher": "", "cmd": "a.py", "ch": "", "timeout": None, "n": None, "miss": 0}
    h.update(kw)
    return h


def _body():
    return {"events": [
        {"ev": "PreToolUse", "hooks": [
            _hook(cmd="gone.py", miss=1),
            _hook(matcher="Bash", cmd="x.py", ch="aaaa1111", n=5),
            _hook(matcher="Bash", cmd="x.py", ch="aaaa1111", src="project", n=5),
            _hook(matcher="Edit", cmd="slow.py", timeout=60, n=2),
            _hook(matcher="Write", cmd="never.py", nomatch=1),
            _hook(cmd="fine.py", n=3, timeout=10)]},
        {"ev": "PostToolUse", "hooks": [_hook(matcher="Read", cmd="quiet.py"), _hook(cmd="slow2.py", timeout=120)]}],
        "scanning": False,
        "rules": [{"path": "~/a/AGENTS.md", "size": 50000}, {"path": "~/b/AGENTS.md", "size": 100}],
        "agents": [{"name": "ghost", "scope": "", "open": "", "pipes": [{"pipe": "p1", "stage": "구현"}]},
                   {"name": "general-purpose", "scope": "", "open": "", "pipes": [{"pipe": "p1", "stage": "x"}]},
                   {"name": "real", "scope": "project", "open": "a:real", "pipes": [{"pipe": "p1", "stage": "y"}]}],
        "skills": [{"name": "noskill", "scope": "", "open": "", "pipes": [{"pipe": "p2", "stage": "s"}]},
                   {"name": "sk", "scope": "user", "open": "s:0", "pipes": []}],
        "mcps": [{"name": "m1", "status": "fail", "err": "-32000"}, {"name": "m2", "status": "ok", "err": ""}]}


class VerdictTest(unittest.TestCase):
    def setUp(self):
        self.b = V.verdict(_body(), 30)
        pre, post = self.b["events"]
        self.pre, self.post = pre["hooks"], post["hooks"]

    def _why(self, row):
        return (row["vd"]["lvl"], row["vd"]["why"]) if "vd" in row else None

    def test_hooks(self):
        self.assertEqual(self._why(self.pre[0]), ("bad", "hook_missing"))
        self.assertEqual(self.pre[0]["vd"]["vp"], {"ev": "PreToolUse", "cmd": "gone.py"})
        self.assertIsNone(self._why(self.pre[1]))
        self.assertEqual(self._why(self.pre[2]), ("check", "dup"))
        self.assertEqual(self.pre[2]["vd"]["vp"]["srcs"], ["user", "project"])
        self.assertEqual(self.pre[3]["vd"]["vp"], {"ev": "PreToolUse", "timeout": 60})
        self.assertEqual(self.pre[4]["vd"], {"lvl": "check", "why": "idle", "vp": {"days": 30, "matcher": "Write"}, "id": self.pre[4]["vd"]["id"]})
        self.assertIsNone(self._why(self.pre[5]))

    def test_idle_only_from_nomatch(self):
        # no run record proves nothing: silent hooks write none
        self.assertIsNone(self._why(self.post[0]))
        b = _body()
        b["scanning"] = True                                    # partial tool index: never idle
        self.assertNotIn("vd", V.verdict(b, 30)["events"][0]["hooks"][4])
        # PostToolUse is not an event the session waits on
        self.assertIsNone(self._why(self.post[1]))

    def test_rows_and_counts(self):
        b = self.b
        self.assertEqual(self._why(b["rules"][0]), ("check", "rule_big"))
        self.assertEqual(b["rules"][0]["vd"]["vp"], {"bytes": 50000})
        self.assertIsNone(self._why(b["rules"][1]))
        self.assertEqual(b["agents"][0]["vd"]["vp"], {"pipe": "p1", "stage": "구현"})
        self.assertEqual([self._why(r) for r in b["agents"][1:]], [None, None])
        self.assertEqual(self._why(b["skills"][0]), ("bad", "ref_missing"))
        self.assertEqual(self._why(b["mcps"][0]), ("bad", "mcp_fail"))
        self.assertIsNone(self._why(b["mcps"][1]))
        self.assertEqual(b["verdict"], {"bad": 4, "check": 4, "ok": 9})
        ids = [r["vd"]["id"] for e in b["events"] for r in e["hooks"] if "vd" in r]
        ids += [r["vd"]["id"] for k in ("rules", "agents", "skills", "mcps") for r in b[k] if "vd" in r]
        self.assertEqual(ids, ["v%d" % i for i in range(8)])

    def test_rerun_is_idempotent_and_empty_body(self):
        b = V.verdict(self.b, 30)
        self.assertEqual(b["verdict"], {"bad": 4, "check": 4, "ok": 9})
        self.assertEqual(V.verdict({}, 7)["verdict"], {"bad": 0, "check": 0, "ok": 0})

    def test_no_dup_without_hash(self):   # cmd is a basename / type name: never a dup key
        b = V.verdict({"events": [{"ev": "Stop", "hooks": [_hook(cmd="s.sh", src="a"), _hook(cmd="s.sh", src="b")]}]}, 30)
        self.assertNotIn("vd", b["events"][0]["hooks"][1])


class HookRowFieldsTest(unittest.TestCase):
    def test_nomatch(self):
        tools = ["Bash", "Read", "mcp__docs__search"]
        self.assertEqual(H._nomatch("PreToolUse", "Write|Edit", tools), 1)
        self.assertEqual(H._nomatch("PreToolUse", "Task|Agent|Bash", tools), 0)
        self.assertEqual(H._nomatch("PostToolUse", "mcp__docs__.*", tools), 0)
        self.assertEqual(H._nomatch("PreToolUse", "*", tools), 0)
        self.assertEqual(H._nomatch("PreToolUse", "Write", []), 0)          # nothing indexed: unknown
        self.assertEqual(H._nomatch("Stop", "Write", tools), 0)             # not a tool event
        self.assertEqual(H._nomatch("PreToolUse", "(", tools), 1)           # bad regex: plain compare

    def test_miss_and_ch(self):
        tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-vd-"))
        here = os.path.join(tmp, "here.py")
        with open(here, "w", encoding="utf-8") as f:
            f.write("print(1)\n")
        gone = os.path.join(tmp, "gone.py")
        cmds = ["python3 " + here, "python3 " + gone]
        it = {"key": ["hooks", "Stop"], "scope": "user", "file": os.path.join(tmp, "settings.json"),
              "entry": {"hooks": [{"type": "command", "command": c} for c in cmds]}}
        rows = H._hook_rows([it], tmp, {"tool:Bash": {"n": 1, "last": 1}})
        hs = next(r["hooks"] for r in rows if r["ev"] == "Stop")
        self.assertEqual([h["miss"] for h in hs], [0, 1])
        self.assertEqual(hs[1]["ch"], H.hook_hash(cmds[1])[:8])
        self.assertNotIn(gone, repr(rows))

    def test_prompt_hooks_not_dup(self):
        it = {"key": ["hooks", "UserPromptSubmit"], "scope": "user", "file": "/nonexistent/settings.json",
              "entry": {"hooks": [{"type": "prompt", "prompt": "check A"}, {"type": "prompt", "prompt": "check B"},
                                  {"type": "prompt", "prompt": "check A"}]}}
        rows = H._hook_rows([it], "/nonexistent", {})
        b = V.verdict({"events": rows, "scanning": False}, 30)
        hs = next(r["hooks"] for r in b["events"] if r["ev"] == "UserPromptSubmit")
        self.assertEqual([(h.get("vd") or {}).get("why") for h in hs], [None, None, "dup"])
        self.assertNotIn("check A", repr(rows))   # hash only

    def test_plat_same_basename_not_dup(self):
        P = sidereus("harness_plat")
        tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-vdp-"))
        for d in ("a", "b"):
            os.makedirs(os.path.join(tmp, d))
            with open(os.path.join(tmp, d, "hook.py"), "w", encoding="utf-8") as f:
                f.write("print(1)\n")

        class Mod:
            LANE = {"Stop": "Stop"}

            @staticmethod
            def root():
                return tmp
        items = [{"ev": "Stop", "cmd": "python3 " + os.path.join(tmp, d, "hook.py"), "scope": "user"} for d in ("a", "b", "a")]
        orig = P.ctxsrc._git_root
        P.ctxsrc._git_root = lambda p: ""
        try:
            rows = P._hook_rows(Mod, items, tmp)
        finally:
            P.ctxsrc._git_root = orig
        b = V.verdict({"events": rows, "scanning": False}, 30)
        self.assertEqual([(h.get("vd") or {}).get("why") for h in b["events"][0]["hooks"]], [None, None, "dup"])

    def test_gemini_lane_slow_block(self):
        b = V.verdict({"events": [{"ev": "BeforeTool", "lane": "PreToolUse", "hooks": [_hook(timeout=60)]},
                                  {"ev": "AfterTool", "lane": "PostToolUse", "hooks": [_hook(timeout=60)]}], "scanning": False}, 30)
        self.assertEqual(b["events"][0]["hooks"][0]["vd"]["why"], "slow_block")
        self.assertNotIn("vd", b["events"][1]["hooks"][0])

    def test_health_ok_at(self):
        st = {"mcp:m": {"status": "ok", "err": "", "fail_at": 100, "ok_at": 200}}
        self.assertEqual(H._health(st, ["mcp:m"]), ("ok", "", 100, 200))
        self.assertEqual(H._health({}, ["mcp:m"]), ("none", "", 0, 0))


if __name__ == "__main__":
    unittest.main()
