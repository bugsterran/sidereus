"""Tests for source <-> test pairing (sidereus/structure.py `_struct_pair_match` + `structure_pair`).

The matcher is pure (file list + reader in); the endpoint runs on a temp dir with the allow list patched.
"""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

S = sidereus("structure")


def _m(rel, files, bodies=None):
    bodies = bodies or {}
    t, out = S._struct_pair_match(rel, files, lambda f: bodies.get(f, ""))
    return t, [(r["file"], r["reason"]) for r in out]


class NameRules(unittest.TestCase):
    def test_python_test_prefix_and_suffix(self):
        fs = ["sidereus/retro.py", "tests/test_retro.py", "sidereus/retro_test.py", "tests/test_other.py"]
        t, got = _m("sidereus/retro.py", fs)
        self.assertFalse(t)
        self.assertEqual({f for f, _ in got}, {"tests/test_retro.py", "sidereus/retro_test.py"})
        self.assertEqual(got[0], ("sidereus/retro_test.py", "dir"))

    def test_python_reverse(self):
        t, got = _m("tests/test_retro.py", ["sidereus/retro.py", "tests/test_retro.py", "web/retro.js"])
        self.assertTrue(t)
        self.assertEqual(got, [("sidereus/retro.py", "name")])

    def test_java_mirror_beats_name(self):
        fs = ["src/main/java/a/b/Foo.java", "src/test/java/a/b/FooTest.java",
              "src/test/java/x/FooTests.java", "src/test/java/a/b/BarTest.java"]
        _t, got = _m("src/main/java/a/b/Foo.java", fs)
        self.assertEqual(got, [("src/test/java/a/b/FooTest.java", "mirror"), ("src/test/java/x/FooTests.java", "name")])
        _t, back = _m("src/test/java/a/b/FooTest.java", fs)
        self.assertEqual(back, [("src/main/java/a/b/Foo.java", "mirror")])

    def test_ts_spec_and_dunder_tests(self):
        fs = ["web/src/api/token.ts", "web/src/api/token.test.ts", "web/src/api/__tests__/token.ts",
              "web/src/api/token.spec.tsx", "web/src/api/tokenizer.test.ts"]
        _t, got = _m("web/src/api/token.ts", fs)
        self.assertEqual({f for f, _ in got}, {"web/src/api/token.test.ts", "web/src/api/__tests__/token.ts",
                                              "web/src/api/token.spec.tsx"})
        self.assertTrue(all(r == "dir" for _f, r in got))

    def test_other_language_is_not_a_pair(self):
        _t, got = _m("sidereus/retro.py", ["sidereus/retro.py", "web/retro.test.js"])
        self.assertEqual(got, [])


class RefFallback(unittest.TestCase):
    def test_python_quoted_module_name(self):
        fs = ["sidereus/usage.py", "tests/test_quota_who.py", "tests/test_x.py"]
        b = {"tests/test_quota_who.py": 'u = _load.sidereus("usage")\n', "tests/test_x.py": "usage = 1\n"}
        _t, got = _m("sidereus/usage.py", fs, b)
        self.assertEqual(got, [("tests/test_quota_who.py", "ref")])
        _t, back = _m("tests/test_quota_who.py", fs, b)
        self.assertEqual(back, [("sidereus/usage.py", "ref")])

    def test_name_match_skips_fallback(self):
        fs = ["sidereus/retro.py", "tests/test_retro.py", "tests/test_y.py"]
        _t, got = _m("sidereus/retro.py", fs, {"tests/test_y.py": "import retro\n"})
        self.assertEqual(got, [("tests/test_retro.py", "name")])

    def test_python_quoted_string_is_not_a_reference(self):
        fs = ["sidereus/usage.py", "tests/test_other.py"]
        b = {"tests/test_other.py": 'x = "usage"\ny = \'sidereus("usage")\'\n"""\nimport sidereus.usage\n"""\n# import sidereus.usage\n'}
        self.assertEqual(_m("sidereus/usage.py", fs, b)[1], [])

    def test_python_import_forms(self):
        fs = ["sidereus/usage.py", "tests/test_a.py", "tests/test_b.py", "tests/test_c.py"]
        b = {"tests/test_a.py": "import sidereus.usage as u\n", "tests/test_b.py": "from sidereus import (live,\n  usage)\n",
             "tests/test_c.py": "from sidereus.usage import quota_who\n"}
        self.assertEqual(len(_m("sidereus/usage.py", fs, b)[1]), 3)

    def test_js_import_path(self):
        fs = ["src/lib/clock.ts", "src/app.test.ts", "src/other.test.ts"]
        b = {"src/app.test.ts": "import { now } from './lib/clock'\n",
             "src/other.test.ts": "import { clock } from 'clock'\n// from './lib/clock'?\n"}
        _t, got = _m("src/lib/clock.ts", fs, b)
        self.assertEqual(got, [("src/app.test.ts", "ref")])

    def test_java_import_and_same_package(self):
        fs = ["src/main/java/a/b/Foo.java", "src/test/java/a/x/UsesTest.java", "src/test/java/a/b/PkgTest.java",
              "src/test/java/a/b/CommentTest.java", "src/test/java/q/OtherTest.java"]
        fs.append("src/test/java/a/x/UnusedTest.java")      # import without use is not a reference
        b = {"src/test/java/a/x/UsesTest.java": "package a.x;\nimport a.b.Foo;\nclass UsesTest { Foo f; }\n",
             "src/test/java/a/x/UnusedTest.java": "package a.x;\nimport a.b.Foo;\nclass UnusedTest {}\n",
             "src/test/java/a/b/PkgTest.java": "package a.b;\nclass PkgTest { Foo f = new Foo(); }\n",
             "src/test/java/a/b/CommentTest.java": "package a.b;\n// Foo\nclass CommentTest { String s = \"Foo\"; }\n",
             "src/test/java/q/OtherTest.java": "package q;\nclass OtherTest { Foo f; }\n"}
        _t, got = _m("src/main/java/a/b/Foo.java", fs, b)
        self.assertEqual({f for f, _ in got}, {"src/test/java/a/x/UsesTest.java", "src/test/java/a/b/PkgTest.java"})


