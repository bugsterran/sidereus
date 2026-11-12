"""arch_brief v2 gate (R1-R4): containment boxes (screens / 3-7 components / 1-4 externals with uses), labelled arrows on
verified edges, 2-4 principles with file:line at the commit; v1 briefs and v1 maps refused.
Temp store (ARCH_DIR patched); the commit tree and file reads are patched on arch_verify (_tree, _show)."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

AV = sidereus("arch_verify")
AB = sidereus("arch_brief")
B2 = sidereus("arch_brief_v2")
COMMIT = "a" * 40
TREE = {"app/main.py", "app/store.py"}


def ev(file="app/main.py", line=1, symbol="f"):
    return {"file": file, "line": line, "symbol": symbol}


def mod(i, kind, layer, ext=None):
    d = {"id": i, "name": i.title(), "path": "" if kind != "module" else i, "kind": kind, "layer": layer, "group": "g"}
    if ext:
        d["ext"] = ext
    return d


def edge(f, t, kind="call"):
    return {"from": f, "to": t, "kind": kind, "label": "", "evidence": [ev()]}


def show(_repo, _commit, rel):
    return ["line"] * 10 if rel in TREE else None


class Base(unittest.TestCase):
    def setUp(self):
        self.repo = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-brief2-"))
        self.store = tempfile.mkdtemp(prefix="sidereus-brief2-store-")
        self.ps = [mock.patch.object(AV, "ARCH_DIR", self.store), mock.patch.object(AV, "_tree", return_value=set(TREE)),
                   mock.patch.object(AV, "_show", side_effect=show)]
        for p in self.ps:
            p.start()
        self.d = AV.store_dir(self.repo, COMMIT)
        os.makedirs(self.d)

    def tearDown(self):
        for p in self.ps:
            p.stop()
        shutil.rmtree(self.store, ignore_errors=True)
        shutil.rmtree(self.repo, ignore_errors=True)

    def map2(self):
        return {"v": 2, "repo": self.repo, "commit": COMMIT, "groups": [{"id": "g", "name": "G"}],
                "modules": [mod("web_entry", "entry", "entry", "http"), mod("ui", "module", "ui"), mod("api", "module", "api"),
                            mod("svc", "module", "service"), mod("jobs", "module", "service"),
                            mod("pkg_a", "module", "domain"), mod("pkg_b", "module", "domain"),
                            mod("db", "store", "data", "db"), mod("llm", "external", "infra", "api")],
                "edges": [edge("ui", "api"), edge("api", "svc"), edge("svc", "db", "write"), edge("svc", "llm"),
                          edge("jobs", "svc"), edge("pkg_a", "db", "write"), edge("api", "pkg_a")]}

    def verdict(self):
        return {"commit": COMMIT, "edges": [{"i": i, "ok": i != 4, "why": None} for i in range(7)]}

    def brief(self):
        return {"v": 2, "repo": self.repo, "commit": COMMIT, "title": "App", "what": "Answers questions for staff",
                "actors": [{"id": "user", "name": "User"}],
                "screens": [{"id": "web", "name": "Web", "note": "pages", "role": "shows answers", "modules": ["ui"]}],
                "system": {"name": "Api", "components": [
                    {"id": "api", "name": "Api", "note": "routes", "role": "takes requests", "modules": ["api", "web_entry"]},
                    {"id": "svc", "name": "Service", "note": "logic", "role": "runs work", "modules": ["svc", "jobs"]},
                    {"id": "dom", "name": "Domain", "note": "packages", "role": "domain rules",
                     "pkgs": [{"name": "Orders", "modules": ["pkg_a"]}, {"name": "Billing", "note": "bills", "modules": ["pkg_b"]}]}],
                    "principles": [{"text": "one store", "evidence": {"file": "app/main.py", "line": 3}},
                                   {"text": "calls go through Api", "evidence": {"file": "app/store.py", "line": 10}}]},
                "externals": [{"id": "store", "name": "Store", "role": "keeps rows", "uses": [{"name": "Rows"}], "modules": ["db"]},
                              {"id": "llm", "name": "Llm", "role": "answers", "uses": [{"name": "Chat"}, {"name": "Embed"}],
                               "modules": ["llm"]}],
                "arrows": [{"from": "web", "to": "api", "label": "HTTP calls", "edges": [0]},
                           {"from": "api", "to": "svc", "label": "jobs", "edges": [1]},
                           {"from": "svc", "to": "store", "label": "rows", "use": 1, "edges": [2]},
                           {"from": "svc", "to": "llm", "label": "prompts", "use": 2, "edges": [3]},
                           {"from": "api", "to": "dom", "label": "orders", "edges": [6]}]}

    def put(self, name, doc):
        with open(os.path.join(self.d, name), "w", encoding="utf-8") as f:
            json.dump(doc, f)

    def gate(self, b, m=None):
        self.put("map.json", m or self.map2())
        self.put("verify.json", self.verdict())
        self.put(AV.BRIEF_JSON, b)
        return AB.run(self.repo, COMMIT)

    def fails(self, b, needle, **kw):
        rc, line = self.gate(b, **kw)
        self.assertEqual(rc, 1, line)
        self.assertIn(needle, line)
        self.assertFalse(os.path.exists(os.path.join(self.d, AV.BRIEF_HTML)))
        return line


class GateV2Test(Base):
    def test_r1_r4_ok_fixture_passes(self):
        self.assertEqual(AV.schema_errors(self.map2(), self.repo, COMMIT), [])
        rc, line = self.gate(self.brief())
        self.assertEqual(rc, 0, line)
        self.assertIn("ok · v2 · 3 components · 2 externals · 5 arrows · 2 principles · uncovered modules 0", line)
        with open(os.path.join(self.d, AV.BRIEF_HTML), "rb") as f:
            sha = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(AV.read_json(os.path.join(self.d, AV.BRIEF_OK)), {"v": 1, "sha256": sha, "commit": COMMIT})

    def test_r1_what_required(self):
        b = self.brief()
        del b["what"]
        self.fails(b, "what: 1..120 chars")

    # R2: containment
    def test_r2_two_components(self):
        b = self.brief()
        b["system"]["components"] = b["system"]["components"][:2]
        self.fails(b, "components: 3..7 (got 2)")

    def test_r2_eight_components(self):
        b = self.brief()
        b["system"]["components"] += [{"id": "c%d" % k, "name": "C", "note": "n", "role": "r", "modules": ["svc"]} for k in range(5)]
        self.fails(b, "components: 3..7 (got 8)")

    def test_r2_two_pkgs_components(self):
        b = self.brief()
        g = dict(b["system"]["components"][2], id="dom2")
        b["system"]["components"].append(g)
        self.fails(b, "components: at most one with pkgs")

    def test_r2_store_module_in_component(self):
        b = self.brief()
        b["system"]["components"][1]["modules"] = ["svc", "jobs", "db"]
        b["externals"][0]["modules"] = ["llm"]
        b["externals"] = b["externals"][:1]
        b["arrows"] = b["arrows"][:2]
        self.fails(b, "component svc: db is kind store")

    def test_r2_external_holds_plain_module(self):
        b = self.brief()
        b["externals"][1]["modules"] = ["llm", "ui"]
        self.fails(b, "external llm: ui is kind module")

    def test_r2_external_uses_count(self):
        for uses in ([], [{"name": "a"}, {"name": "b"}, {"name": "c"}, {"name": "d"}]):
            b = self.brief()
            b["externals"][0]["uses"] = uses
            self.fails(b, "external: {id")

    def test_r2_duplicate_id(self):
        b = self.brief()
        b["screens"][0]["id"] = "api"
        b["arrows"] = b["arrows"][1:]
        self.fails(b, "duplicate id api")

    # R3: labelled arrows on verified edges
    def test_r3_arrow_without_label(self):
        b = self.brief()
        del b["arrows"][0]["label"]
        self.fails(b, "label<=32 (required)")

    def test_r3_unverified_edge(self):
        b = self.brief()
        b["arrows"][1]["edges"] = [4]
        self.fails(b, "arrow api->svc: edge 4 is not verified")

    def test_r3_edge_not_joining(self):
        b = self.brief()
        b["arrows"][1]["edges"] = [3]
        self.fails(b, "arrow api->svc: edge 3 does not join these boxes")

    def test_r3_actor_endpoint(self):
        b = self.brief()
        b["arrows"][0]["from"] = "user"
        self.fails(b, "actor endpoint")

    def test_r3_bad_use(self):
        b = self.brief()
        b["arrows"][2]["use"] = 2
        self.fails(b, "use 2 needs an external target")
        b = self.brief()
        b["arrows"][1]["use"] = 1
        self.fails(b, "use 1 needs an external target")

    # R4: principles with file:line evidence
    def test_r4_principle_count(self):
        for n in (1, 5):
            b = self.brief()
            b["system"]["principles"] = [{"text": "p", "evidence": {"file": "app/main.py", "line": 1}}] * n
            self.fails(b, "principles: 2..4")

    def test_r4_principle_without_evidence(self):
        b = self.brief()
        del b["system"]["principles"][0]["evidence"]
        self.fails(b, "every principle cites file:line")

    def test_r4_file_missing_at_commit(self):
        b = self.brief()
        b["system"]["principles"][0]["evidence"]["file"] = "app/nope.py"
        self.fails(b, "principle 1: app/nope.py not in the commit")

    def test_r4_line_out_of_range(self):
        b = self.brief()
        b["system"]["principles"][1]["evidence"]["line"] = 11
        self.fails(b, "principle 2: app/store.py:11 outside 1..10")

    def test_r4_unreadable_tree_is_unknown_not_missing(self):
        with mock.patch.object(AV, "_tree", side_effect=subprocess.TimeoutExpired("git", 1)):
            line = self.fails(self.brief(), "principle 1: commit tree unreadable")
        self.assertNotIn("not in the commit", line)

    def test_v1_map_refused(self):
        m = self.map2()
        m["v"] = 1
        del m["groups"]
        m["modules"] = [{"id": "x", "name": "X", "path": "x", "kind": "module"}]
        m["edges"] = []
        self.fails(self.brief(), "v2 overview needs a v2 map", m=m)

    def test_v1_brief_refused(self):
        b1 = {"v": 1, "repo": self.repo, "commit": COMMIT, "title": "Old", "bands": [{"id": "x", "name": "X"}],
              "boxes": [{"id": "b", "name": "B", "band": "x", "modules": ["api"]}], "arrows": [], "route": {"na": "n/a"}}
        self.assertEqual(AB.shape_errors(b1, self.repo, COMMIT), [])
        self.fails(b1, "v1 brief.json: redraw as v2")
        self.assertFalse(os.path.exists(os.path.join(self.d, AV.BRIEF_OK)))

    def test_unknown_key_refused(self):
        b = self.brief()
        b["route"] = {"na": "none"}
        self.fails(b, "unknown keys")


class DispatchTest(Base):
    def test_v1_still_uses_old_check(self):
        m = {"modules": [{"id": "app"}], "edges": []}
        b1 = {"v": 1, "bands": [{"id": "x", "name": "X"}], "boxes": [{"id": "b", "name": "B", "band": "nope", "modules": ["app"]}],
              "arrows": [], "route": {"na": "n/a"}}
        with mock.patch.object(B2, "check", side_effect=AssertionError("v2 check called for v1")):
            errs, _unc = AB.check(b1, m, {"edges": []}, set(), lambda r: None)
        self.assertIn("box b: unknown band nope", errs)

    def test_shape_v2_dispatch(self):
        b = self.brief()
        self.assertEqual(AB.shape_errors(b, self.repo, COMMIT), [])
        b["bands"] = []
        self.assertTrue(any("unknown keys" in x for x in AB.shape_errors(b, self.repo, COMMIT)))


if __name__ == "__main__":
    unittest.main()
