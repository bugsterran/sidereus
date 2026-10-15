"""structure_plug: language plug-in registry, sorted loading and treemap dispatch."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

PL = sidereus("structure_plug")
LG = sidereus("structure_lang")


class Registry(unittest.TestCase):
    def test_key_errors(self):
        with mock.patch.dict(PL.LANGS, clear=True):
            with self.assertRaises(ValueError):
                PL.lang_register("x", {"exts": (".x",), "parse": None})
            with self.assertRaises(ValueError):
                PL.lang_register("x", {"lang": "x"})                  # no exts
            with self.assertRaises(ValueError):
                PL.lang_register("x", {"exts": ("x",)})               # ext without the dot
            self.assertEqual(PL.LANGS, {})
            s = PL.lang_register("x", {"exts": (".x", ".xy"), "test": r"_t\.x$", "skip": ("gen*",),
                                       "gen": lambda rel: rel.endswith(".g.x"), "test_dirs": ("Specs",)})
            PL.lang_register("y", {"exts": (".y", ".x")})
            self.assertEqual(PL.plug_exts(), (".x", ".xy", ".y"))
            self.assertIs(PL.lang_for("a/b.xy"), s)
            self.assertEqual(PL.plug_test_pats(), [r"_t\.x$"])
            self.assertTrue(PL.plug_is_test("a/b_t.x"))
            self.assertTrue(PL.plug_is_test("specs/b.x"))              # dir names, case-insensitive
            self.assertFalse(PL.plug_is_test("a/b.y"))
            self.assertTrue(PL.plug_skip("generated/b.x"))
            self.assertTrue(PL.plug_skip("a/b.g.x"))
            self.assertFalse(PL.plug_skip("a/b.x"))
            self.assertFalse(PL.plug_skip("generated/b.py"))           # other exts untouched


class Load(unittest.TestCase):
    def test_sorted_glob_and_broken_module(self):
        d = tempfile.mkdtemp()
        try:
            for n in ("structure_lang_b.py", "structure_lang_a.py", "structure_lang_bad.py", "structure_lang.py",
                      "other_lang_c.py"):
                open(os.path.join(d, n), "w").close()
            seen, warned = [], []

            def imp(mod):
                seen.append(mod)
                if mod.endswith("_bad"):
                    raise SyntaxError("x")
            with mock.patch.object(PL, "PLUG_DIR", d), mock.patch.object(PL, "_import", imp), \
                    mock.patch.object(PL, "_loaded", []), \
                    mock.patch.object(PL, "warn_once", lambda k, m, **kw: warned.append(k)):
                got = PL.plug_load()
                PL.plug_load()                                         # once each
            want = ["sidereus.structure_lang_a", "sidereus.structure_lang_b", "sidereus.structure_lang_bad"]
            self.assertEqual(seen, want)
            self.assertEqual(got, want)
            self.assertEqual(warned, ["plug:sidereus.structure_lang_bad"])
        finally:
            shutil.rmtree(d)


class Dispatch(unittest.TestCase):
    def test_scan(self):
        with mock.patch.dict(PL.LANGS, clear=True):
            PL.lang_register("zz", {"exts": (".zz",), "lang": lambda rel, src: "zz",
                                    "scan": lambda src: [{"name": "f", "line": 2, "lines": 1, "h": "x"}]})
            n, fns, skip = LG._struct_one_file("a.zz", "ns n\nclass A\n")
            self.assertEqual((n, skip), (3, 0))
            self.assertEqual(fns, [{"name": "f", "line": 2, "lines": 1, "h": "x", "lang": "zz", "file": "a.zz"}])
            PL.LANGS["zz"]["scan"] = lambda src: None              # parse failure counts as skipped
            self.assertEqual(LG._struct_one_file("a.zz", "")[1:], ([], 1))
            for k in ("fam", "rel", "calls", "index", "resolve", "imp", "pair"):   # Relations-era keys are refused
                with self.assertRaises(ValueError):
                    PL.lang_register("zz", {"exts": (".zz",), k: None})


if __name__ == "__main__":
    unittest.main()