def _u(rel, files, bodies):
    _t, out = S._struct_pair_match(rel, files, lambda f: bodies.get(f, ""))
    return [(r["file"], r.get("uses")) for r in out]


class RefOrderByUses(unittest.TestCase):
    def test_java_own_test_beats_config_import(self):
        # repo-J LegacyDdlParseController: config test imports it (2 uses) vs the gate test (3 uses)
        fs = ["src/main/java/a/c/Ctl.java", "src/test/java/a/cfg/ExposureTest.java", "src/test/java/a/c/GateTest.java"]
        b = {"src/test/java/a/cfg/ExposureTest.java": "package a.cfg;\nimport a.c.Ctl;\nclass ExposureTest { Ctl c() { return null; } }\n",
             "src/test/java/a/c/GateTest.java": "package a.c;\nclass GateTest { void t() { g(Ctl.class); Ctl c = new Ctl(); } }\n"}
        self.assertEqual(_u("src/main/java/a/c/Ctl.java", fs, b),
                         [("src/test/java/a/c/GateTest.java", 3), ("src/test/java/a/cfg/ExposureTest.java", 1)])

    def test_ties_keep_via_order_and_cap_after_sort(self):
        fs = ["src/main/java/a/Foo.java"] + ["src/test/java/%s/T%dTest.java" % (p, i) for i, p in enumerate("abqrsty")]
        b = {f: "package %s;\nimport a.Foo;\nclass X { Foo f; }\n" % f.split("/")[3] for f in fs[1:]}
        b[fs[-1]] = "package t;\nimport a.Foo;\nclass X { Foo a = new Foo(); Foo b; }\n"   # last by path, most used
        got = _u(fs[0], fs, b)
        self.assertEqual(len(got), S.STRUCT_PAIR_REF_MAX)
        self.assertEqual(got[0], (fs[-1], 3))
        self.assertEqual([f for f, _ in got[1:]], sorted([f for f, _ in got[1:]], key=lambda f: (len(f), f)))

    def test_python_loader_binding_and_js_names(self):
        fs = ["sidereus/usage.py", "tests/test_a.py", "tests/test_b.py"]
        b = {"tests/test_a.py": 'U = _load.sidereus("usage")\nU.f()\n',
             "tests/test_b.py": 'from sidereus.usage import f, g as h\nf(); h(); h()\n# f f f\n'}
        self.assertEqual(_u("sidereus/usage.py", fs, b), [("tests/test_b.py", 3), ("tests/test_a.py", 1)])
        fs = ["src/clock.ts", "src/a.test.ts", "src/b.test.ts"]
        b = {"src/a.test.ts": "import { now } from './clock'\nnow()\n",
             "src/b.test.ts": "import * as c from './clock'\nc.now(); c.tick() // c\n"}
        self.assertEqual(_u("src/clock.ts", fs, b), [("src/b.test.ts", 2), ("src/a.test.ts", 1)])


class Endpoint(unittest.TestCase):
    def setUp(self):
        self.d = os.path.realpath(tempfile.mkdtemp())
        for rel, body in (("pkg/core.py", "def f():\n    pass\n"), ("tests/test_core.py", "import core\n"),
                          ("node_modules/x/core.test.js", "")):
            p = os.path.join(self.d, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                f.write(body)
        S._struct_pair_ls.clear()
        S._struct_pair_cache.clear()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_pairs_and_confinement(self):
        with mock.patch.object(S, "_struct_src_root", lambda p: self.d if p == self.d else ""):
            r = S.structure_pair(self.d, "pkg/core.py")
            self.assertTrue(r["ok"])
            self.assertEqual([x["file"] for x in r["pairs"]], ["tests/test_core.py"])
            self.assertTrue(S.structure_pair(self.d, "pkg/core.py")["warm"])
            self.assertFalse(S.structure_pair("/etc", "passwd.py")["ok"])
            self.assertFalse(S.structure_pair(self.d, "../../etc/x.py")["ok"])


if __name__ == "__main__":
    unittest.main()
