"""Table tests for sidereus/structure_pairing.py helpers and name rules (test_structure_pair.py covers refs/endpoint).

Pure inputs (file lists, synthetic bodies) plus one temp-dir walk for `_struct_pair_files`.
"""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

P = sidereus("structure_pairing")


def _m(rel, files):
    t, out = P._struct_pair_match(rel, files)
    return t, [(r["file"], r["reason"]) for r in out]


class Subject(unittest.TestCase):
    def test_test_name_to_subject(self):
        rows = [("test_foo.py", ("foo", ".py")), ("foo_test.py", ("foo", ".py")),
                ("foo.test.ts", ("foo", ".ts")), ("foo.spec.jsx", ("foo", ".jsx")),
                ("FooTest.java", ("Foo", ".java")), ("FooTests.kt", ("Foo", ".kt")),
                ("FooIT.java", ("Foo", ".java")), ("foo_test.go", ("foo", ".go")),
                ("foo.py", ("", "")), ("Contest.java", ("", "")), ("foo.test.py", ("", ""))]
        for base, want in rows:
            with self.subTest(base=base):
                self.assertEqual(P._struct_pair_subject(base), want)

    def test_family(self):
        self.assertEqual(P._struct_pair_fam(".tsx"), (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts"))
        self.assertEqual(P._struct_pair_fam(".py"), (".py",))

    def test_mirror(self):
        rows = [("src/main/java/A.java", "src/test/java/A.java"),
                ("src/test/java/A.java", "src/main/java/A.java"),
                ("main/x.py", "test/x.py"), ("lib/x.py", ""), ("maintenance/x.py", "")]
        for rel, want in rows:
            with self.subTest(rel=rel):
                self.assertEqual(P._struct_pair_mirror(rel), want)


class NameMatch(unittest.TestCase):
    def test_table(self):
        # (rel, files, is_test, [(file, reason)])
        rows = [
            ("foo.py", ["foo.py", "tests/test_foo.py", "tests/unit/test_foo.py"],
             False, [("tests/test_foo.py", "dir"), ("tests/unit/test_foo.py", "name")]),
            ("tests/unit/test_foo.py", ["foo.py", "tests/unit/foo.py", "tests/unit/test_foo.py"],
             True, [("foo.py", "name")]),                 # a file inside tests/ is never a subject
            ("tests/test_foo.py", ["foo.py", "pkg/foo.py", "tests/test_foo.py"],
             True, [("foo.py", "dir"), ("pkg/foo.py", "name")]),
            ("src/main/java/a/Foo.java", ["src/main/java/a/Foo.java", "src/test/java/a/FooTest.java",
                                          "src/test/java/a/FooIT.java", "src/test/java/a/FooTest.kt"],
             False, [("src/test/java/a/FooIT.java", "mirror"), ("src/test/java/a/FooTest.java", "mirror")]),
            ("src/x.ts", ["src/x.ts", "src/__tests__/x.ts", "src/x.spec.js", "src/x.test.py"],
             False, [("src/x.spec.js", "dir"), ("src/__tests__/x.ts", "dir")]),
            ("src/__tests__/x.test.tsx", ["src/x.tsx", "lib/x.js", "src/x.py"],
             True, [("src/x.tsx", "dir"), ("lib/x.js", "name")]),
            ("a/util.go", ["a/util.go", "a/util_test.go"], False, [("a/util_test.go", "dir")]),
            ("a/util.go", ["a/util.go", "a/util_test.py"], False, []),     # other language
            ("tests/test_nothing.py", ["foo.py", "tests/test_nothing.py"], True, []),
        ]
        for rel, files, is_test, want in rows:
            with self.subTest(rel=rel, files=files):
                self.assertEqual(_m(rel, files), (is_test, want))

    def test_go_needs_same_dir(self):
        # ⚠Go tests belong to the package dir — `b/util_test.go` cannot test `a/util.go`.
        fs = ["a/util.go", "a/util_test.go", "b/util_test.go", "b/other.go"]
        self.assertEqual(_m("a/util.go", fs), (False, [("a/util_test.go", "dir")]))
        self.assertEqual(_m("b/util_test.go", fs), (True, []))
        self.assertEqual(_m("a/util_test.go", fs), (True, [("a/util.go", "dir")]))

    def test_c_and_cs_plugins(self):
        # fake plug-ins own the test classification (structure_plug); the name rules live here
        pl = sidereus("structure_plug")
        rows = [("src/foo.cc", ["src/foo.cc", "src/foo.h", "test/foo_test.cc", "test/foo_unittest.cpp"],
                 False, [("test/foo_test.cc", "name"), ("test/foo_unittest.cpp", "name")]),
                ("src/foo.h", ["src/foo.h", "src/foo_test.cc"], False, [("src/foo_test.cc", "dir")]),
                ("t/test_bar.c", ["lib/bar.c", "lib/bar.py"], True, [("lib/bar.c", "name")]),
                ("tests/Shop.Tests/Svc/OrderTests.cs", ["src/Shop/Svc/Order.cs", "other/Order.cs"],
                 True, [("src/Shop/Svc/Order.cs", "mirror"), ("other/Order.cs", "name")]),
                ("src/Shop/Svc/Order.cs", ["src/Shop/Svc/Order.cs", "tests/Shop.Tests/Svc/Order.cs",
                                           "x/OrderTests.cs"],
                 False, [("tests/Shop.Tests/Svc/Order.cs", "mirror"), ("x/OrderTests.cs", "name")])]
        with mock.patch.dict(pl.LANGS, clear=True):          # ⚠register inside: never over the real plug-ins
            pl.lang_register("c", {"exts": (".c", ".cc", ".cpp", ".h"), "test": r"_(?:unit)?test\.\w+$|/test_"})
            pl.lang_register("cs", {"exts": (".cs",), "test": r"Tests?\.cs$",
                                    "test_dirs": r"\.(?:Unit|Integration)?Tests?$"})
            for rel, files, is_test, want in rows:
                with self.subTest(rel=rel):
                    self.assertEqual(_m(rel, files), (is_test, want))
        self.assertEqual(P._struct_pair_subject("FooTests.cs"), ("Foo", ".cs"))
        self.assertEqual(P._struct_pair_subject("foo_unittest.cpp"), ("foo", ".cpp"))
        self.assertEqual(P._struct_pair_mirror("tests/A.UnitTests/b/C.cs"), "src/A/b/C.cs")

    def test_cap(self):
        fs = ["x.py"] + ["t%02d/test_x.py" % i for i in range(20)]
        _t, got = _m("x.py", fs)
        self.assertEqual(len(got), P.STRUCT_PAIR_MAX)


class Index(unittest.TestCase):
    def test_keys(self):
        idx = P._struct_pair_index(["pkg/sub/mod.py", "pkg/__init__.py", "top.py", "tests/test_top.py",
                                    "src/main/java/a/B.java", "src/main/kotlin/a/C.kt",
                                    "web/api/index.ts", "web/u.js"])
        self.assertEqual(idx["py"], {"pkg.sub.mod": "pkg/sub/mod.py", "sub.mod": "pkg/sub/mod.py",
                                     "pkg": "pkg/__init__.py", "top": "top.py"})
        self.assertEqual(idx["jv"], {"a.B": "src/main/java/a/B.java", "a.C": "src/main/kotlin/a/C.kt"})
        self.assertEqual(idx["js"], {"web/api/index": "web/api/index.ts", "web/api": "web/api/index.ts",
                                     "web/u": "web/u.js"})

    def test_py_code_blanks_strings_and_comments(self):
        code, loads = P._struct_pair_py_code("x = sidereus('usage')  # import y\ns = 'sidereus(\"x\")'\n")
        self.assertEqual(loads, [("sidereus", "usage")])
        self.assertNotIn("import", code)
        self.assertNotIn("sidereus(\"x\")", code)
        # untokenizable body falls back to regex loads
        _c, loads = P._struct_pair_py_code("x = sidereus('a')\n  (\n")
        self.assertEqual(loads, [("sidereus", "a")])


class Files(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="sidereus-pair-")
        for rel in ["a.py", "tests/test_a.py", "node_modules/x.js", ".hidden/y.py", "doc.md", "src/B.java"]:
            p = os.path.join(self.d, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w", encoding="utf-8").close()
        P._struct_pair_ls.pop(self.d, None)

    def tearDown(self):
        P._struct_pair_ls.pop(self.d, None)
        shutil.rmtree(self.d, ignore_errors=True)

    def test_walk_filters_and_caches(self):
        got = P._struct_pair_files(self.d)
        self.assertEqual(got, ["a.py", "src/B.java", "tests/test_a.py"])
        open(os.path.join(self.d, "new.py"), "w", encoding="utf-8").close()
        self.assertEqual(P._struct_pair_files(self.d), got)     # within TTL: cached list


if __name__ == "__main__":
    unittest.main()
