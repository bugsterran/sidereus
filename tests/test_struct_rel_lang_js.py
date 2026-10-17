"""Rel code popup language (web/js/81 strRelLang): the node's own lang (a .h is cpp or c per file) beats the extension guess."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import jconst
from tests._node import node_e


@unittest.skipUnless(shutil.which("node"), "node not installed")
class RelLang(unittest.TestCase):
    def test_node_lang_wins(self):
        src = jconst("STR_TEXT_LANG") + "\n" + js_fn("strPairLang") + "\n" + js_fn("strRelLang") + "\n" + """
process.stdout.write(JSON.stringify([strRelLang('inc/async.h', 'cpp'), strRelLang('inc/async.h', ''), strRelLang('a.c', 'c'),
  strRelLang('a/B.cs', 'cs'), strRelLang('a/B.java', 'java')]));
"""
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        self.assertEqual(json.loads(r.stdout), [{"hl": "c", "label": "cpp"}, {"hl": "c", "label": "c"}, {"hl": "c", "label": "c"},
                                                {"hl": "java", "label": "cs"}, {"hl": "java", "label": "java"}])


if __name__ == "__main__":
    unittest.main()
