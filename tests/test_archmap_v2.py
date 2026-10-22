"""arch_verify map.json v2 (layers, groups, entry/store modules, read/write/serve/event edges) + arch_map.load pass-through."""
import copy
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus
from tests.test_archmap_verify import make_repo

AV = sidereus("arch_verify")
AM = sidereus("arch_map")
C1 = "a" * 40


def v1_map(repo, commit):
    return {"v": 1, "repo": repo, "commit": commit,
            "modules": [{"id": "app", "name": "App", "path": "app", "kind": "module"},
                        {"id": "lib", "name": "Lib", "path": "lib", "kind": "module", "role": "data"},
                        {"id": "pg", "name": "Postgres", "path": "", "kind": "external", "ext": "db"}],
            "edges": [{"from": "app", "to": "pg", "kind": "call", "label": "uses",
                       "evidence": [{"file": "app/main.py", "line": 6, "symbol": "conn"}]}]}


def v2_map(repo, commit):
    ev = lambda f, ln, s: [{"file": f, "line": ln, "symbol": s}]
    return {"v": 2, "repo": repo, "commit": commit,
            "groups": [{"id": "core", "name": "Core", "layer": "service"}, {"id": "io", "name": "I/O"}],
            "modules": [{"id": "http", "name": "HTTP", "path": "", "kind": "entry", "ext": "http", "layer": "entry", "group": "io"},
                        {"id": "app", "name": "App", "path": "app", "kind": "module", "layer": "service", "group": "core",
                         "role": "service", "summary": "Runs the job", "owns": ["pg"]},
                        {"id": "lib", "name": "Lib", "path": "lib", "kind": "module", "layer": "data", "group": "core",
                         "role": "data"},
                        {"id": "pg", "name": "Postgres", "path": "", "kind": "store", "ext": "db", "layer": "data", "group": "io"}],
            "edges": [{"from": "app", "to": "pg", "kind": "read", "label": "rows", "evidence": ev("app/main.py", 6, "conn")},
                      {"from": "lib", "to": "pg", "kind": "write", "label": "", "evidence": ev("lib/db.py", 1, "connect")},
                      {"from": "http", "to": "app", "kind": "serve", "label": "/run", "evidence": ev("app/main.py", 5, "run")},
                      {"from": "app", "to": "lib", "kind": "event", "label": "", "evidence": ev("app/main.py", 7, "helper")},
                      {"from": "app", "to": "lib", "kind": "call", "label": "", "evidence": ev("app/main.py", 2, "connect")}]}


class SchemaV2Test(unittest.TestCase):
    R = "/tmp/sidereus-v2-repo"  # nosec B108 -- path value in an in-memory map, never touched on disk

    def errs(self, m):
        return AV.schema_errors(m, None, None)

    def test_v1_unchanged(self):
        self.assertEqual(self.errs(v1_map(self.R, C1)), [])

    def test_v2_valid(self):
        self.assertEqual(self.errs(v2_map(self.R, C1)), [])

    def test_rejections(self):
        def bad(fn):
            m = v2_map(self.R, C1)
            fn(m)
            return self.errs(m)
        mods = lambda m: {d["id"]: d for d in m["modules"]}
        cases = {
            "missing layer": lambda m: mods(m)["lib"].pop("layer"),
            "unknown layer": lambda m: mods(m)["lib"].update(layer="db"),
            "group not in groups": lambda m: mods(m)["lib"].update(group="zzz"),
            "summary 121": lambda m: mods(m)["app"].update(summary="x" * 121),
            "summary newline": lambda m: mods(m)["app"].update(summary="a\nb"),
            "owns missing id": lambda m: mods(m)["app"].update(owns=["nope"]),
            "owns non-store": lambda m: mods(m)["app"].update(owns=["lib"]),
            "read to non-store": lambda m: m["edges"][0].update(to="lib"),
            "serve from non-entry": lambda m: m["edges"][2].update(**{"from": "lib"}),
            "entry without ext": lambda m: mods(m)["http"].pop("ext"),
            "store wrong layer": lambda m: mods(m)["pg"].update(layer="infra"),
            "role/layer mismatch": lambda m: mods(m)["lib"].update(role="view"),
            "groups missing": lambda m: m.pop("groups"),
            "v=3": lambda m: m.update(v=3),
        }
        for name, fn in cases.items():
            with self.subTest(name):
                self.assertTrue(bad(fn))

    def test_v1_refuses_v2_features(self):
        m = v1_map(self.R, C1)
        m["edges"][0]["kind"] = "read"
        self.assertTrue(self.errs(m))
        m = v1_map(self.R, C1)
        m["groups"] = [{"id": "g", "name": "G"}]
        self.assertTrue(self.errs(m))
        m = v1_map(self.R, C1)
        m["modules"][0]["layer"] = "service"
        self.assertTrue(self.errs(m))
        m = v1_map(self.R, C1)
        del m["v"]
        self.assertTrue(self.errs(m))

    def test_event_estimated(self):
        self.assertEqual(AV.est_of({"kind": "event", "evidence": []}), 1)
        self.assertEqual(AV.est_of({"kind": "read", "evidence": []}), 0)


