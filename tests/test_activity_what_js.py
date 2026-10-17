"""web/js/42-activity.js actWhat: ctx pills show the real % (not the 85/95 threshold); 17-attention.js
attnWhy uses the strip's wording for ask; 62-attention.css dims low rows by colour, not opacity."""
import json
import os
import re
import subprocess
import unittest

from tests._i18n_js import i18n_switch
from tests._load import js_all, js_fn
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUB = "let LANG = %s; function PL(n, w){ return n + ' ' + w; } function waitOnLabel(){ return false; }\n"


def _tables():
    src = js_all()
    return "\n".join(re.search(r"^const " + n + r" = \{.*?\};", src, re.S | re.M).group(0) for n in ("LBL", "LBL_CTX", "ATTN_LBL"))


def run(lang, expr):
    js = (STUB % json.dumps(lang) + i18n_switch(("T", "TV", "U")) + _tables() + "\n" + js_fn("stateLbl") + "\n" + js_fn("attnLbl") + "\n"
          + js_fn("actWhat")) + "\n" + js_fn("attnWhy") + "\nconsole.log(JSON.stringify(" + expr + "));"
    return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


class ActWhat(unittest.TestCase):
    def test_ctx_shows_real_percent(self):
        self.assertEqual(run("ko", "actWhat({}, 'ctx85', '컨텍스트 87%')"), "컨텍스트 87%")
        self.assertEqual(run("en", "actWhat({}, 'ctx95', '컨텍스트 96% — 곧 자동 압축')"), "Context 96%")

    def test_ctx_without_why_falls_back_to_label(self):
        self.assertEqual(run("ko", "actWhat({}, 'ctx85')"), "컨텍스트 85%↑")

    def test_ask_wording_matches_strip(self):
        self.assertEqual(run("en", "attnWhy({k: 'ask', why: '질문 대기'})"), "Awaiting answer")


class LowRowCss(unittest.TestCase):
    def test_low_rows_not_dimmed_by_opacity(self):
        css = open(os.path.join(ROOT, "web/css/62-attention.css"), encoding="utf-8").read()
        self.assertNotIn(".atr.low{opacity", css)
        self.assertIn(".atr.low *{color:var(--nx-t2)}", css)


if __name__ == "__main__":
    unittest.main()
