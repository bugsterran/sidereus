"""Demo World reproduces the «Since your last visit» strip from fixture data (R5): `visitDemo` + runs ended after it.

Pinned anchor and clock, no live files. The verdict rule mirrors the client (any stage `o` "fail" = fail, else ended = pass).
"""
import os
import unittest

from tests._load import sidereus

demo = sidereus("demo")

A = 1_790_000_000
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Q:
    """urlparse result stand-in: demo.respond reads only `.query`."""
    def __init__(self, q=""):
        self.query = q


def _runs(st):
    """Every plrun head and past entry across session rows, keyed once by (sid, name, rid or t0)."""
    out = {}
    for row in st["sessions"]:
        for r in row.get("plrun") or ():
            for u in [r] + list(r.get("past") or ()):
                out[(row["sid"], r["name"], u.get("rid", u["t0"]))] = u
    return out


class R5DemoVisit(unittest.TestCase):
    def setUp(self):
        self.w = demo.World(anchor=A, page_build="b", now=A + 120)
        self.st = self.w.state()

    def test_r5_visit_demo_is_anchor_minus_4h(self):
        """[R5] demo state carries visitDemo = anchor - 4 h, independent of the request clock."""
        self.assertEqual(self.st["visitDemo"], A - 4 * 3600)
        later = demo.World(anchor=A, page_build="b", now=A + 9999).state()
        self.assertEqual(later["visitDemo"], A - 4 * 3600)

    def test_r5_pass_and_fail_end_after_visit(self):
        """[R5] at least one passed and one failed finished run end in (visitDemo, now]."""
        since, now = self.st["visitDemo"], self.w.now()
        ok = bad = 0
        for u in _runs(self.st).values():
            if not (u.get("end") and since < u["end"] <= now):
                continue
            if any(g.get("o") == "fail" for g in u["stages"].values()):
                bad += 1
            else:
                ok += 1
        self.assertGreaterEqual(ok, 1)
        self.assertGreaterEqual(bad, 1)

    def test_r5_past_rid_differs_from_head(self):
        """[R5] the failed past entry has its own rid, never the head run's t0 (counted once)."""
        rows = [r for row in self.st["sessions"] for r in row.get("plrun") or () if r.get("past")]
        self.assertTrue(rows)
        for r in rows:
            for p in r["past"]:
                self.assertNotEqual(p["rid"], r["rid"])
                self.assertLess(p["t0"], r["t0"])

    def test_r5_every_run_has_rid(self):
        """[R5] every demo plrun row carries rid = t0 (pl_model shape), so the run picker can open a past run."""
        for row in self.st["sessions"]:
            for r in row.get("plrun") or ():
                self.assertEqual(r.get("rid"), r["t0"], r["name"])

    def test_r5_passed_run_stops_on_last_defined_stage(self):
        """[R5] ended passing runs in the window sit on the last stage of their demo pipeline definition."""
        since, now = self.st["visitDemo"], self.w.now()
        web = self.w.by["web"]["cwd"]
        code, b = demo.respond(self.w, "/api/pipelines", _Q("proj=" + web))
        self.assertEqual(code, 200)
        last = {p["name"]: p["stages"][-1]["title"] for p in b["pipelines"]}
        n = 0
        for row in self.st["sessions"]:
            for r in row.get("plrun") or ():
                if r["proj"] == web and r["end"] and since < r["end"] <= now:
                    self.assertEqual(r["cur"], last.get(r["name"]), r["name"])
                    n += 1
        self.assertGreaterEqual(n, 1)

    def test_r5_commit_after_pass_in_window(self):
        """[R5] a passed run in the window has a commit stamp after one of its done stages."""
        since, now = self.st["visitDemo"], self.w.now()
        hits = 0
        for u in _runs(self.st).values():
            st = list(u["stages"].values())
            if not (u.get("end") and since < u["end"] <= now) or any(g.get("o") == "fail" for g in st):
                continue
            done = [g["t1"] for g in st if g.get("o") == "done"]
            hits += sum(1 for g in st for c in g.get("cm", ()) if done and c > min(done) and since < c <= now)
        self.assertGreaterEqual(hits, 1)

    def test_r5_real_state_never_emits_visit_demo(self):
        """[R5] the real state builder has no visitDemo key (demo-only)."""
        with open(os.path.join(ROOT, "sidereus", "state.py"), encoding="utf-8") as f:
            self.assertNotIn("visitDemo", f.read())


if __name__ == "__main__":
    unittest.main()
