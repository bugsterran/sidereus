"""Boot warms enter `boot_queue.gate(<ORDER name>)` around their heavy part (issue #20: R1 one at a time, R2 peak, R4 warm cache)."""
import ast
import contextlib
import inspect
import tempfile
import textwrap
import unittest

from tests._load import sidereus

bq = sidereus("boot_queue")
tl = sidereus("timeline")
ti = sidereus("toolidx")
burn = sidereus("burn")
git = sidereus("git")

# name -> (module, function): every ORDER entry has exactly one call site (R1).
SITES = {"today_loop": ("burn_scan", "_today_loop"), "usage_loop": ("quota_loop", "_usage_loop"),
         "fail_loop": ("failures", "_fail_loop"), "qburn_warm": ("burn", "_qburn_warm"),
         "win_loop": ("live_win", "_win_loop"), "tl_warm": ("timeline", "_tl_warm"),
         "toolidx_warm": ("toolidx", "warm"), "br_boot_warm": ("git", "br_boot_warm"),
         "wkuse_loop": ("burn_usage", "_wkuse_loop"), "struct_warm": ("structure", "_struct_warm_loop")}


class Recorder(unittest.TestCase):
    def setUp(self):
        self._gate = bq.gate
        self.log, self.inside = [], []

        @contextlib.contextmanager
        def rec(name):
            self.log.append(("enter", name))
            self.inside.append(name)
            try:
                yield
            finally:
                self.inside.pop()
                self.log.append(("exit", name))
        bq.gate = rec

    def tearDown(self):
        bq.gate = self._gate

    def mark(self, tag):
        return lambda *a, **k: self.log.append((tag, tuple(self.inside)))


class GateRuns(Recorder):
    def test_tl_warm_runs_inside_gate(self):      # R1 R4
        saved = (tl.agents_timeline, tl.TL_WARM_DELAY_S)
        try:
            tl.agents_timeline, tl.TL_WARM_DELAY_S = self.mark("tl"), 0
            tl._tl_warm()
        finally:
            tl.agents_timeline, tl.TL_WARM_DELAY_S = saved
        self.assertEqual(self.log, [("enter", "tl_warm"), ("tl", ("tl_warm",)), ("tl", ("tl_warm",)),
                                    ("exit", "tl_warm")])

    def test_toolidx_warm_runs_inside_gate(self):  # R1 R4
        saved = (ti.TI_BG, ti._bg_warm, ti.tool_uses, ti.mcp_status, ti._TI_STATE.get("bg"))
        try:
            ti.TI_BG = True
            ti._bg_warm, ti.tool_uses, ti.mcp_status = self.mark("bg"), self.mark("tu"), self.mark("mcp")
            ti.warm(0)
        finally:
            ti.TI_BG, ti._bg_warm, ti.tool_uses, ti.mcp_status, ti._TI_STATE["bg"] = saved
        self.assertEqual([e for e in self.log if e[0] in ("bg", "tu", "mcp")],
                         [(t, ("toolidx_warm",)) for t in ("bg", "tu", "mcp")])
        self.assertEqual(self.log[0], ("enter", "toolidx_warm"))

    def test_qburn_warm_gate_after_live_wait(self):  # R1: never held across the live-sample wait
        saved = (burn._qb_live, burn._qb_full, burn._qb_body, dict(burn._qb_warm))
        try:
            burn._qb_live = lambda: (self.log.append(("live", tuple(self.inside))), True)[1]
            burn._qb_full, burn._qb_body = self.mark("full"), self.mark("body")
            burn._qburn_warm()
        finally:
            burn._qb_live, burn._qb_full, burn._qb_body = saved[:3]
            burn._qb_warm.clear()
            burn._qb_warm.update(saved[3])
        self.assertEqual(self.log[0], ("live", ()))     # the wait loop's check sits outside the gate
        self.assertIn(("full", ("qburn_warm",)), self.log)
        self.assertNotIn("body", [e[0] for e in self.log])

    def test_br_boot_warm_runs_inside_gate(self):  # R1 R4
        d = tempfile.mkdtemp(prefix="sidereus-bq-")
        saved = (git._br_seen_load, git._branch_ok, git.git_slot_free, git.branch_graph, git._br_warm_start,
                 dict(git._br_seen), dict(git._br_want))
        try:
            git._br_seen_load = lambda now: {(d, 10): 1.0}
            git._branch_ok = lambda cwd: True
            git.git_slot_free = lambda w: True
            git.branch_graph, git._br_warm_start = self.mark("graph"), lambda: None
            done = git.br_boot_warm(now=100.0)
        finally:
            (git._br_seen_load, git._branch_ok, git.git_slot_free, git.branch_graph,
             git._br_warm_start) = saved[:5]
            git._br_seen.clear()
            git._br_seen.update(saved[5])
            git._br_want.clear()
            git._br_want.update(saved[6])
        self.assertEqual(done, [(d, 10)])
        self.assertEqual(self.log, [("enter", "br_boot_warm"), ("graph", ("br_boot_warm",)),
                                    ("exit", "br_boot_warm")])


