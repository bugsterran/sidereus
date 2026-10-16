"""Double-send guards: chat box send() (10-feed.js) and work-popup wkcPost() (36-wkcompose.js) post once per
in-flight request; the chat room counter (92-mainview-tabs.js rcPaint) counts real rooms only, singular/plural in en."""
import json
import re
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e


def async_fn(name):
    # js_fn only matches plain `function`; these two are top-level `async function`.
    return re.compile(r"^async function " + name + r"\(.*?^}", re.S | re.M).search(js_all()).group(0)


LANG_FNS = js_fn("U") + "\n" + js_fn("PL") + "\n" + js_fn("KE") + "\n"
UNIT = "const UNIT_KO = {' rooms':'개'};\n"


def run(js):
    return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True).stdout)


def el():
    return "{value:'hi', style:{}, focus(){}, disabled:false, hidden:true, innerHTML:''}"


class ChatSend(unittest.TestCase):
    def test_double_enter_posts_once(self):
        js = ("let replyTo=null, MSGS=[], place='room:a', calls=0;\n"
              "const E={cbox:" + el() + ", csend:" + el() + "};\n"
              "const document={getElementById:i=>E[i]};\n"
              "function T(s){return s;} function note(){} function setReply(){} async function poll(){} function ctoPaint(){}\n"
              "function chatTarget(){return {room:'a'};} function rcOpen(){}\n"
              "function postJSON(){calls++; return new Promise(r=>setTimeout(()=>r({ok:true}),20));}\n"
              + async_fn("send") + "\n"
              "Promise.all([send(), send()]).then(()=>{ E.cbox.value='again'; return send(); })"
              ".then(()=>process.stdout.write(JSON.stringify(calls)));")
        self.assertEqual(run(js), 2)   # the two quick ones collapse to one; a later send still goes


class WorkPopupSend(unittest.TestCase):
    def test_double_confirm_posts_once(self):
        js = ("let wkcSentAt=0, wkcAsk={to:'s1', body:'hi'}, wkcBusy=false, calls=0;\n"
              "const E={wkcsend:" + el() + ", wkcbox:" + el() + ", wkcq:" + el() + "};\n"
              "const document={getElementById:i=>E[i]};\n"
              "function T(s){return s;} function note(){} async function poll(){} function wkcPaint(){}\n"
              "function postJSON(){calls++; return new Promise(r=>setTimeout(()=>r({ok:true}),20));}\n"
              + async_fn("wkcPost") + "\n"
              "Promise.all([wkcPost('s1','hi'), wkcPost('s1','hi')]).then(()=>wkcPost('s1','x'))"
              ".then(()=>process.stdout.write(JSON.stringify([calls, wkcBusy])));")
        self.assertEqual(run(js), [2, False])


class RoomCount(unittest.TestCase):
    def cnt(self, lang, kinds):
        js = ("let LANG='" + lang + "', mainView='chat', place='all', q='', rcEdit=null, rcTag='';\n" + UNIT + LANG_FNS
              + "const CS=" + json.dumps([{"k": k, "name": k, "tags": []} for k in kinds]) + ";\n"
              "const E={cnt:{textContent:''}}, document={getElementById:i=>E[i]};\n"
              "const feed={querySelector(){return null;}};\n"
              "function T(s){return s;} function esc(s){return s;} function raHold(){return false;}\n"
              "function rcCards(){return CS;} function raBarHtml(){return '';} function raToolHtml(){return '';}\n"
              "function raBoxHtml(){return '';} function raCardHtml(){return '';} function rcBind(){}\n"
              + js_fn("rcPaint") + "\nrcPaint();\nprocess.stdout.write(JSON.stringify(E.cnt.textContent));")
        return run(js)

    def test_outside_rooms_card_is_not_counted(self):
        self.assertEqual(self.cnt("en", ["dm"]), "0 rooms + Outside rooms")
        self.assertEqual(self.cnt("en", ["dm", "room"]), "1 room + Outside rooms")
        self.assertEqual(self.cnt("en", ["room", "dev", "dm"]), "2 rooms + Outside rooms")
        self.assertEqual(self.cnt("en", ["room", "dev"]), "2 rooms")
        self.assertEqual(self.cnt("ko", ["room"]), "1개")


if __name__ == "__main__":
    unittest.main()
