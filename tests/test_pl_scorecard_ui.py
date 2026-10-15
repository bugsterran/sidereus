"""R3: «Security n/m» row of the pipeline «Evaluation» panel (web/js/48i-pipeline-sec.js). No live files."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import ROOT, js_fn
from tests._node import node_e

STUBS = """
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const I18N = { ko: {} };
"""
SEC = {"n": 5, "m": 7, "checks": [{"id": "security-policy", "v": "fail"}, {"id": "license", "v": "pass"},
                                  {"id": "pinned-deps", "v": "na"}, {"id": "sast-gate", "v": "fail"},
                                  {"id": "<img src=x>", "v": "fail"}]}


def _node(body, lang="en"):
    with open(os.path.join(ROOT, "web", "js", "06-i18n-zx-eval.js"), encoding="utf-8") as fh:
        ko = fh.read()
    with open(os.path.join(ROOT, "web", "js", "48i-pipeline-sec.js"), encoding="utf-8") as fh:
        src = fh.read()
    tbl = src[src.index("const PLE_SEC = "):src.index("let PLE_SEC_OPEN")]
    fns = "\n".join(js_fn(f) for f in ("T", "TV", "plEvalSec"))
    code = "let LANG = %s;\n" % json.dumps(lang) + STUBS + ko + "\n" + tbl + "\n" + fns + "\n" + body
    r = subprocess.run(node_e(code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


def _sec(sec, open_=False, lang="en"):
    return _node("console.log(JSON.stringify(plEvalSec(%s, %s)));" % (json.dumps(sec), json.dumps(open_)), lang)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SecurityRow(unittest.TestCase):
    def test_r3_panel_shows_security_n_of_m(self):
        h = _sec(SEC)
        self.assertIn("Security 5/7", h)
        self.assertTrue(h.startswith("<details"))
        self.assertNotIn(" open", h.split(">")[0])
        self.assertIn(" open", _sec(SEC, True).split(">")[0])

    def test_r3_expanding_lists_only_failing_checks_with_hints(self):
        h = _sec(SEC)
        self.assertIn("Security policy", h)
        self.assertIn("Add SECURITY.md (root, .github/ or docs/)", h)
        self.assertIn("Static analysis", h)
        self.assertIn("Add a semgrep or bandit gate", h)
        self.assertNotIn("License", h)
        self.assertNotIn("Pinned dependencies", h)
        self.assertEqual(h.count("<li>"), 3)

    def test_r3_escapes_unknown_id(self):
        h = _sec(SEC)
        self.assertNotIn("<img", h)
        self.assertIn("&lt;img src=x>", h)

    def test_r3_ko_labels(self):
        h = _sec(SEC, lang="ko")
        self.assertIn("보안 5/7", h)
        self.assertIn("보안 정책", h)
        self.assertIn("SECURITY.md 를 추가하세요", h)
        self.assertNotIn("Security policy", h)

    def test_r3_no_block_when_security_missing(self):
        self.assertEqual(_sec(None), "")
        self.assertEqual(_node("console.log(JSON.stringify(plEvalSec(undefined)));"), "")

    def test_r3_all_pass_is_plain_row(self):
        h = _sec({"n": 2, "m": 2, "checks": [{"id": "license", "v": "pass"}, {"id": "secret-gate", "v": "na"}]})
        self.assertIn("Security 2/2", h)
        self.assertNotIn("<details", h)
        self.assertNotIn("<li>", h)


if __name__ == "__main__":
    unittest.main()
