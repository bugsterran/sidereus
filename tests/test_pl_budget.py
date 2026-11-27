"""Pipeline token budget: `budget` key (pipeline_schema), «of budget» counts (pl_outcome.run_cost/counts), kept by both
save paths (pipeline.save). Temp dirs only; OC_EVAL_DIR, _git, _now, EV_FILE, _proj_ok, _bak_dir patched."""
import json
import os
import shutil
import tempfile
import types
import unittest

from tests._load import load, sidereus

load()
SC = sidereus("pipeline_schema")
OC = sidereus("pl_outcome")
EV = sidereus("harness_evidence")
PL = sidereus("pipeline")
D = 86400
NOW = 1000000000.0
PIPE = {"v": 1, "name": "flow", "title": "Flow", "budget": {"tok": 300000}, "defaults": {"model": "inherit", "retry": 0},
        "stages": [{"title": "build", "agent": "general-purpose", "task": "build it"},
                   {"title": "check", "agent": "general-purpose", "task": "check it"}]}


def st(tok, s="done"):
    return {"s": s, "sec": 1, "n": 1, "tok": tok}


def patch(tc, mod, k, v):
    old = getattr(mod, k)
    setattr(mod, k, v)
    tc.addCleanup(setattr, mod, k, old)


class Schema(unittest.TestCase):
    def test_r1_valid_and_missing(self):
        self.assertEqual(SC.validate(PIPE, "flow"), [])
        self.assertEqual(SC.budget_tok(PIPE), 300000)
        P = {k: v for k, v in PIPE.items() if k != "budget"}
        self.assertEqual(SC.validate(P, "flow"), [])
        self.assertIsNone(SC.budget_tok(P))
        self.assertIsNone(SC.budget_tok(None))

    def test_r1_invalid_names_budget(self):
        for b in ({"tok": "x"}, {"tok": 0}, {"tok": -5}, {"tok": True}, {"tok": 1.5}, {}, {"tok": 5, "usd": 1}, 7, "300000",
                  None, [300000]):
            P = dict(PIPE, budget=b)
            errs = SC.validate(P, "flow")
            self.assertEqual(len(errs), 1, b)
            self.assertIn("budget", errs[0], b)
            self.assertIsNone(SC.budget_tok(P), b)

    def test_r1_over_cap_names_the_range(self):
        P = dict(PIPE, budget={"tok": 10 ** 13})
        self.assertEqual(SC.validate(P, "flow"), ["budget: {tok: integer 1..10^12}"])
        self.assertEqual(SC.BUDGET_TOK_MAX, 10 ** 12)   # message quotes this cap
        self.assertEqual(SC.budget_tok(dict(PIPE, budget={"tok": 10 ** 12})), 10 ** 12)


