"""arch_brief: --pre pointer, brief.json gate (ids, verified edges, evidence lines at the commit), brief.html on pass.
Temp git repo + temp store (ARCH_DIR patched on arch_verify)."""
import copy
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests._load import ROOT, sidereus

AV = sidereus("arch_verify")
AB = sidereus("arch_brief")
FIX = os.path.join(ROOT, "tests", "fixtures", "archmap_repo")
GENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid", GIT_AUTHOR_DATE="2000-01-01T00:00:00Z",
            GIT_COMMITTER_DATE="2000-01-01T00:00:00Z")


def _script():
    spec = importlib.util.spec_from_file_location("arch_brief_cli", os.path.join(ROOT, "scripts", "arch_brief.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CLI = _script()


def cli(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = CLI.main(list(argv))
    return rc, buf.getvalue().strip()


def ev(file, line, symbol):
    return {"file": file, "line": line, "symbol": symbol}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sidereus-brief-")
        repo = os.path.join(cls.tmp, "repo")
        shutil.copytree(FIX, repo)
        for a in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "fixture"]):
            subprocess.run(["git", "-C", repo] + a, check=True, env=GENV, capture_output=True)
        cls.repo = os.path.realpath(repo)
        cls.commit = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], check=True, env=GENV, capture_output=True,
                                    text=True, encoding="utf-8").stdout.strip()
        with open(os.path.join(repo, "app", "main.py"), encoding="utf-8") as f:
            cls.main_lines = len(f.read().splitlines())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="sidereus-brief-store-")
        self.p = mock.patch.object(AV, "ARCH_DIR", self.store)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        shutil.rmtree(self.store, ignore_errors=True)

    def put_map(self):
        m = {"v": 1, "repo": self.repo, "commit": self.commit,
             "modules": [{"id": "app", "name": "App", "path": "app", "kind": "module"},
                         {"id": "lib", "name": "Lib", "path": "lib", "kind": "module"},
                         {"id": "pg", "name": "Postgres", "path": "", "kind": "external", "ext": "db"}],
             "edges": [{"from": "app", "to": "lib", "kind": "call", "label": "uses", "evidence": [ev("app/main.py", 1, "lib")]},
                       {"from": "app", "to": "pg", "kind": "call", "label": "reads", "evidence": [ev("app/main.py", 1, "x")]},
                       {"from": "lib", "to": "pg", "kind": "call", "label": "reads", "evidence": [ev("lib/db.py", 1, "connect")]}]}
        self.assertEqual(AV.schema_errors(m, self.repo, self.commit), [])
        v = {"commit": self.commit, "total": 3, "passed": 2, "rate": 0.67,
             "edges": [{"i": 0, "ok": True, "why": None}, {"i": 1, "ok": False, "why": "nosym"}, {"i": 2, "ok": True, "why": None}]}
        d = AV.store_dir(self.repo, self.commit)
        os.makedirs(d, exist_ok=True)
        for name, doc in (("map.json", m), ("verify.json", v)):
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                json.dump(doc, f)
        return d

    def brief(self):
        return {"v": 1, "repo": self.repo, "commit": self.commit, "title": "Fixture <app>",
                "bands": [{"id": "front", "name": "Front"}, {"id": "back", "name": "Back"}],
                "boxes": [{"id": "web", "name": "Web", "band": "front", "modules": ["app"]},
                          {"id": "data", "name": "Data", "band": "back", "note": "storage", "modules": ["lib", "pg"]}],
                "arrows": [{"from": "web", "to": "data", "label": "calls", "edges": [0]}],
                "route": {"by": "request path", "rows": [{"when": "always", "goes": "data", "box": "data",
                                                          "evidence": {"file": "app/main.py", "line": 1}}]}}

    def gate(self, b):
        """v1 rules only (shape + check_v1): the gate itself refuses every v1 brief (R4)."""
        d = self.put_map()
        with open(os.path.join(d, AV.BRIEF_JSON), "w", encoding="utf-8") as f:
            json.dump(b, f)
        m, v = AV.read_json(os.path.join(d, "map.json")), AV.read_json(os.path.join(d, "verify.json"))
        errs, unc = AB.shape_errors(b, self.repo, self.commit), 0
        if not errs:
            errs, unc = AB.check_v1(self.repo, self.commit, b, m, v)
        return (1 if errs else 0), "; ".join(errs) or "uncovered modules %d" % unc, d


