"""arch_schema: non-string ids/kinds are schema errors (no TypeError), read/write/serve endpoint kinds, load() survives."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus
from tests.test_archmap_v2 import C1, v1_map, v2_map

AS = sidereus("arch_schema")
AV = sidereus("arch_verify")
AM = sidereus("arch_map")
R = "/tmp/sidereus-schema-repo"  # nosec B108 -- path value in an in-memory map, never touched on disk


def mods(m):
    return {d["id"]: d for d in m["modules"]}


class NonStringTest(unittest.TestCase):
    def test_reexported(self):
        self.assertIs(AV.schema_errors, AS.schema_errors)

    def test_list_values_are_errors(self):
        cases = {
            "modules[1].kind must be a string": lambda m: m["modules"][1].update(kind=["module"]),
            "modules[1].id must be a string": lambda m: m["modules"][1].update(id=["app"]),
            "edges[0].from must be a string": lambda m: m["edges"][0].update(**{"from": ["app"]}),
            "edges[0].to must be a string": lambda m: m["edges"][0].update(to=["pg"]),
            "edges[0].kind must be a string": lambda m: m["edges"][0].update(kind=["read"]),
        }
        for want, fn in cases.items():
            for mk in (v2_map, v1_map):
                with self.subTest(want, v=mk.__name__):
                    m = mk(R, C1)
                    fn(m)
                    self.assertIn(want, AS.schema_errors(m))


class EndpointKindTest(unittest.TestCase):
    def test_read_from_entry(self):
        m = v2_map(R, C1)
        m["edges"][0]["from"] = "http"
        self.assertIn("edges[0]: read/write must start at a kind:module", AS.schema_errors(m))

    def test_write_from_store(self):
        m = v2_map(R, C1)
        m["edges"][1]["from"] = "pg"
        self.assertIn("edges[1]: read/write must start at a kind:module", AS.schema_errors(m))

    def test_serve_to_store(self):
        m = v2_map(R, C1)
        m["edges"][2]["to"] = "pg"
        self.assertIn("edges[2]: serve must end at a kind:module", AS.schema_errors(m))

    def test_valid_map_still_clean(self):
        self.assertEqual(AS.schema_errors(v2_map(R, C1)), [])


class LoadSurvivesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-archschema-"))
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

    def test_list_fields_load_bad(self):
        m = v2_map(self.repo, C1)
        mods(m)["app"]["kind"] = ["module"]
        m["edges"][0]["from"] = ["app"]
        d = os.path.join(self.store, AV.repo_key(self.repo), C1)
        os.makedirs(d)
        v = {"commit": C1, "total": 5, "passed": 5, "rate": 1.0, "edges": [{"i": i, "ok": True, "why": None} for i in range(5)]}
        for name, data in (("map.json", m), ("verify.json", v)):
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                json.dump(data, f)
        self.assertTrue(AM.load(self.repo).get("bad"))


if __name__ == "__main__":
    unittest.main()
