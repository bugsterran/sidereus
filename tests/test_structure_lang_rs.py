"""Rust plug-in (sidereus/structure_lang_rs.py): masking, treemap cells, test/skip paths and pathological input
through the treemap entry — synthetic sources only."""
import time
import unittest

from tests._load import sidereus

RS = sidereus("structure_lang_rs")
P = sidereus("structure_plug")
SL = sidereus("structure_lang")


class Mask(unittest.TestCase):
    def test_comments_strings_chars_lifetimes(self):
        src = ('a /* x /* y { */ z { */ b // c {\nlet s = r##"q"# {"##; let t = b"x\\"{"; let u = br#"{"#;\n'
               "let c = '{'; let d = '\\''; fn f<'a>(x: &'a str) -> &'a str { 'outer: loop {} }\n\"open {")
        m = RS.rs_mask(src)
        self.assertEqual((len(m), m.count("\n")), (len(src), src.count("\n")))
        self.assertEqual(m.count("{"), 2)                # the fn body and the labelled loop only
        self.assertIn("<'a>(x: &'a str)", m)
        self.assertIn("'outer: loop", m)


class Scan(unittest.TestCase):
    def test_scan_impl_methods_and_free_fns(self):
        src = ("pub struct U;\nimpl User {\n    pub fn new(id: u64) -> Self { User::build(id) }\n    pub fn name(&self) {}\n}\n"
               "fn main() {}\n")
        self.assertEqual([f["name"] for f in RS.rs_scan(src)], ["User::new", "User::name", "main"])

    def test_paths(self):
        self.assertTrue(P.plug_is_test("app/tests/it.rs"))
        self.assertTrue(P.plug_is_test("src/foo_test.rs"))
        self.assertFalse(P.plug_is_test("src/lib.rs"))
        self.assertTrue(P.plug_skip("target/debug/a.rs"))
        self.assertFalse(P.plug_skip("src/a.rs"))


class Pathological(unittest.TestCase):
    def test_entry_points_stay_fast(self):
        n = 100000
        ids = " ".join("a%d" % i for i in range(80000))
        for src in ('let s = r###"' + "x\n" * (n // 2), "/*" * 50000, "<" * n, "'a" * n, ids,
                    "fn r() -> Router { Router::new()\n" + '.route("/x", get(h))\n' * 20000 + "}\n",
                    ".route(" * 20000, "impl<" + "T, " * 30000 + "> X for Y {}", "fn f(" + "[" * n + ") {}",
                    "struct S {" + "a: u8, " * 30000 + "}", "use a::{" * 20000, "mod a { struct X; " * 20000,
                    "[;" * n):
            t0 = time.process_time()
            SL._struct_one_file("a.rs", src + " ")         # treemap entry
            self.assertLess(time.process_time() - t0, 1.0, src[:16])



if __name__ == "__main__":
    unittest.main()