class PreTest(Base):
    def test_pre_without_map(self):
        rc, line = cli("--pre", "--repo", self.repo)
        self.assertEqual(rc, 1)
        self.assertIn("no arch-map result for", line)
        self.assertIn("run arch-map first", line)
        j = AV.read_json(os.path.join(self.store, AV.BRIEF_LAST))
        self.assertEqual((j["commit"], j["ok"]), (self.commit, False))
        self.assertFalse(os.path.exists(os.path.join(self.store, "_last.json")))   # arch-map's pointer untouched
        self.assertEqual(cli("--ready")[0], 1)
        self.assertEqual(cli("--last")[0], 1)

    def test_pre_with_map(self):
        d = self.put_map()
        rc, line = cli("--pre", "--repo", self.repo)
        self.assertEqual(rc, 0, line)
        self.assertIn(d, line)
        self.assertEqual(cli("--ready")[0], 0)

    def test_pre_rewrites_stale_ok(self):
        self.put_map()
        self.assertEqual(cli("--pre", "--repo", self.repo)[0], 0)
        os.remove(os.path.join(AV.store_dir(self.repo, self.commit), "verify.json"))
        self.assertEqual(cli("--pre", "--repo", self.repo)[0], 1)
        self.assertEqual(cli("--ready")[0], 1)

    def test_usage(self):
        self.assertEqual(cli("--bogus")[0], 2)


