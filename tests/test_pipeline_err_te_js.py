"""Pipeline folder picker shows a server error through TE(): a known key is translated once, an unknown string stays as-is (escaped)."""
import json
import os
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import ROOT
from tests._node import node_e

_F = os.path.join(ROOT, "web", "js", "48f-pipeline-browse.js")
_STUB = """
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[c]);
function lsGet(k, d){ return d; } function lsSet(){}
function agoAt(t){ return 'AGO:' + t; }
const document = {addEventListener(){}, querySelector(){ return null; }, getElementById(){ return null; }};
"""


def _add(err):
    body = """
(async () => {
  plBrPaint = () => {};
  plAddGo = async () => ({ok: false, err: %s});
  PLBR = {path: '/h/p', home: '/h', parent: '', dirs: [], busy: false, recent: []};
  await plBrAdd();
  console.log(JSON.stringify({msg: PLBR.msg, html: plBrHtml(PLBR)}));
})();
""" % json.dumps(err)
    with open(_F, encoding="utf-8") as f:
        src = _STUB + i18n_prelude("'ko'", ("T", "TV", "TE", "U")) + f.read() + "\n" + body
    return json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


class PickerErr(unittest.TestCase):
    def test_known_key_translated_once(self):
        out = _add("The chosen path cannot be used")
        self.assertEqual(out["msg"], "선택한 경로를 쓸 수 없습니다")
        self.assertIn("선택한 경로를 쓸 수 없습니다", out["html"])

    def test_unknown_string_unchanged_and_escaped(self):
        out = _add("weird <x> reason")
        self.assertEqual(out["msg"], "weird <x> reason")
        self.assertIn("weird &lt;x&gt; reason", out["html"])
        self.assertNotIn("<x>", out["html"])

    def test_no_err_falls_back_to_literal(self):
        out = _add("")
        self.assertEqual(out["msg"], "추가하지 못했습니다")


if __name__ == "__main__":
    unittest.main()
