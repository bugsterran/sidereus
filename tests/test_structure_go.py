"""Tests for Go support in the structure tab (sidereus/structure_scan.py `_go_scan` + test classification + pairing)."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

SC = sidereus("structure_scan")
S = sidereus("structure")

GO_SRC = '''package store

import "fmt"

type Store struct{ m map[string]interface{} }

func New() *Store {
	return &Store{m: map[string]interface{}{}}
}

func (s *Store) Get(k string) (interface{}, bool) {
	v, ok := s.m[k] // a comment with a } brace
	return v, ok
}

func Map[K comparable, V any](m map[K]V, f func(V) V) map[K]V {
	out := map[K]V{}
	for k, v := range m {
		out[k] = f(v)
	}
	fmt.Println("}")
	return out
}

func asm(x int) int
'''


class GoScan(unittest.TestCase):
    def test_functions_methods_generics(self):
        lines, fns, skip = SC._struct_one_file("pkg/store/store.go", GO_SRC)
        self.assertEqual(skip, 0)
        got = {f["name"]: (f["line"], f["lines"], f["lang"]) for f in fns}
        self.assertEqual(got, {"New": (7, 3, "go"), "Store.Get": (11, 4, "go"), "Map": (16, 8, "go")})
        self.assertTrue(all(f["file"] == "pkg/store/store.go" for f in fns))

    def test_ext_and_test_classification(self):
        self.assertIn(".go", SC.STRUCT_EXTS)
        self.assertTrue(SC._struct_wanted("pkg/store/store.go"))
        self.assertTrue(SC._struct_is_test("pkg/store/store_test.go"))
        self.assertFalse(SC._struct_is_test("pkg/store/store.go"))
        self.assertFalse(SC._struct_is_test("pkg/store/testutil.go"))


class GoPair(unittest.TestCase):
    def setUp(self):
        self.d = os.path.realpath(tempfile.mkdtemp())
        for rel, body in (("pkg/store/store.go", GO_SRC),
                          ("pkg/store/store_test.go", "package store\n\nfunc TestNew(t *testing.T) {\n}\n"),
                          ("pkg/other/store_test.go", "package other\n")):
            p = os.path.join(self.d, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(body)
        S._struct_pair_ls.clear()
        S._struct_pair_cache.clear()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_same_dir_pair_both_ways(self):
        with mock.patch.object(S, "_struct_src_root", lambda p: self.d if p == self.d else ""):
            r = S.structure_pair(self.d, "pkg/store/store.go")
            self.assertTrue(r["ok"])
            self.assertEqual([(x["file"], x["reason"]) for x in r["pairs"]][0], ("pkg/store/store_test.go", "dir"))
            back = S.structure_pair(self.d, "pkg/store/store_test.go")
            self.assertEqual([(x["file"], x["reason"]) for x in back["pairs"]], [("pkg/store/store.go", "dir")])
