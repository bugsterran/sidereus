"""structure_lang_c: C/C++ plug-in — masking, treemap scan and linear time (synthetic sources only)."""
import time
import unittest

from tests._load import sidereus

C = sidereus("structure_lang_c")


class TestMask(unittest.TestCase):
    def test_comments_strings_raw_chars_defines(self):
        src = ('int a = 1\'000; // class X {\nconst char* s = "class Y {";\nauto r = R"d(class Z { )" )d";\n'
               "char c = '{';\n#define M(x) \\\n  class W {\n/* class V { */ int b;\n")
        m, _i = C.c_mask(src)
        self.assertEqual(len(m), len(src))
        self.assertEqual(m.count("\n"), src.count("\n"))
        for w in ("X", "Y", "Z", "W", "V"):
            self.assertNotIn("class " + w, m)
        self.assertNotIn("{", m)
        self.assertIn("1'000", m)

    def test_if0_dropped_else_kept_and_first_branch_only(self):
        src = "#if 0\nclass Dead {};\n#else\nclass Live {};\n#endif\n#ifdef A\nclass One {};\n#else\nclass Two {};\n#endif\n"
        names = [c["name"] for c in C.c_walk(C.c_mask(src)[0])[0]]
        self.assertEqual(names, ["Live", "One"])

    def test_includes_kind_and_inactive(self):
        _m, incs = C.c_mask('#include "a.h"\n#  include <b/c.h>\n#if 0\n#include "dead.h"\n#endif\n')
        self.assertEqual(incs, [('"', "a.h", 1), ("<", "b/c.h", 2)])


class TestRows(unittest.TestCase):
    def test_header_lang_guess(self):
        self.assertEqual(C.c_lang("a.h", "struct P { int x; };\nint f(void);\n"), "c")
        self.assertEqual(C.c_lang("a.h", "namespace n { int f(); }\n"), "cpp")
        self.assertEqual(C.c_lang("a.h", "int x = a::b;\n"), "cpp")
        self.assertEqual(C.c_lang("a.h", "// class in a comment\nint f(void);\n"), "c")
        self.assertEqual(C.c_lang("a.c", "class"), "c")
        self.assertEqual(C.c_lang("a.hpp", ""), "cpp")

    def test_owner_rows_for_out_of_class_definitions(self):
        src = "#include \"foo.h\"\nnamespace n {\nvoid Foo::bar() { baz(); }\nFoo::Foo() : a_(1), b_{2} { }\n}\nint free_fn(void) { return 0; }\n"
        rows = dict((r["name"], r) for r in C.c_scan(src))
        self.assertEqual(sorted(rows), ["Foo::Foo", "Foo::bar", "free_fn"])
        self.assertEqual((rows["Foo::bar"]["owner"], rows["Foo::bar"]["line"]), ("Foo", 3))
        self.assertNotIn("owner", rows["free_fn"])
        self.assertEqual(rows["Foo::Foo"]["line"], 4)

    def test_extern_c_braces_balance(self):
        src = ('extern "C" {\n#ifdef _WIN32\nint w(void) {\n#else\nint p(void) {\n#endif\n  return 0;\n}\n}\n'
               "struct After { int x; };\nstatic int last(int a) { return a; }\n")
        self.assertEqual([r["name"] for r in C.c_scan(src)], ["w", "last"])

class TestLinearTime(unittest.TestCase):
    """Through the real entry point: the treemap dispatcher."""
    CASES = {"lt": "<" * 100000, "paren": "(" * 100000, "brace": "{" * 100000, "qual": "a::" * 100000,
             "if0": "#if 0\n" * 50000, "comment": "int x;\n/*" + "a\n" * 50000, "raw": 'auto s = R"x(' + "b\n" * 50000,
             "hash": "a#" * 100000, "head": "void f(" + "a::" * 30000 + ") {}\n" + "}" * 1000,
             "ifcomment": "#if /* " + "/* " * 40000,
             "nested": ("template <class T> struct S" + "<a" * 20000 + ">" * 20000 + " { T x; };\n") * 3}

    def test_pathological_input_is_fast(self):
        L = sidereus("structure_lang")
        for nm, src in sorted(self.CASES.items()):
            t = time.process_time()
            self.assertIsNotNone(L._struct_one_file(nm + ".cpp", src), nm)
            self.assertLess(time.process_time() - t, 5.0, nm) # did-not-hang bound: catastrophic backtracking runs for minutes, a loaded runner adds seconds


if __name__ == "__main__":
    unittest.main()
