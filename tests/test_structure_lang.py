"""Table tests for sidereus/structure_lang.py — per-language function extraction and `_struct_one_file`.

Synthetic source strings only; nothing touches a live repo.
"""
import unittest

from tests._load import sidereus

L = sidereus("structure_lang")


def _names(fns):
    return [f["name"] for f in fns]


class OneFileDispatch(unittest.TestCase):
    def test_line_count_and_lang_by_extension(self):
        # (rel, src, lines, [names], lang, skipped)
        rows = [
            ("e.py", "", 1, [], None, 0),                       # empty file still counts one line
            ("a.py", "def f():\n    return 1\n", 3, ["f"], "py", 0),
            ("a.js", "function f() { return 1 }\n", 2, ["f"], "js", 0),
            ("a.ts", "const g = (x) => { return x }\n", 2, ["g"], "js", 0),
            ("A.java", "class A { void f() {} }", 1, ["A.f"], "java", 0),
            ("K.kt", "class K { fun f() {} }", 1, ["K.f"], "kt", 0),
            ("x.go", "package x\nfunc F() {\n}\n", 4, ["F"], "go", 0),
            ("p.jsp", "a\r\nb\n", 3, ["p.jsp"], "jsp", 0),       # one cell per file; CRLF counts by \n
            ("t.tag", "x", 1, ["t.tag"], "jsp", 0),
            ("B.java", "class B { void f() {", 1, [], None, 1),  # unbalanced -> whole file skipped
        ]
        for rel, src, n, names, lang, skip in rows:
            with self.subTest(rel=rel):
                got_n, fns, got_skip = L._struct_one_file(rel, src)
                self.assertEqual((got_n, _names(fns), got_skip), (n, names, skip))
                for f in fns:
                    self.assertEqual(f["file"], rel)
                    if lang:
                        self.assertEqual(f["lang"], lang)

    def test_minified_js_only(self):
        long = "var a=" + "1+" * L.STRUCT_MINIFIED_COL + "1;\nfunction f() { }\n"
        self.assertEqual(L._struct_one_file("m.js", long), (3, [], 0))
        # ⚠the minified rule is js-family only — long lines are normal in java
        jv = "class A { void f() { String s = \"" + "x" * 2100 + "\"; } }"
        self.assertEqual(_names(L._struct_one_file("A.java", jv)[1]), ["A.f"])

    def test_py_embedded_script_offsets(self):
        src = 'PAGE = """\n<' + 'script>\nfunction hi() {\n  return 1;\n}\n</' + 'script>\n"""\ndef g():\n    pass\n'
        _n, fns, _s = L._struct_one_file("page.py", src)
        by = {f["name"]: f for f in fns}
        self.assertEqual(set(by), {"g", "hi"})
        self.assertEqual((by["hi"]["lang"], by["hi"]["line"], by["hi"]["lines"]), ("js", 3, 3))

    def test_hash_stable_and_body_sensitive(self):
        a = L._struct_one_file("a.py", "def f():\n    return 1\n")[1][0]["h"]
        b = L._struct_one_file("b.py", "\n\ndef f():\n    return 1\n")[1][0]["h"]
        c = L._struct_one_file("a.py", "def f():\n    return 2\n")[1][0]["h"]
        self.assertEqual(a, b)          # same body, different position
        self.assertNotEqual(a, c)


class Python(unittest.TestCase):
    def test_nested_async_and_syntax_error(self):
        src = "async def a():\n    def inner():\n        pass\n    return 1\n\nclass C:\n    def m(self): pass\n"
        got = {(f["name"], f["line"], f["lines"]) for f in L._struct_py_fns(src)}
        self.assertEqual(got, {("a", 1, 4), ("inner", 2, 2), ("m", 7, 1)})
        self.assertEqual(L._struct_py_fns("def broken(:\n"), [])

    def test_crlf(self):
        got = L._struct_py_fns("def f():\r\n    x = 1\r\n    return x\r\n")
        self.assertEqual([(f["name"], f["lines"]) for f in got], [("f", 3)])


