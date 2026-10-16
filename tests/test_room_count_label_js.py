"""Chat tab counter (92-mainview-tabs.js rcPaint): rooms are counted, and the «Outside rooms» card is named
after the count only while it is on screen (a tag filter can hide it)."""
import json
import subprocess
import unittest

from tests._i18n_js import i18n_switch
from tests._load import js_fn
from tests._node import node_e


def cnt(lang, cards, tag=""):
    js = (i18n_switch(("T", "KE", "U", "PL"))
          + "let LANG='" + lang + "', mainView='chat', place='all', q='', rcEdit=null, rcTag=" + json.dumps(tag) + ";\n"
          + "const CS=" + json.dumps([{"k": k, "name": k, "tags": t} for k, t in cards]) + ";\n"
          "const E={cnt:{textContent:''}}, document={getElementById:i=>E[i]};\n"
          "const feed={querySelector(){return null;}};\n"
          "function esc(s){return s;} function raHold(){return false;}\n"
          "function rcCards(){return CS;} function raBarHtml(){return '';} function raToolHtml(){return '';}\n"
          "function raBoxHtml(){return '';} function raCardHtml(){return '';} function rcBind(){}\n"
          + js_fn("rcPaint") + "\nrcPaint();\nprocess.stdout.write(JSON.stringify(E.cnt.textContent));")
    return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True).stdout)


class RoomCountLabel(unittest.TestCase):
    CARDS = [("release", ["ops"]), ("dm", []), ("docs", ["ops"])]

    def test_dm_shown_is_named(self):
        self.assertEqual(cnt("en", self.CARDS), "2 rooms + Outside rooms")
        self.assertEqual(cnt("ko", self.CARDS), "2개 + 방 밖 글")

    def test_dm_hidden_by_filter(self):
        self.assertEqual(cnt("en", self.CARDS, "ops"), "2 rooms")

    def test_no_dm_card(self):
        self.assertEqual(cnt("en", [("release", [])]), "1 room")


if __name__ == "__main__":
    unittest.main()
