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

    def test_never_ran_only_from_telemetry_with_enough_days(self):
        def one(**kw):
            b = {"events": [{"ev": "PreToolUse", "hooks": [_hook(matcher="Bash", **kw)]}], "scanning": False}
            h = V.verdict(b, 14)["events"][0]["hooks"][0]
            return (h["vd"]["why"], h["vd"]["vp"]) if "vd" in h else None
        self.assertEqual(one(n=0, nsrc="otel", ndays=5), ("never_ran", {"days": 5, "matcher": "Bash"}))
        self.assertIsNone(one(n=0, nsrc="otel", ndays=2))       # too short to tell unused from quiet
        self.assertIsNone(one(n=3, nsrc="otel", ndays=9))
        self.assertIsNone(one(n=None, ndays=9))                  # transcript-only: no record proves nothing

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

    def test_otel_counts_fill_silent_hooks(self):
        from unittest import mock
        it = {"key": ["hooks", "PreToolUse"], "scope": "user", "file": "/nonexistent/settings.json",
              "entry": {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 /nonexistent/g.py"}]}}
        with mock.patch.object(H, "hook_fires", return_value=(0, "2026-10-20", False)), \
                mock.patch.object(H, "hook_cost", return_value=None), \
                mock.patch.object(H, "_days_since", return_value=7):
            h = next(r["hooks"] for r in H._hook_rows([it], "/nonexistent", {}, since="2026-10-12") if r["ev"] == "PreToolUse")[0]
        self.assertEqual((h["n"], h["quiet"], h["nsrc"], h["nfrom"], h["ndays"], h["cost"]), (0, 0, "otel", "2026-10-20", 7, None))
        with mock.patch.object(H, "hook_fires", return_value=(0, "2026-10-26", False)), \
                mock.patch.object(H, "hook_cost", return_value=None), \
                mock.patch.object(H, "_days_since", return_value=1):   # coverage too short: 0 stays unknown
            h = next(r["hooks"] for r in H._hook_rows([it], "/nonexistent", {}, since="2026-10-12") if r["ev"] == "PreToolUse")[0]
        self.assertEqual((h["n"], h["quiet"], h["nsrc"]), (None, 1, ""))
        with mock.patch.object(H, "hook_fires", return_value=(4, "2026-10-20", True)):   # ambiguous: keep transcript count
            h = next(r["hooks"] for r in H._hook_rows([it], "/nonexistent", {}, since="2026-10-12") if r["ev"] == "PreToolUse")[0]
        self.assertEqual((h["n"], h["quiet"], h["nsrc"]), (None, 1, ""))

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

    def _cost_rows(self, groups, cost, runs):
        from unittest import mock
        items = [{"key": ["hooks", "PreToolUse"], "scope": sc, "file": "/nonexistent/settings.json",
                  "entry": {"matcher": m, "hooks": [{"type": "command", "command": "python3 /nonexistent/%s.py" % i}]}}
                 for i, (sc, m) in enumerate(groups)]
        with mock.patch.object(H, "hook_fires", return_value=(runs, "2026-10-20", False)), \
                mock.patch.object(H, "hook_cost", return_value=cost), \
                mock.patch.object(H, "_days_since", return_value=7):
            hs = next(r["hooks"] for r in H._hook_rows(items, "/nonexistent", {}, since="2026-10-12") if r["ev"] == "PreToolUse")
        for h in hs:
            h["miss"] = 0   # the fake script paths do not exist; only cost verdicts are under test
        return hs

    def test_r1_r2_cost_rollup_and_k(self):
        c = {"mruns": 4, "ms": 4002, "blk": 0, "out": 1, "subs": ["Bash"], "amb": False}
        hs = self._cost_rows([("user", "Bash"), ("project", "Bash|Edit")], c, 4)
        # R1 avg = ms / mruns; R2 two hooks fit Bash, both rows carry the same combined time
        self.assertEqual([h["cost"] for h in hs], [{"runs": 4, "avg": 1000, "blk": 0, "out": 1, "k": 2}] * 2)
        hs = self._cost_rows([("user", "Bash"), ("user", "Read")], c, 4)
        self.assertEqual([h["cost"]["k"] for h in hs], [1, 1])   # R2: a non-fitting matcher is not combined
        b = V.verdict({"events": [{"ev": "PreToolUse", "hooks": hs}], "scanning": False}, 30)
        self.assertEqual(b["events"][0]["hooks"][0]["vd"]["vp"], {"avg": 1000, "runs": 4, "k": 1, "min": V.VD_SLOW_MS})

    def test_r4_cost_none_or_partial(self):
        self.assertIsNone(self._cost_rows([("user", "Bash")], None, 3)[0]["cost"])
        amb = {"mruns": 4, "ms": 40, "blk": 0, "out": 0, "subs": ["Bash"], "amb": True}
        self.assertIsNone(self._cost_rows([("user", "Bash")], amb, 4)[0]["cost"])
        # some firings unmeasured: blk/out unknown, never read as clean (R3 cannot fire)
        part = {"mruns": 60, "ms": 600, "blk": 0, "out": 0, "subs": ["Bash"], "amb": False}
        hs = self._cost_rows([("user", "Bash")], part, 80)
        self.assertEqual(hs[0]["cost"], {"runs": 60, "avg": 10, "blk": None, "out": None, "k": 1})
        self.assertNotIn("vd", V.verdict({"events": [{"ev": "PreToolUse", "hooks": hs}], "scanning": False}, 30)["events"][0]["hooks"][0])

    def test_r1_r3_slow_and_no_effect_verdicts(self):
        def one(cost, scanning=False):
            b = {"events": [{"ev": "PostToolUse", "hooks": [_hook(matcher="Bash", cost=cost)]}], "scanning": scanning}
            r = V.verdict(b, 30)["events"][0]["hooks"][0]
            return (r["vd"]["lvl"], r["vd"]["why"], r["vd"]["vp"]) if "vd" in r else None
        c = {"runs": 3, "avg": 1000, "blk": 1, "out": 1, "k": 2}
        self.assertEqual(one(c), ("check", "slow", {"avg": 1000, "runs": 3, "k": 2, "min": 1000}))   # R1 + R2
        self.assertIsNone(one(dict(c, avg=999)))
        self.assertIsNone(one(c, scanning=True))                                     # partial body
        q = {"runs": 50, "avg": 10, "blk": 0, "out": 0, "k": 1}
        self.assertEqual(one(q), ("check", "no_effect", {"runs": 50, "min": 50}))                 # R3
        self.assertIsNone(one(dict(q, runs=49)))
        self.assertIsNone(one(dict(q, out=1)))
        self.assertIsNone(one(dict(q, blk=1)))
        self.assertIsNone(one(dict(q, out=None)))                                    # R4 not measured is not clean
        self.assertIsNone(one(None))
        # order: slow_block before slow, slow before never_ran
        b = {"events": [{"ev": "Stop", "hooks": [_hook(timeout=60, cost=c)]}], "scanning": False}
        self.assertEqual(V.verdict(b, 30)["events"][0]["hooks"][0]["vd"]["why"], "slow_block")

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