class GateTest(Base):
    def fails(self, b, needle):
        rc, line, d = self.gate(b)
        self.assertEqual(rc, 1, line)
        self.assertIn(needle, line)
        self.assertFalse(os.path.exists(os.path.join(d, AV.BRIEF_HTML)))

    def test_valid_v1_rules(self):
        rc, line, d = self.gate(self.brief())
        self.assertEqual(rc, 0, line)
        self.assertIn("uncovered modules 0", line)
        self.assertIn('data-box="web"', AB.render(self.brief()))

    def test_r4_run_refuses_valid_v1(self):
        # R4: a v1 brief skips the v2 rules, so the gate refuses it and writes neither html nor stamp
        _rc, _line, d = self.gate(self.brief())
        rc, line = AB.run(self.repo, self.commit)
        self.assertEqual(rc, 1, line)
        self.assertIn("v1 brief.json: redraw as v2", line)
        self.assertFalse(os.path.exists(os.path.join(d, AV.BRIEF_HTML)))
        self.assertFalse(os.path.exists(os.path.join(d, AV.BRIEF_OK)))

    def test_fail_removes_stale_ok(self):
        _rc, _line, d = self.gate(self.brief())
        with open(os.path.join(d, AV.BRIEF_OK), "w", encoding="utf-8") as f:
            f.write("{}")
        self.assertEqual(AB.run(self.repo, self.commit)[0], 1)
        self.assertFalse(os.path.exists(os.path.join(d, AV.BRIEF_OK)))
        os.remove(os.path.join(d, AV.BRIEF_JSON))   # unreadable brief.json fails the same way
        with open(os.path.join(d, AV.BRIEF_OK), "w", encoding="utf-8") as f:
            f.write("{}")
        self.assertEqual(AB.run(self.repo, self.commit)[0], 1)
        self.assertFalse(os.path.exists(os.path.join(d, AV.BRIEF_OK)))

    def test_agent_written_html_has_no_ok(self):
        d = self.put_map()
        with open(os.path.join(d, AV.BRIEF_HTML), "w", encoding="utf-8") as f:
            f.write("<p>hand made</p>")
        self.assertFalse(os.path.exists(os.path.join(d, AV.BRIEF_OK)))

    def test_self_arrow(self):
        b = self.brief()
        b["arrows"] = [{"from": "data", "to": "data", "edges": [2]}]
        self.fails(b, "arrow to its own box")

    def test_duplicate_band_id(self):
        b = self.brief()
        b["bands"].append({"id": "back", "name": "Back again"})
        self.fails(b, "duplicate band id back")

    def test_duplicate_box_id(self):
        b = self.brief()
        b["boxes"][1]["id"] = "web"
        self.fails(b, "duplicate box id web")

    def test_r4_v1_via_last_refused(self):
        self.put_map()
        with open(os.path.join(AV.store_dir(self.repo, self.commit), AV.BRIEF_JSON), "w", encoding="utf-8") as f:
            json.dump(self.brief(), f)
        self.assertEqual(cli("--pre", "--repo", self.repo)[0], 0)
        rc, line = cli("--last")
        self.assertEqual(rc, 1, line)   # R4: v1 is refused by the gate
        self.assertIn("redraw as v2", line)

    def test_uncovered_is_advisory(self):
        b = self.brief()
        b["boxes"][1]["modules"] = ["lib"]
        rc, line, _d = self.gate(b)
        self.assertEqual(rc, 0, line)
        self.assertIn("uncovered modules 1", line)

    def test_unknown_module(self):
        b = self.brief()
        b["boxes"][0]["modules"] = ["app", "ghost"]
        self.fails(b, "unknown module ghost")

    def test_unknown_band(self):
        b = self.brief()
        b["boxes"][0]["band"] = "nope"
        self.fails(b, "unknown band nope")

    def test_unknown_box_in_arrow(self):
        b = self.brief()
        b["arrows"][0]["to"] = "nope"
        self.fails(b, "unknown box")

    def test_module_in_two_boxes(self):
        b = self.brief()
        b["boxes"][1]["modules"] = ["lib", "app"]
        self.fails(b, "module app in two boxes")

    def test_too_many_boxes(self):
        b = self.brief()
        b["boxes"] = [{"id": "b%d" % k, "name": "B", "band": "front", "modules": ["app"] if k == 0 else ["lib"]}
                      for k in range(13)]
        self.fails(b, "too many boxes: 13 > 12")

    def test_arrow_unverified_edge(self):
        b = self.brief()
        b["arrows"][0]["edges"] = [1]
        self.fails(b, "edge 1 is not verified")

    def test_arrow_edge_not_joining_boxes(self):
        b = self.brief()
        b["arrows"] = [{"from": "data", "to": "web", "edges": [2]}]
        self.fails(b, "edge 2 does not join these boxes")

    def test_arrow_edge_out_of_range(self):
        b = self.brief()
        b["arrows"][0]["edges"] = [9]
        self.fails(b, "edge 9 does not exist")

    def test_arrow_without_edges(self):
        b = self.brief()
        b["arrows"][0]["edges"] = []
        self.fails(b, "arrow:")

    def test_evidence_unsafe_path(self):
        b = self.brief()
        b["route"]["rows"][0]["evidence"]["file"] = "../etc/passwd"
        self.fails(b, "unsafe evidence path")

    def test_evidence_file_missing(self):
        b = self.brief()
        b["route"]["rows"][0]["evidence"]["file"] = "app/nope.py"
        self.fails(b, "not in the commit")

    def test_evidence_strings_unchanged_via_helper(self):
        # v1 route rows and v2 principles share arch_brief_v2._ev_errors; the v1 wording stays byte-for-byte
        b = self.brief()
        m = {"modules": [{"id": "app"}, {"id": "lib"}, {"id": "pg"}], "edges": []}
        b["arrows"] = []
        cases = [("../x", 1, {"app/main.py"}, "route row 1: unsafe evidence path"),
                 ("app/main.py", 1, None, "route row 1: commit tree unreadable"),
                 ("app/nope.py", 1, {"app/main.py"}, "route row 1: app/nope.py not in the commit"),
                 ("app/gone.py", 1, {"app/gone.py"}, "route row 1: app/gone.py unreadable"),
                 ("app/main.py", 4, {"app/main.py"}, "route row 1: app/main.py:4 outside 1..3")]
        for f, ln, tree, want in cases:
            b["route"]["rows"][0]["evidence"] = {"file": f, "line": ln}
            errs, _u = AB.check(b, m, {"edges": []}, tree, lambda rel: ["a", "b", "c"] if rel == "app/main.py" else None)
            self.assertEqual(errs, [want])

    def test_evidence_line_range(self):
        for ln in (0, self.main_lines + 1):
            b = self.brief()
            b["route"]["rows"][0]["evidence"]["line"] = ln
            self.fails(b, "outside 1..%d" % self.main_lines)
        b = self.brief()
        b["route"]["rows"][0]["evidence"]["line"] = self.main_lines
        self.assertEqual(self.gate(b)[0], 0)

    def test_evidence_reads_commit_not_worktree(self):
        p = os.path.join(self.repo, "app", "ghost.py")
        with open(p, "w", encoding="utf-8") as f:
            f.write("x = 1\n")
        try:
            b = self.brief()
            b["route"]["rows"][0]["evidence"]["file"] = "app/ghost.py"
            self.fails(b, "not in the commit")
        finally:
            os.remove(p)

    def test_unreadable_tree_is_not_missing_file(self):
        with mock.patch.object(AV, "_tree", side_effect=subprocess.TimeoutExpired("git", 1)):
            self.fails(self.brief(), "commit tree unreadable")

    def test_route_na(self):
        b = self.brief()
        b["route"] = {"na": "No router: one entry point."}
        self.assertEqual(self.gate(b)[0], 0)

    def test_shape_errors(self):
        for mut in (lambda b: b.update(extra=1), lambda b: b.update(v=2), lambda b: b.update(commit="0" * 40),
                    lambda b: b.update(route={}), lambda b: b.update(bands=[]),
                    lambda b: b["boxes"][0].update(name="x" * 41)):
            b = copy.deepcopy(self.brief())
            mut(b)
            rc, line, _d = self.gate(b)
            self.assertEqual(rc, 1, line)

    def test_r2_band_with_one_same_named_box_fails(self):
        b = self.brief()
        b["bands"][0]["name"] = " web "   # strip + casefold match on the box «Web»
        rc, line, _d = self.gate(b)
        self.assertEqual(rc, 1, line)
        self.assertIn("band front", line)

    def test_r2_two_box_band_passes(self):
        b = self.brief()
        b["bands"][0]["name"] = "Web"
        b["boxes"][1]["band"] = "front"
        b["bands"] = b["bands"][:1]
        rc, line, _d = self.gate(b)
        self.assertEqual(rc, 0, line)

    def _labelled(self, n):
        b = self.brief()
        b["arrows"] = [{"from": "web", "to": "data", "label": "Auth " if k % 2 else "auth", "edges": [0]} for k in range(n)]
        return b

    def test_r3_four_same_labels_into_one_box_fail(self):
        rc, line, _d = self.gate(self._labelled(4))
        self.assertEqual(rc, 1, line)
        self.assertIn("box data: 4 arrows labelled «auth»", line)

    def test_r3_three_same_labels_pass(self):
        rc, line, _d = self.gate(self._labelled(3))
        self.assertEqual(rc, 0, line)

    def test_r3_band_note(self):
        b = self.brief()
        b["bands"][1]["note"] = "every area uses login, permissions, mail"
        rc, line, _d = self.gate(b)
        self.assertEqual(rc, 0, line)
        self.assertIn("every area uses login, permissions, mail", AB.render(b))
        b["bands"][1]["note"] = "x" * 81
        rc, line, _d = self.gate(b)
        self.assertEqual(rc, 1, line)
        self.assertIn("band:", line)

    def test_no_map_result(self):
        rc, line = AB.run(self.repo, self.commit)
        self.assertEqual(rc, 1)
        self.assertIn("run arch-map first", line)