class Save(unittest.TestCase):
    """R1: Sidereus rewrites (stage edit = _apply, canvas = _replace) keep the budget key byte-for-byte in place."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pl-bud-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.proj = os.path.join(self.tmp, "proj")
        d = os.path.join(self.proj, ".claude", "pipelines")
        os.makedirs(d)
        self.path = os.path.join(d, "flow.json")
        # newline="": text mode on Windows writes CRLF, and save() hashes the file bytes (base would never match)
        with open(self.path, "w", encoding="utf-8", newline="") as f:
            f.write(SC.dump(PIPE))
        patch(self, PL, "_proj_ok", lambda p: p == self.proj)
        patch(self, PL, "_bak_dir", lambda: os.path.join(self.tmp, "bak"))
        patch(self, PL, "_strftime", lambda fmt: "20260101-000000")

    def save(self, **req):
        with open(self.path, encoding="utf-8", newline="") as f:
            raw = f.read()
        code, b = PL.save(dict(req, proj=self.proj, name="flow", base=PL._sha(raw), dry=False))
        self.assertEqual(code, 200, b)
        with open(self.path, encoding="utf-8", newline="") as f:
            return f.read()

    def test_r1_stage_edit_keeps_budget(self):
        text = self.save(stages={"build": {"model": "opus", "title": "make"}})
        P = json.loads(text)
        self.assertEqual(P["budget"], {"tok": 300000})
        self.assertEqual(list(P), list(PIPE))
        self.assertIn('  "budget": { "tok": 300000 },\n', text)

    def test_r1_canvas_save_keeps_budget(self):
        rows = [dict(s) for s in reversed(PIPE["stages"])]
        P = json.loads(self.save(stages=rows, defaults={"retry": 1}))
        self.assertEqual(P["budget"], {"tok": 300000})
        self.assertEqual([s["title"] for s in P["stages"]], ["check", "build"])


class Cost(unittest.TestCase):
    ROWS = [{"t0": 0, "end": 10, "ss": {"a": st(200), "b": st(150)}},     # 350 > 300: over
            {"t0": 10, "end": 20, "ss": {"a": st(300)}},                  # == budget: not over (strict >)
            {"t0": 20, "end": 30, "ss": {"a": st(None), "b": st(None)}},  # all unknown: left out
            {"t0": 30, "end": 40, "ss": {"a": st(320), "b": st(None)}}]   # partial: known 320 is a lower bound, over

    def test_r2_r4_bud_fields(self):
        c = OC.run_cost(self.ROWS, 300)
        self.assertEqual(c["bud"], {"tok": 300, "over": 2, "m": 3})
        self.assertEqual(c["mn"], 3)
        self.assertEqual(c["last"]["tok"], 320)

    def test_r4_all_unknown_never_over(self):
        self.assertEqual(OC.run_cost(self.ROWS[2:3], 1)["bud"], {"tok": 1, "over": 0, "m": 0})

    def test_r3_no_budget_unchanged(self):
        want = OC.run_cost(self.ROWS)
        self.assertNotIn("bud", want)
        for tb in (None, 0, -1, True, 1.5, "300"):
            self.assertEqual(OC.run_cost(self.ROWS, tb), want, tb)

    def test_r2_counts_keeps_bud(self):
        o = {"eff": {"a": {"n": 4, "sec": 1, "tok": 300, "tn": 3}}, "cost": OC.run_cost(self.ROWS, 300)}
        self.assertEqual(OC.counts(o)["cost"]["bud"], {"tok": 300, "over": 2, "m": 3})
        o["cost"]["bud"] = {"tok": 300, "over": 9, "m": 3, "x": "body"}   # over clamped to m, unknown keys dropped
        self.assertEqual(OC.counts(o)["cost"]["bud"], {"tok": 300, "over": 3, "m": 3})

    def test_r3_counts_no_bud_without_or_invalid(self):
        o = {"eff": {"a": {"n": 4, "sec": 1, "tok": 300, "tn": 3}}, "cost": OC.run_cost(self.ROWS)}
        self.assertNotIn("bud", OC.counts(o)["cost"])
        for bd in ({"tok": 0, "over": 1, "m": 1}, {"tok": True}, {"tok": "300"}, "junk", None, {"over": 1}):
            o["cost"]["bud"] = bd
            self.assertNotIn("bud", OC.counts(o)["cost"], bd)

    def test_demo_bud_survives_counts(self):
        from sidereus import demo_tools as d
        oc = d.DEMO_EVAL["outcome"]
        self.assertEqual(OC.counts(oc)["cost"]["bud"], oc["cost"]["bud"])
        self.assertGreater(oc["cost"]["last"]["tok"], oc["cost"]["bud"]["tok"])   # demo shows «Over budget»


class Outcome(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pl-bud-oc-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(self.proj)
        patch(self, OC, "OC_EVAL_DIR", os.path.join(self.tmp, "eval"))
        patch(self, OC, "_git", lambda repo, args: (0, "f" * 40 + "\n") if args[0] == "rev-parse" else (0, ""))
        patch(self, OC, "_now", lambda: NOW)
        patch(self, EV, "EV_FILE", os.path.join(self.tmp, "evidence.jsonl"))
        OC._OC_MEMO.clear()
        self.addCleanup(OC._OC_MEMO.clear)
        d = os.path.join(self.tmp, "eval", OC.repo_key(self.proj))
        os.makedirs(d)
        with open(os.path.join(d, "runs.jsonl"), "w", encoding="utf-8") as f:
            for k, tok in enumerate((500, 200)):
                f.write(json.dumps({"name": "flow", "t0": NOW - (k + 1) * D - 60, "end": NOW - (k + 1) * D,
                                    "ss": {"build": st(tok)}}) + "\n")

    def test_r2_memo_follows_budget(self):
        # ⚠HEAD, ledger and evidence unchanged: only the budget differs, so a memo keyed without it would return 300's bud
        a = OC.outcome(self.proj, "flow", [], tok_budget=300)
        b = OC.outcome(self.proj, "flow", [], tok_budget=100)
        c = OC.outcome(self.proj, "flow", [])
        self.assertEqual(a["cost"]["bud"], {"tok": 300, "over": 1, "m": 2})
        self.assertEqual(b["cost"]["bud"], {"tok": 100, "over": 2, "m": 2})
        self.assertNotIn("bud", c["cost"])
        self.assertIs(OC.outcome(self.proj, "flow", [], tok_budget=300), a)   # memo still hits for the same budget


class View(unittest.TestCase):
    """R2/R3 through GET /api/pipelines/eval: the file's budget reaches outcome(); no budget = no bud, call unchanged."""

    def setUp(self):
        self.v = sidereus("pl_eval_view")
        self.proj = tempfile.mkdtemp(prefix="pl-bud-v-")
        self.addCleanup(shutil.rmtree, self.proj, ignore_errors=True)
        os.makedirs(os.path.join(self.proj, ".claude", "pipelines"))
        pp, sc = sidereus("pipeline_projects"), sidereus("pl_scorecard")
        patch(self, pp, "_proj_ok", lambda p: p == self.proj)
        patch(self, sc, "scorecard", lambda p, head: None)
        patch(self, self.v, "_head", lambda p: "a" * 40)
        patch(self, self.v, "_pe", lambda: None)
        patch(self, self.v, "fix_pipes", lambda p: [])
        self.kw = []
        rows = Cost.ROWS

        def outcome(p, name, review, now, fix=(), **kw):
            self.kw.append(kw)
            return {"proc": {"runs": 4, "jump": 0}, "lb": {}, "result": {}, "eff": {"a": {"n": 4, "sec": 1, "tok": 1, "tn": 3}},
                    "cost": OC.run_cost(rows, kw.get("tok_budget"))}
        fake = types.SimpleNamespace(counts=OC.counts, latest_report=lambda p, n: None, outcome=outcome)
        patch(self, self.v, "_oc", lambda: fake)

    def write(self, P):
        with open(os.path.join(self.proj, ".claude", "pipelines", "flow.json"), "w", encoding="utf-8") as f:
            f.write(SC.dump(P))

    def test_r2_budget_reaches_body(self):
        self.write(PIPE)
        code, b = self.v.pl_eval(self.proj, "flow")
        self.assertEqual(code, 200)
        self.assertEqual(self.kw, [{"tok_budget": 300000}])
        self.assertEqual(b["outcome"]["cost"]["bud"], {"tok": 300000, "over": 0, "m": 3})

    def test_r3_no_budget_no_bud(self):
        self.write({k: v for k, v in PIPE.items() if k != "budget"})
        code, b = self.v.pl_eval(self.proj, "flow")
        self.assertEqual(code, 200)
        self.assertEqual(self.kw, [{}])
        self.assertNotIn("bud", b["outcome"]["cost"])
        self.assertNotIn("bud", json.dumps(b))


if __name__ == "__main__":
    unittest.main()
