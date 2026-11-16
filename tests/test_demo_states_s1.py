"""Demo World: attention «loop» / «toolfail» rows carry a tool name (R1) and the invoice run waits on a command (R2).

The demo writes attention rows as literals; these tests rebuild them with the real ranker (attention._row_sigs,
attention._toolfail_sigs) from the demo session rows so the two never drift. Pinned anchor, no live files.
"""
import unittest

from tests._load import sidereus

demo = sidereus("demo")
att = sidereus("attention")

A = 1_790_000_000


class _Base(unittest.TestCase):
    def setUp(self):
        self.w = demo.World(anchor=A, page_build="b", now=A)
        self.st = self.w.state()
        self.at = self.st["attention"]["at"]

    def row(self, k):
        sid = self.w.by[k]["sid"]
        return next(r for r in self.st["sessions"] if r.get("sid") == sid)

    def att_row(self, k):
        sid = self.w.by[k]["sid"]
        return next(r for r in self.st["attention"]["rows"] if r["sid"] == sid)


class R1LoopAndToolfail(_Base):
    def test_r1_inv_sigs_match_real_row_sigs(self):
        """[R1] inv row signals = what the real ranker reads off the demo session row (loop + ctx85, no done)."""
        real = att._row_sigs(self.row("inv"), self.at)
        mine = self.att_row("inv")["sigs"]
        self.assertEqual({s["k"] for s in mine}, {s["k"] for s in real})
        self.assertEqual({s["k"] for s in mine}, {"loop", "ctx85"})
        byk = {s["k"]: s for s in real}
        for s in mine:
            self.assertEqual(s["why"], att._why(s["k"], s["v"]), s["k"])
            self.assertEqual((s["v"], s["pts"], s["since"]), (byk[s["k"]]["v"], byk[s["k"]]["pts"], byk[s["k"]]["since"]))

    def test_r1_inv_score_and_order_follow_rank(self):
        """[R1] score = top pts + 5 per extra signal; signals ordered by pts like attention._rank."""
        r = self.att_row("inv")
        self.assertEqual(r["score"], max(s["pts"] for s in r["sigs"]) + 5 * (len(r["sigs"]) - 1))
        self.assertEqual([s["k"] for s in r["sigs"]], ["loop", "ctx85"])

    def test_r1_search_toolfail_matches_real_builder(self):
        """[R1] search row toolfail = attention._toolfail_sigs fed the same failure index."""
        mine = self.att_row("search")["sigs"]
        self.assertEqual([s["k"] for s in mine], ["toolfail"])
        s = mine[0]
        self.assertEqual(s["why"], att._why("toolfail", s["v"]))
        sess = [r for r in self.st["sessions"] if isinstance(r, dict)]
        cwd = self.w.by["search"]["cwd"]
        old = att._toolfail_idx
        att._toolfail_idx = lambda now: {cwd: [(s["v"]["n"], s["v"]["tool"], s["since"])]}
        self.addCleanup(setattr, att, "_toolfail_idx", old)
        extra = {}
        att._toolfail_sigs(extra, att._owner_of(sess), self.at)
        own = att._owner_of(sess)(cwd)
        self.assertEqual(own["sid"], self.w.by["search"]["sid"])
        (real,) = extra[id(own)]
        self.assertEqual({k: real[k] for k in ("k", "why", "pts", "since", "v")}, {k: s[k] for k in ("k", "why", "pts", "since", "v")})

    def test_r1_tool_names_present(self):
        """[R1] loop / toolfail carry a non-empty tool name, so no «tool» placeholder is drawn in either language."""
        sigs = [s for r in self.st["attention"]["rows"] for s in r["sigs"] if s["k"] in ("loop", "toolfail")]
        self.assertEqual(sorted(s["k"] for s in sigs), ["loop", "toolfail"])
        for s in sigs:
            self.assertTrue(isinstance(s["v"]["tool"], str) and s["v"]["tool"], s)
            self.assertTrue(isinstance(s["v"]["n"], int) and s["v"]["n"] > 0, s)
            self.assertEqual(set(s["v"]), {"n", "tool"})   # metadata only: count + tool name

    def test_r1_rows_sorted_by_score(self):
        rows = self.st["attention"]["rows"]
        self.assertEqual([r["score"] for r in rows], sorted((r["score"] for r in rows), reverse=True))


class R2InvoiceRunWaits(_Base):
    def test_r2_inv_open_run_between_stages(self):
        """[R2] one unended run with no stage «run»: the Timeline names what the session waits on, not «Aborted»."""
        r = self.row("inv")
        (pl,) = r["plrun"]
        self.assertEqual(pl["end"], 0)
        self.assertEqual(pl["name"], "invoice-change")
        self.assertFalse(any(s["o"] == "run" for s in pl["stages"].values()))
        self.assertEqual(pl["cur"], "구현")
        self.assertEqual(pl["t1"], max(s["t1"] for s in pl["stages"].values()))
        self.assertEqual(pl["proj"], self.w.by["bill"]["cwd"])
        self.assertEqual(set(pl), {"name", "proj", "sid", "cur", "end", "t0", "t1", "stages"})
        # waitOnLabel (20-session-state.js): state wait + no sub + bgs -> «Command waiting on work»
        self.assertEqual((r["state"], r["sub"]), ("wait", []))
        self.assertTrue(r["bgs"] and all(set(b) == {"lab", "min"} for b in r["bgs"]))

    def test_r2_command_stays_tied_to_run(self):
        """[R2] the open command's start stays within 30 min of the run's last touch at any later now (74c tlPlWaitTied)."""
        for later in (0, 3600, 6 * 3600):
            w = demo.World(anchor=A, page_build="b", now=A + later)
            r = next(x for x in w.state()["sessions"] if x.get("sid") == w.by["inv"]["sid"])
            t1 = r["plrun"][0]["t1"]
            self.assertTrue(any(abs(A + later - b["min"] * 60 - t1) <= 1800 for b in r["bgs"]), later)
        self.assertEqual(self.row("inv")["bgs"][0]["min"], 16)

    def test_r2_web_runs_unchanged(self):
        """[R2] the invoice run uses its own rng: web run ids and every other row's runs stay as they were."""
        web = self.row("web")["plrun"]
        self.assertEqual([r["name"] for r in web], ["change-flow", "hotfix", "release-check"])
        others = [r for r in self.st["sessions"] if r.get("plrun") and r.get("sid") not in (self.w.by["web"]["sid"], self.w.by["inv"]["sid"])]
        self.assertEqual(others, [])
        w2 = demo.World(anchor=A, page_build="b", now=A)
        self.assertEqual(w2.pl_runs("web"), self.w.pl_runs("web"))


if __name__ == "__main__":
    unittest.main()
