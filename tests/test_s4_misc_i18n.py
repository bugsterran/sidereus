"""Feature manifest titles are English source text; session tree labels (user data) never go through T()."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANGUL = re.compile(r"[\uac00-\ud7a3\u3131-\u318e]")


class FeatureTitles(unittest.TestCase):
    def test_titles_english_with_ko_entry(self):
        d = os.path.join(ROOT, "features")
        js = os.path.join(ROOT, "web", "js")
        dic = "\n".join(open(os.path.join(js, f), encoding="utf-8").read() for f in sorted(os.listdir(js))
                        if f.endswith(".js") and ("-i18n" in f))
        for f in sorted(os.listdir(d)):
            if not f.endswith(".json"):
                continue
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                t = json.load(fh).get("title") or ""
            self.assertFalse(HANGUL.search(t), f)
            self.assertIn("'%s':" % t, dic, f)   # the ko screen keeps its Korean title via I18N.ko


@unittest.skipUnless(shutil.which("node"), "node missing")
class SessKidLab(unittest.TestCase):
    def test_user_text_unchanged(self):
        with open(os.path.join(ROOT, "web", "js", "40b-sessions-list.js"), encoding="utf-8") as fh:
            src = fh.read()
        fn = re.search(r"function sessKidLab\(s\)\{.*?\n\}\n", src, re.S).group(0)
        code = (i18n_prelude("'ko'") + fn
                + "console.log(JSON.stringify([sessKidLab('Insights'), sessKidLab('Pipelines'),"
                  " sessKidLab('Mailbox watch'), sessKidLab('Mailbox watch · me')]));")
        out = json.loads(subprocess.run(node_e(code), capture_output=True, text=True, check=True, encoding="utf-8").stdout)
        self.assertEqual(out[:2], ["Insights", "Pipelines"])   # descriptions that happen to equal a dictionary key
        self.assertNotEqual(out[2], "Mailbox watch")           # the fixed watcher label is still translated
        self.assertTrue(out[3].endswith(" · me"))


    def test_monitor_prefix(self):
        with open(os.path.join(ROOT, "web", "js", "06-i18n-zo-misc.js"), encoding="utf-8") as fh:
            src = fh.read()
        pre = "\uac10\uc2dc "   # the server's Korean Monitor prefix (sidereus/bgtasks_parse.py)
        out = {}
        for lang in ("ko", "en"):
            code = ("let LANG = '%s';\nconst I18N = {ko: {}};\n" % lang) + src + ("console.log(JSON.stringify([monLab('%sSidereus x'), monLab('Bash run'), monLab('x %s')]));" % (pre, pre))
            out[lang] = json.loads(subprocess.run(node_e(code), capture_output=True, text=True, check=True, encoding="utf-8").stdout)
        self.assertEqual(out["ko"], [pre + "Sidereus x", "Bash run", "x " + pre])   # ko screen unchanged
        self.assertEqual(out["en"], ["Monitor Sidereus x", "Bash run", "x " + pre])

if __name__ == "__main__":
    unittest.main()
