"""C# plug-in (sidereus/structure_lang_cs.py): masking, treemap cells, test/skip paths and pathological input —
synthetic sources only."""
import time
import unittest

from tests._load import sidereus

C = sidereus("structure_lang_cs")
P = sidereus("structure_plug")
SL = sidereus("structure_lang")

SVC = ('using System;\nusing static System.Math;\nusing Ent = Shop.Domain.Order;\nglobal using Shop.Shared;\n'
       'namespace Shop.Services;\n\n'
       '#if DEBUG\npublic partial class OrderService : BaseService<Ent>, IOrderService, IDisposable\n#else\n'
       'public class OrderService : Broken {\n#endif\n{\n'
       '    private readonly IOrderRepository _repo;\n    public string Name { get; set; } = "x // not a comment {";\n'
       '    public OrderService(IOrderRepository repo, IEnumerable<IRule> rules, int n) { _repo = repo; }\n'
       '    public async Task<Ent> GetAsync(int id) {\n'
       '        var s = $"id={id} {{x}} {(id > 0 ? "a" : "b")}";\n        var v = @"c:\\dir""q {";\n'
       '        var raw = """\n          { not a brace\n          """;\n'
       '        int Local(int x) { return Helper(x); }\n        return await _repo.FindAsync(Local(id));\n    }\n'
       '    public int Twice(int x) => Max(x, 2);\n}\n')
PROG = ('using Shop.Services;\nvar builder = WebApplication.CreateBuilder(args);\nvar app = builder.Build();\n'
        'static int Port() { return 80; }\napp.MapGet("/health", () => "ok");\napp.Run();\n')


class Mask(unittest.TestCase):
    def test_strings_comments_directives_blanked(self):
        src = ('a /* x { */ b // c {\n"s{" @"v""{" $"i{{ {f("q{")} }}" """r{"""\n#region R {\n'
               '#if A\nkeep {\n#elif B\ndrop {\n#if C\nx\n#endif\n#else\ndrop2 {\n#endif\nz')
        m = C.cs_mask(src)
        self.assertEqual((len(m), m.count("\n")), (len(src), src.count("\n")))
        self.assertEqual(m.count("{"), 1)                # only the first #if branch survives
        self.assertIn("keep {", m)
        self.assertNotIn("drop", m)
        self.assertTrue(m.endswith("z"))

    def test_char_literal_and_verbatim_identifier(self):
        m = C.cs_mask("var c = '\"'; var @class = 1; s = \"}\";")
        self.assertNotIn("}", m)
        self.assertIn("@class", m)


class Scan(unittest.TestCase):
    def test_scan_methods_ctors_local_functions(self):
        names = [f["name"] for f in C.cs_scan(SVC)]
        self.assertEqual(names, ["OrderService.OrderService", "OrderService.GetAsync", "OrderService.Local"])
        self.assertEqual([f["name"] for f in C.cs_scan(PROG)], ["Port"])

    def test_expression_body_braces_are_not_a_block(self):
        src = ('public class OrdersController : ControllerBase\n{\n'
               '    public ActionResult<Order> Get(int id) => _svc.Find(id) is { } o ? o : NotFound();\n'
               '    public IActionResult Purge(int id) => NoContent();\n'
               '    public IActionResult Create(Order o) { return Ok(); }\n}\n')
        self.assertEqual([x["name"] for x in C.cs_parse(src)["meths"]], ["Get", "Purge", "Create"])
        self.assertEqual([f["name"] for f in C.cs_scan(src)], ["OrdersController.Create"])   # block bodies only

    def test_paths(self):
        self.assertTrue(P.plug_is_test("Shop.Tests/OrderServiceTests.cs"))
        self.assertTrue(P.plug_is_test("tests/Shop.UnitTests/Helpers.cs"))
        self.assertFalse(P.plug_is_test("src/Shop/Contest.cs"))
        for rel in ("src/bin/Debug/X.cs", "src/obj/Y.cs", "a/Form1.Designer.cs", "a/Gen.g.cs",
                    "Properties/AssemblyInfo.cs"):
            self.assertTrue(P.plug_skip(rel), rel)
        self.assertFalse(P.plug_skip("src/Shop/Order.cs"))


PATHO = 100000


class Pathological(unittest.TestCase):
    def test_pathological_input_is_fast(self):
        n = PATHO
        for src in ("<" * n, "(" * n, "{" * n, "/*" + "x" * n, '@"' + "x\n" * (n // 2), '"""' + "x" * n,
                    '$"{' + "x" * n, "class A " + "<" * n, "class A { void F(" + "(" * n,
                    "class A { " + "void F() { " * (n // 12), "class A { " + "a" * (n - 20000) + " b x(); }"):
            t0 = time.process_time()
            SL._struct_one_file("a.cs", src + " ")          # treemap entry
            self.assertLess(time.process_time() - t0, 5.0, src[:12]) # did-not-hang bound: catastrophic backtracking runs for minutes, a loaded runner adds seconds

    def test_long_identifier_head(self):
        got = C.cs_scan("class A { int " + "a" * 5000 + "(int x) { return 1; } }")
        self.assertEqual([x["name"] for x in got], ["A." + "a" * 5000])


if __name__ == "__main__":
    unittest.main()