class _Stop(Exception):
    pass


class EarlyReturns(Recorder):
    """Each nothing-to-do path calls boot_queue.done(name) so the queue drains before its time cap (R1 R4)."""
    def setUp(self):
        super().setUp()
        self._done, self._others = bq.done, bq.others_done
        self.done = []
        bq.done = self.done.append

    def tearDown(self):
        bq.done, bq.others_done = self._done, self._others
        super().tearDown()

    def test_toolidx_off_calls_done(self):
        saved = ti.TI_BG
        try:
            ti.TI_BG = False
            ti.warm(0)
        finally:
            ti.TI_BG = saved
        self.assertEqual(self.done, ["toolidx_warm"])
        self.assertEqual(self.log, [])

    def test_br_no_keys_calls_done(self):
        saved = git._br_seen_load
        try:
            git._br_seen_load = lambda now: {}
            self.assertEqual(git.br_boot_warm(now=1.0), [])
        finally:
            git._br_seen_load = saved
        self.assertEqual(self.done, ["br_boot_warm"])
        self.assertEqual(self.log, [])

    def test_br_busy_slot_is_bounded_and_skips(self):
        d = tempfile.mkdtemp(prefix="sidereus-bq-")
        probes, naps = [], []
        saved = (git._br_seen_load, git._branch_ok, git.git_slot_free, git.branch_graph, git.time,
                 dict(git._br_seen))
        try:
            git._br_seen_load = lambda now: {(d, 10): 1.0}
            git._branch_ok = lambda cwd: True
            git.git_slot_free = lambda w: probes.append(w) and False
            git.branch_graph = self.mark("graph")
            git.time = type("T", (), {"time": staticmethod(lambda: 1.0), "sleep": staticmethod(naps.append)})
            self.assertEqual(git.br_boot_warm(now=1.0), [])
        finally:
            (git._br_seen_load, git._branch_ok, git.git_slot_free, git.branch_graph, git.time) = saved[:5]
            git._br_seen.clear()
            git._br_seen.update(saved[5])
        self.assertEqual(len(probes), git.BR_WARM_PROBES)
        self.assertLessEqual(sum(naps) + sum(probes), 11)
        self.assertEqual(self.log, [("enter", "br_boot_warm"), ("exit", "br_boot_warm")])

    def _struct_ticks(self, n, act, targets):
        st = sidereus("structure")
        ticks, clock = [], [1000.0]

        def sleep(s):
            if len(ticks) >= n:
                raise _Stop()
            ticks.append(s)
            clock[0] += 100
        saved = (st.time, st._struct_act[0], st._struct_warm_targets, dict(st._struct_warm_seen),
                 st._struct_prune_at[0], st._struct_disk_prune, st.structure)
        try:
            st.time = type("T", (), {"time": staticmethod(lambda: clock[0]), "sleep": staticmethod(sleep)})
            st._struct_act[0] = act(clock)
            st._struct_warm_targets = lambda: targets
            st._struct_disk_prune = lambda: None
            st.structure = self.mark("struct")
            with self.assertRaises(_Stop):
                st._struct_warm_loop()
        finally:
            st.time, st._struct_act[0], st._struct_warm_targets = saved[:3]
            st._struct_warm_seen.clear()
            st._struct_warm_seen.update(saved[3])
            st._struct_prune_at[0], st._struct_disk_prune, st.structure = saved[4:]

    def test_struct_no_target_calls_done(self):
        self._struct_ticks(1, lambda c: 0.0, [])
        self.assertEqual(self.done, ["struct_warm"])

    def test_struct_busy_user_waits_until_others_done(self):
        bq.others_done = lambda name: False
        self._struct_ticks(1, lambda c: c[0] + 100, ["/r"])
        self.assertEqual(self.done, [])
        bq.others_done = lambda name: True
        self._struct_ticks(1, lambda c: c[0] + 100, ["/r"])
        self.assertEqual(self.done, ["struct_warm"])


def _gate_names(fn):
    """Names passed to `boot_queue.gate("...")` inside fn's source."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    out = []
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "gate"
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "boot_queue"
                and n.args and isinstance(n.args[0], ast.Constant)):
            out.append(n.args[0].value)
    return out


class CallSites(unittest.TestCase):
    def test_every_order_name_has_its_call_site(self):   # R1
        self.assertEqual(set(SITES), set(bq.ORDER))
        for name, (mod, fn) in SITES.items():
            with self.subTest(name=name):
                self.assertEqual(_gate_names(getattr(sidereus(mod), fn)), [name])


if __name__ == "__main__":
    unittest.main()
