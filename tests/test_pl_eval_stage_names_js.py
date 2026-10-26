"""Eval panel and suggestion list show stage display names (plgShow) like the canvas; wire text and red-check keys keep the saved title."""
import json
import shutil
import unittest

from tests.test_pl_eval_view import _node

EV = {"ok": True, "graded": {"n": 1, "m": 2},
      "stages": [{"title": "검증", "catch": {"caught": 1, "n": 2}, "red": "pass"},
                 {"title": "리뷰", "catch": None, "red": "none"}],
      "sugg": [{"code": "redcheck", "stage": "리뷰", "cmd": "c"},
               {"code": "add-gate", "stage": "검증", "kind": "dep", "tpl": "t"}]}
# Display map stub; '<b>' checks the shown name is still escaped.
SHOW = "function plgShow(t){ return ({'검증': 'Verify <b>', '리뷰': 'Review'})[t] || t; }\n"


@unittest.skipUnless(shutil.which("node"), "node not installed")
class EvalStageNames(unittest.TestCase):
    def test_panel_and_suggestions_use_display_names(self):
        p, sg, body = _node(SHOW + "const S = {sel: {}, req: null, sent: '', msg: ''};"
                            "console.log(JSON.stringify([plEvalPanel(%s), plEvalSgHtml(%s, S, [], null),"
                            " plEvalFixBody('/p', 'f', plEvalSgList(%s))]));" % ((json.dumps(EV),) * 3))
        self.assertIn("<td>Verify &lt;b></td>", p)
        self.assertIn("<td>Review</td>", p)
        self.assertNotIn("검증", p + sg)
        self.assertIn("red check needed", p)                     # need[] still keyed by the saved title
        self.assertIn("Stage Verify &lt;b> has no gate", sg)
        self.assertIn("Stage Review: red check needed", sg)
        self.assertIn("Stage 검증 has no gate", body)            # mailbox wire text keeps the saved title


if __name__ == "__main__":
    unittest.main()