class JavaScript(unittest.TestCase):
    def test_strings_comments_regex_do_not_break_braces(self):
        src = ("const s = '{';\n"
               "function f(a) {\n"
               "  /* } */ const t = `}${a}`; // }\n"
               "  return '}' + /}/.test(a);\n"
               "}\r\n"
               "const g = u => u + 1;\n"
               "let h = async function () { return \"}\" };\n")
        got = [(f["name"], f["line"], f["lines"]) for f in L._js_scan(src, 1)]
        self.assertEqual(got, [("f", 2, 4), ("g", 6, 1), ("h", 7, 1)])

    def test_functions_inside_comments_strings_regex_ignored(self):
        # (src, [(name, line)])
        rows = [
            ("// function x() {}\nfunction f() {}\n", [("f", 2)]),
            ("/* function x() {}\n const y = () => {} */\nfunction f() {}\n", [("f", 3)]),
            ("function f() {}\n/* function x() {} never closed\nfunction g() {}\n", [("f", 1)]),
            ("const u = 'http://x/function a() {}';\nfunction f() {}\n", [("f", 2)]),
            ("const d = \"function b() {}\"; let t = `\nfunction c() {}\n`;\nfunction f() {}\n", [("f", 4)]),
            ("const r = /function z() {}/g;\nfunction f() {}\n", [("f", 2)]),
            ("const q = a / b; function f() { return 1 / 2 }\n", [("f", 1)]),   # division is not a regex
            ("const s = 'it\\'s function w() {}'; function f() {}\n", [("f", 1)]),
        ]
        for src, want in rows:
            with self.subTest(src=src):
                self.assertEqual([(f["name"], f["line"]) for f in L._js_scan(src, 1)], want)

    def test_mask_keeps_offsets(self):
        src = "a // c\n/* x\ny */ 'q\\'s' `t\nu` = /r/ b"
        m = L._js_mask(src)
        self.assertEqual((len(m), m.count("\n")), (len(src), src.count("\n")))
        self.assertEqual([i for i, c in enumerate(m) if c == "\n"], [i for i, c in enumerate(src) if c == "\n"])
        self.assertEqual(m.replace(" ", "").replace("\n", ""), "a''``=//b")

    def test_unclosed_and_huge_dropped(self):
        self.assertEqual(L._js_scan("function f() {\n  if (x) {\n", 1), [])
        big = "function big() {\n" + "x;\n" * 900 + "}\n"
        self.assertEqual(L._js_scan(big, 1), [])

    def test_block_end(self):
        rows = [("{ a { b } }", 0, 10), ("x => y;", 0, 6), ("no brace", 0, -1), ("{ '}' }", 0, 6)]
        for s, i, want in rows:
            with self.subTest(s=s):
                self.assertEqual(L._js_block_end(s, i), want)


class Java(unittest.TestCase):
    def test_sig_table(self):
        rows = [
            ("public void run()", "run"),
            ("public <T> List<T> map(T x) throws IOException", "map"),
            ("@Override public String toString()", "toString"),
            ('@GetMapping(value = ") public R get(@PathVariable(name = ") String id)', "get"),
            ("fun total(x: Int): Int", "total"),          # Kotlin return type
            ("if (x)", None),
            ("new Runnable()", None),
            ("Runnable r = new Runnable()", None),
            ("int x = compute(1)", None),
            ("() ->", None),
            ("foo.bar()", None),
            ("no parens", None),
        ]
        for seg, want in rows:
            with self.subTest(seg=seg):
                self.assertEqual(L._java_sig(seg), want)

    def test_scan_class_members(self):
        src = ('package a;\n'
               'class A {\n'
               '  @RequestMapping(value = "/x")\n'
               '  public void f() { return; }\n'
               '  @Test(expected = X.class) void g() {}\n'
               '  int x = compute(1);\n'
               '  Runnable r = new Runnable() { public void run() {} };\n'
               '  static { init(); }\n'
               '  A(int a) throws Exception { }\n'
               '  String t = """\n    { not code\n    """;\n'
               '  char c = \'{\';\n'
               '  class In { void h() { if (true) { } } }\n'
               '}\n')
        got = [(f["name"], f["line"], f["lines"]) for f in L._java_scan(src)]
        self.assertEqual(got, [("A.f", 3, 2), ("A.g", 5, 1), ("A.A", 9, 1), ("In.h", 14, 1)])

    def test_kotlin_typed_functions(self):
        src = ("class K {\n"
               "  fun a(x: Int): Int { return x }\n"
               "  fun b() { }\n"
               "  fun c(): Map<String, Int> { return mapOf() }\n"
               "  val o = object : Runnable { override fun run() {} }\n"
               "}\n")
        self.assertEqual(_names(L._java_scan(src, "kt")), ["K.a", "K.b", "K.c"])

    def test_abandon_whole_file(self):
        rows = ['class A { void f() { String s = "open\n; } }',   # unclosed string
                "class A { /* never closed ",
                "class A { void f() { }",                          # depth != 0
                "} class A {}",                                    # depth < 0
                'class A { String t = """ open']
        for src in rows:
            with self.subTest(src=src):
                self.assertIsNone(L._java_scan(src))


class Go(unittest.TestCase):
    def test_scan_table(self):
        src = ("package p\n"
               "func A() {}\n"
               "func (r *Repo[T]) Get(k string) (T, error) {\n  return nil, nil\n}\n"
               "func B() map[string]interface{} {\n  return nil\n}\n"
               "func C() struct{ a int } {\n  return struct{ a int }{}\n}\n"
               "func asm(x int) int\n")
        got = [(f["name"], f["line"], f["lines"]) for f in L._go_scan(src)]
        self.assertEqual(got, [("A", 2, 1), ("Repo.Get", 3, 3), ("B", 6, 3), ("C", 9, 3)])


if __name__ == "__main__":
    unittest.main()