class V1GoldenTest(unittest.TestCase):
    # ⚠Stored v1 briefs are sha256-stamped: the v2 overview must not move one byte of the v1 render.
    GOLDEN = "8f858d185a543329e3411a3a8cb6b8593e4ccde36b81a89596d918f6e498641b"

    def brief(self):
        return {"v": 1, "repo": "/r", "commit": "c" * 40, "title": "Golden <v1>", "heads": {"arch": "Arch", "route": "Order"},
                "bands": [{"id": "front", "name": "Front"}, {"id": "back", "name": "Back", "note": "shared services"}],
                "boxes": [{"id": "web", "name": "Web", "band": "front", "modules": ["app"]},
                          {"id": "api", "name": "API & jobs", "band": "front", "note": "routes", "modules": ["api"]},
                          {"id": "data", "name": "Data", "band": "back", "modules": ["lib", "pg"]}],
                "arrows": [{"from": "web", "to": "data", "label": "calls", "edges": [0]},
                           {"from": "api", "to": "data", "edges": [1, 2]}],
                "route": {"by": "path", "rows": [{"when": "/api/*", "goes": "API", "box": "api",
                                                  "evidence": {"file": "app/main.py", "line": 3}}]}}

    def test_v1_render_bytes_unchanged(self):
        import hashlib
        b = self.brief()
        for h in (AB.render(b), sidereus("arch_brief_html").render(b)):
            self.assertEqual(hashlib.sha256(h.encode("utf-8")).hexdigest(), self.GOLDEN)


class PipelineFileTest(unittest.TestCase):
    def test_pipeline_stages(self):
        with open(os.path.join(ROOT, ".claude", "pipelines", "arch-brief.json"), encoding="utf-8") as f:
            p = json.load(f)
        gates = [s.get("gate") for s in p["stages"]]
        self.assertEqual(gates, ["/usr/bin/python3 scripts/arch_brief.py --ready", None,
                                 "/usr/bin/python3 scripts/arch_brief.py --last"])
        self.assertEqual(p["stages"][2]["onFail"], {"goto": p["stages"][1]["title"], "max": 1})
        self.assertTrue(all(s.get("model") for s in p["stages"]))


if __name__ == "__main__":
    unittest.main()
