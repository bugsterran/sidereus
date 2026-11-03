"""Chat tab counter (92-mainview-tabs.js rcPaint): rooms are counted, and the «Outside rooms» card is named
after the count only while it is on screen."""
import json
import subprocess
import unittest

from tests._i18n_js import i18n_switch
from tests._load import js_fn
from tests._node import node_e


def cnt(lang, cards):
    js = (i18n_switch(("T", "KE", "U", "PL"))
          + "let LANG='" + lang + "', mainView='chat', place='all', q='';\n"
          + "const CS=" + json.dumps([{"k": k, "name": k} for k in cards]) + ";\n"
          "const E={cnt:{textContent:''}}, document={getElementById:i=>E[i]};\n"
          "const feed={querySelector(){return null;}};\n"
          "function esc(s){return s;}\n"
          "function rcCards(){return CS;} function rcCardHtml(){return '';} function rcBind(){}\n"
          + js_fn("rcPaint") + "\nrcPaint();\nprocess.stdout.write(JSON.stringify(E.cnt.textContent));")
    return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


class RoomCountLabel(unittest.TestCase):
    CARDS = ["release", "dm", "docs"]

    def test_dm_shown_is_named(self):
        self.assertEqual(cnt("en", self.CARDS), "2 rooms + Outside rooms")
        self.assertEqual(cnt("ko", self.CARDS), "2개 + 방 밖 글")

    def test_no_dm_card(self):
        self.assertEqual(cnt("en", ["release"]), "1 room")


if __name__ == "__main__":
    unittest.main()
