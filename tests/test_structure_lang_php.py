"""PHP plug-in (sidereus/structure_lang_php.py): masking, treemap cells, test/skip paths and pathological input
through the treemap entry — synthetic sources only."""
import time
import unittest

from tests._load import sidereus

P = sidereus("structure_lang_php")
PL = sidereus("structure_plug")
SL = sidereus("structure_lang")

CTL = (r'''<?php
namespace App\Http\Controllers;

use App\Models\{User, Post as Article};
use App\Contracts\UserRepository;
use Illuminate\Support\Facades\Log;

#[Middleware(['auth'])]
class UserController extends Controller implements \JsonSerializable
{
    use HasAudit;
    private ?Mailer $mailer = null;
    public function __construct(private readonly UserRepository $users, Clock $clock, int $n = 3) {}
    public function show(int $id): User {
        $s = "id {$id} } ?> // not code";
        $h = <<<EOT
          class Fake { }
          EOT;
        Log::info('x');
        return $this->users->find($this->wrap(new Article()));
    }
    private function wrap($x) { return $x; }
}
''')


class Mask(unittest.TestCase):
    def test_comments_strings_heredoc_html_blanked(self):
        src = ("<html>{ <?php $a = 'x{'; # c {\n// d { ?> <b>{</b> <?= $b ?>\n<?php /* { */ $c = \"q\\\"{\";\n"
               "$h = <<<'EOT'\n  { not code\n  EOT;\n$k = `ls {`; #[Attr] f();")
        m = P.php_mask(src)
        self.assertEqual((len(m), m.count("\n")), (len(src), src.count("\n")))
        self.assertNotIn("{", m)
        self.assertIn("#[Attr] f();", m)
        self.assertIn("$b", m)

    def test_unterminated_regions_blank_to_the_end(self):
        for src in ("<?php /* { x", "<?php $a = 'x { y", "<?php $h = <<<EOT\n{ a\n", "no php here {"):
            self.assertNotIn("{", P.php_mask(src), src)


class Scan(unittest.TestCase):
    def test_scan_cells(self):
        self.assertEqual([f["name"] for f in P.php_scan(CTL)],
                         ["UserController.__construct", "UserController.show", "UserController.wrap"])
        self.assertEqual([f["name"] for f in P.php_scan("<?php\nfunction helper() { return 1; }\n")], ["helper"])

    def test_paths(self):
        self.assertTrue(PL.plug_is_test("tests/Feature/UserTest.php"))
        self.assertTrue(PL.plug_is_test("app/tests/helpers.php"))
        self.assertFalse(PL.plug_is_test("app/Models/Contest.php"))
        for rel in ("vendor/laravel/x.php", "storage/framework/v.php", "bootstrap/cache/services.php",
                    "resources/views/home.blade.php"):
            self.assertTrue(PL.plug_skip(rel), rel)
        self.assertFalse(PL.plug_skip("app/Models/User.php"))



N = 100000


class Pathological(unittest.TestCase):
    CASES = ("<" * N, "<?php " + "<" * N, "<?php " + "{" * N, "<?php /*" + "x" * N, "<?php $h = <<<EOT\n" + "a\n" * (N // 2),
             "<?php $s = '" + "x" * N, '<?php $s = "' + "\\" * N, "<?php " + " ".join("a%d" % i for i in range(80000)),
             "<?php " + "Route::get('/x', [A::class, 'b']);\n" * 20000, "<?php " + "Route::get(" * 20000,
             "<?php class A { function f(" + "(" * N, "<?php class A { " + "public " * 20000 + "}",
             "<?php " + "namespace " * 20000, "<?php use " + "a\\" * 40000, "<?php " + "$a->" * 30000 + "b();",
             "<?php function f() { " + "x(" * 30000, "<?php function" + " " * N,          # blank run after `function`
             "<?php class A { " + "use " * 25000 + "}", "<?php Route::get('" + "{a" * 200000 + "', 'X@y');")

    def test_pathological_input_is_fast(self):
        for src in self.CASES:
            t0 = time.process_time()
            SL._struct_one_file("a.php", src + " ")                    # treemap entry
            self.assertLess(time.process_time() - t0, 5.0, src[:24]) # did-not-hang bound: catastrophic backtracking runs for minutes, a loaded runner adds seconds



if __name__ == "__main__":
    unittest.main()
