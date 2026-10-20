"""Room card member line (92-mainview-tabs.js rcCardHtml · rcWho): a member matched to a live session gets that
session's platform logo; an id with no session gets none (aiLogo alone would guess Claude)."""
import json
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def card(who, sess):
    js = ("const SESS=" + json.dumps(sess) + ", rcEdit=null;\n"
          "function esc(s){return String(s).replace(/</g,'&lt;');} function T(s){return s;}\n"
          "function aiLogo(p){return '<i class=\"ailg ailg-'+p+'\"></i>';}\n"
          "function rcLabel(c){return c.name;} function rcAgo(){return '';} function rcChip(t){return t;}\n"
          + js_fn("rcPlat") + "\n" + js_fn("rcWho") + "\n" + js_fn("rcCardHtml") + "\n"
          "const h=rcCardHtml({k:'room:r',name:'r',who:" + json.dumps(who) + ",tags:[],n:1,last:0,un:0});\n"
          "process.stdout.write(JSON.stringify(h.match(/<div class=rcwho[^>]*>(.*?)<\\/div>/)[1]));")
    return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


class RoomMemberLogo(unittest.TestCase):
    def test_codex_member_gets_logo_unknown_none(self):
        out = card(["bob-x", "ghost"], [{"mbox": "bob-x", "plat": "cx"}])
        self.assertIn('<i class="ailg ailg-cx"></i>bob-x', out)
        self.assertEqual(out.count("ailg"), 2)   # one logo element, for bob-x only
        self.assertTrue(out.endswith(", ghost"))

    def test_session_without_plat_is_claude(self):
        self.assertIn("ailg-cc", card(["amy"], [{"mbox": "amy"}]))

    def test_name_escaped(self):
        self.assertIn("&lt;b>", card(["<b>"], []))


if __name__ == "__main__":
    unittest.main()