class VerifyV2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sidereus-archv2-")
        cls.repo, cls.commit = make_repo(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_all_kinds_pass(self):
        m = v2_map(self.repo, self.commit)
        self.assertEqual(AV.schema_errors(m, self.repo, self.commit), [])
        v = AV.verify_map(self.repo, self.commit, m)
        self.assertEqual([e["ok"] for e in v["edges"]], [True] * 5, v["edges"])

    def test_read_evidence_must_be_in_from(self):
        m = v2_map(self.repo, self.commit)
        m["edges"][0]["evidence"] = [{"file": "lib/db.py", "line": 1, "symbol": "connect"}]   # lib file, from = app
        self.assertEqual(AV.verify_map(self.repo, self.commit, m)["edges"][0]["why"], "owner")

    def test_serve_evidence_in_to(self):
        m = v2_map(self.repo, self.commit)
        m["edges"][2]["evidence"] = [{"file": "lib/db.py", "line": 1, "symbol": "connect"}]   # to = app
        self.assertEqual(AV.verify_map(self.repo, self.commit, m)["edges"][2]["why"], "owner")


class LoadV2Test(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-archv2load-"))
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        self.store = os.path.join(self.tmp, "store")
        roots = lambda p: os.path.realpath(p) if p and os.path.realpath(p) == self.repo else ""
        self.p = [mock.patch.object(AM, "ARCH_DIR", self.store), mock.patch.object(AM, "_struct_src_root", roots),
                  mock.patch.object(AM, "head_of", lambda r: C1), mock.patch.object(AM, "behind_of", lambda r, c: 0)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, m):
        d = os.path.join(self.store, AV.repo_key(self.repo), C1)
        os.makedirs(d, exist_ok=True)
        v = {"commit": C1, "total": len(m["edges"]), "passed": 1, "rate": 1.0,
             "edges": [{"i": i, "ok": True, "why": None} for i in range(len(m["edges"]))]}
        for name, data in (("map.json", m), ("verify.json", v)):
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                json.dump(data, f)

    def test_v1_loads_without_layer(self):
        self.put(v1_map(self.repo, C1))
        out = AM.load(self.repo)
        self.assertFalse(out.get("bad"))
        self.assertEqual((out["v"], out["groups"]), (1, []))
        self.assertNotIn("layer", out["modules"][0])

    def test_v2_carries_fields(self):
        m = v2_map(self.repo, C1)
        self.put(copy.deepcopy(m))
        out = AM.load(self.repo)
        self.assertFalse(out.get("bad"))
        self.assertEqual(out["v"], 2)
        self.assertEqual(out["groups"], m["groups"])
        app = [x for x in out["modules"] if x["id"] == "app"][0]
        self.assertEqual((app["layer"], app["group"], app["summary"], app["owns"]), ("service", "core", "Runs the job", ["pg"]))
        self.assertEqual([x["kind"] for x in out["modules"]], ["entry", "module", "module", "store"])
        self.assertEqual([e["est"] for e in out["edges"]], [0, 0, 0, 1, 0])


if __name__ == "__main__":
    unittest.main()
