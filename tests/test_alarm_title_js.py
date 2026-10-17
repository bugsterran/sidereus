"""Alarm card title (web/js/15-alarms.js cardHTML): a session-written `title` is user data and never goes through T()."""
import json
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_switch
from tests._load import js_all, js_fn
from tests._node import node_e


def card(lang, c):
    src = js_all()
    ck = re.search(r"^const CKIND = \{.*?\};", src, re.S | re.M).group(0)
    nm = re.search(r"^const ckName = [^\n]*$", src, re.M).group(0)
    js = ("let LANG = %s;\n" % json.dumps(lang) + i18n_switch(("T", "TV", "U")) + ck + "\n" + nm + "\n"
          "const esc = s => String(s), FA_ACTS = {}, faTip = () => '', faLine = () => '', faBtns = () => '',"
          " ckey = c => c.kind, isoHM = () => '';\n" + js_fn("cardHTML")
          + "\nprocess.stdout.write(JSON.stringify(cardHTML(%s, '', true)));" % json.dumps(c))
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class AlarmTitle(unittest.TestCase):
    def test_title_equal_to_dictionary_key_stays(self):
        self.assertIn("<b>Done</b>", card("ko", {"kind": "custom", "title": "Done"}))

    def test_known_kind_and_fallback_translate(self):
        self.assertIn("<b>완료</b>", card("ko", {"kind": "done", "title": "x"}))
        self.assertIn("<b>알림</b>", card("ko", {"kind": "custom"}))
        self.assertIn("<b>Alerts</b>", card("en", {"kind": "custom"}))


if __name__ == "__main__":
    unittest.main()
