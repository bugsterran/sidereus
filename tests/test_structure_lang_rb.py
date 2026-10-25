"""Ruby plug-in (sidereus/structure_lang_rb.py): masking, treemap cells, test/skip paths and pathological input
through the treemap entry — synthetic sources only."""
import time
import unittest

from tests._load import sidereus

RB = sidereus("structure_lang_rb")
P = sidereus("structure_plug")
SL = sidereus("structure_lang")

CTL = ('# frozen_string_literal: true\n'
       'module Shop\n  module Admin\n    class OrdersController < ApplicationController\n'
       '      include Pagination, Auditable\n      before_action :load\n'
       '      def index\n        @orders = Order.where(x: "#{a} class Nope end").page(params[:page])\n'
       '        q = %w(class end def)\n        r = /end|class/\n        s = <<~SQL\n          select end\n        SQL\n'
       '        Helper.call(s) if r\n      end\n'
       '      def self.build(a, b = 1, *rest, key:, &blk) = new(a)\n      private\n'
       '      def load\n        @order = ::Order.find(params[:id]) unless x\n      end\n    end\n  end\nend\n')


class Mask(unittest.TestCase):
    def test_literals_comments_heredocs_blanked(self):
        src = ('a = "x #{b "}" } end" # end\n=begin\nclass Hidden\n=end\nq = %w[end class] + %Q{a {b} end}\n'
               'r = x / 2 + (/end/)\nh = <<-EOS\n  end\n  EOS\nc = ?"\nz = 1\n__END__\nclass Gone\n')
        m = RB.rb_mask(src)
        self.assertEqual((len(m), m.count("\n")), (len(src), src.count("\n")))
        for w in ("end", "Hidden", "class", "Gone", "EOS"):
            self.assertNotIn(w, m, w)
        self.assertIn("r = x / 2", m)                       # division stays code
        self.assertIn("z = 1", m)

    def test_unterminated_string_blanks_to_end(self):
        m = RB.rb_mask('x = "abc\nclass A\nend\n')
        self.assertNotIn("class", m)


class Scan(unittest.TestCase):
    def test_scan(self):
        self.assertEqual([f["name"] for f in RB.rb_scan(CTL)],
                         ["OrdersController.index", "OrdersController.build", "OrdersController.load"])

    def test_paths(self):
        self.assertTrue(P.plug_is_test("spec/models/order_spec.rb"))
        self.assertTrue(P.plug_is_test("test/models/order_test.rb"))
        self.assertTrue(P.plug_is_test("test/helpers/x.rb"))
        self.assertFalse(P.plug_is_test("app/models/contest.rb"))
        for rel in ("vendor/bundle/x.rb", "tmp/cache/y.rb", "log/z.rb"):
            self.assertTrue(P.plug_skip(rel), rel)
        self.assertFalse(P.plug_skip("app/models/order.rb"))


N = 100000


class Pathological(unittest.TestCase):
    def test_pathological_input_is_fast(self):
        for src in ("x = <<~EOS\n" + "a end\n" * (N // 6), 'x = "' + "class A\n" * (N // 8), "q = %w(" + "a " * (N // 2),
                    '"#{' * N, "(" * N, "a " * 80000, "A::" * 30000, "class A\n" * (N // 8), "def a(" * (N // 6),
                    "/" * N, "%(" * N, "?" * N, "<<A " * (N // 4), "if " * (N // 3), "x.y" * (N // 3)):
            t0 = time.process_time()
            SL._struct_one_file("a.rb", src + " ")                     # treemap entry
            self.assertLess(time.process_time() - t0, 5.0, src[:12]) # did-not-hang bound: catastrophic backtracking runs for minutes, a loaded runner adds seconds



if __name__ == "__main__":
    unittest.main()
