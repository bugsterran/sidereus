"""Demo world: «Get started» checklist inputs (/api/diag plugin, pipeline `red`) and the `verdict` deny code in Harness."""
import unittest
from unittest import mock

from tests._load import sidereus

A = 1_790_000_000   # pinned anchor; the harness clocks are patched to it


class _U:
    def __init__(self, q=""):
        self.query = q


class DemoStatesS2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = sidereus("demo")
        cls.w = cls.demo.World(anchor=A, page_build="abc123def456", now=A)
        cls.dt = sidereus("demo_tools")
        cls.hc = sidereus("harness_cost")
        cls.hf = sidereus("harness_flow")

    def get(self, path, q=""):
        st, body = self.demo.respond(self.w, path, _U(q))
        self.assertEqual(st, 200, (path, body))
        return body

    def harness(self):
        with mock.patch.object(self.hc, "_now", lambda: A), mock.patch.object(self.hf, "_now", lambda: A):
            st, body = self.dt._demo_harness(A, "/api/harness")
        self.assertEqual(st, 200)
        return body

    def test_r3_diag_has_enabled_sidereus_plugin(self):
        """[R3] /api/diag answers in the diag shape with an enabled sidereus plugin (checklist step 1 done, not unknown)."""
        d = self.get("/api/diag")
        self.assertTrue(d["ok"])
        for k in ("overlaps", "silent", "shadow", "plugins"):
            self.assertIsInstance(d[k], list, k)
        self.assertIsInstance(d["sidereus"], dict)
        pl = [x for x in d["plugins"] if x["name"] == "sidereus"]
        self.assertEqual(len(pl), 1)
        self.assertIs(pl[0]["on"], True)
        self.assertTrue(pl[0]["version"] and pl[0]["accts"])
        d["plugins"].clear()   # a fresh copy per request
        self.assertTrue(self.get("/api/diag")["plugins"])

    def test_r3_pipeline_red_is_zero(self):
        """[R3] the demo pipeline carries `red` 0 (known, not red-checked) so the checklist shows 3/4."""
        web = self.w.by["web"]["cwd"]
        b = self.get("/api/pipelines", "proj=" + web)
        self.assertEqual(b["pipelines"][0]["red"], 0)

    def test_r3_pipe_red_matches_eval(self):
        """[R3] DEMO_PIPE `red` = DEMO_EVAL stages with red "pass" (one redcheck store in the real server); graded and
        suggestions agree with the stage verdicts."""
        ev, pipe = self.dt.DEMO_EVAL, self.dt.DEMO_PIPE
        self.assertEqual(pipe["red"], sum(1 for s in ev["stages"] if s["red"] == "pass"))
        self.assertEqual(ev["graded"]["n"], pipe["red"])
        v = sidereus("pl_eval_view")
        red = {s["title"]: s["red"] for s in ev["stages"]}
        got = v.suggest(pipe["stages"], None, red, set(ev["graded"]["unstable"]), {}, [], lambda t: "")
        self.assertEqual([(s["code"], s["stage"]) for s in got], [(s["code"], s["stage"]) for s in ev["sugg"]])

    def test_r4_verdict_deny_code(self):
        """[R4] «What is guarding» counts one `verdict` deny, three in total."""
        g = self.harness()["guards"]
        self.assertEqual(g["codes"].get("verdict"), 1)
        self.assertEqual(g["codes"], {"jump": 1, "skipgate": 1, "verdict": 1})
        self.assertEqual(g["deny"], 3)
        self.assertEqual(g["runs"], 1)

    def test_r4_gate_cost_unchanged(self):
        """[R4] «Gate cost» is the pre-change value for the same anchor: the verdict deny never reaches the cost runs."""
        c = self.harness()["cost"]
        self.assertEqual({k: c[k] for k in ("blocked", "gate_ms", "hook_ms", "overridden", "pause_ms", "unknown", "gate_lb")},
                         {"blocked": 3, "gate_ms": 2160000, "hook_ms": 50600, "overridden": 1, "pause_ms": 660000,
                          "unknown": 1, "gate_lb": False})
        self.assertEqual(sorted(x["code"] for x in c["ev"]["blocked"]), ["gate", "jump", "skipgate"])
        self.assertEqual([[e["c"] for e in r["dl"]] for r in self.dt._demo_cost_runs(A)], [["jump", "skipgate"], ["gate"]])


if __name__ == "__main__":
    unittest.main()
