"""Work-popup compose (36-wkcompose.js): no DM thread list, one recipient line as the send preview, and after a send
only that message's status chips (never a body)."""
import json
import re
import subprocess
import unittest
from pathlib import Path

from tests._load import js_all, js_fn
from tests._node import node_e


def run(js):
    return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


def async_fn(name):
    return re.compile(r"^async function " + name + r"\(.*?^}", re.S | re.M).search(js_all()).group(0)


def harness(after, agent="false", watch="true", turn="false"):
    # Target s1 is logged in and watched; an older DM to it (body «old») sits in MSGS.
    return ("let ISWP=true, wkcAsk=null, wkcBusy=false, wkcHtml='', wkcLast=null, wkcSentAt=0;\n"
            "function mk(){return {hidden:true, disabled:false, innerHTML:'', textContent:'', placeholder:'', value:'',"
            " style:{}, focus(){}, querySelector(){return {focus(){}};}};}\n"
            "const E={wkc:mk(), wkch:mk(), wkcbox:mk(), wkcsend:mk(), wkcq:mk()};\n"
            "const document={getElementById:i=>E[i]};\n"
            "const MINE=['me'], ACK={}, CUR={}, PRES={};\n"
            "const MSGS=[{id:'a', mine:true, to:'s1', t:1, body:'old'}];\n"
            "function T(s){return s;} function esc(s){return String(s);} function note(){}\n"
            "async function poll(){ MSGS.push({id:'n1', mine:true, to:'s1', t:5, body:'secret'},"
            " {id:'r1', from:'s1', to:'me', t:6, replyTo:'n1', body:'answer'}); }\n"
            "function postJSON(){return Promise.resolve({ok:true, id:'n1', to:'s1'});}\n"
            "function wkcTarget(){return {id:'s1', login:true, watch:" + watch + ", turn:" + turn + ", blocked:false, agent:" + agent + "};}\n"
            + "\n".join(js_fn(n) for n in ("wkcReplies", "wkcStage", "wkcStat", "wkcPaint", "wkcCancel", "wkcSend")) + "\n"
            + async_fn("wkcPost") + "\n"
            "Promise.resolve(wkcPaint()).then(()=>" + after + ").then(()=>process.stdout.write(JSON.stringify("
            "{h:E.wkch.innerHTML, boxOff:E.wkcbox.disabled, sendOff:E.wkcsend.disabled, q:E.wkcq.innerHTML, ask:wkcAsk, last:wkcLast})));")


class WorkCompose(unittest.TestCase):
    def test_thread_list_is_gone(self):
        html = (Path(__file__).resolve().parent.parent / "web" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("id=wkcl", html)
        self.assertNotIn("wkcl", js_all())
        self.assertIn("<div class=wkch id=wkch></div><div class=wkcq id=wkcq hidden></div><div class=wkcr>", html)

    def test_recipient_line_before_any_send(self):
        r = run(harness("null", agent="true"))
        self.assertIn("→ <b>s1</b>", r["h"])
        self.assertIn("(subagent's parent session)", r["h"])
        self.assertIn("Mailbox watch", r["h"])
        self.assertNotIn("wkcst", r["h"])          # nothing shown before a send from this popup
        self.assertNotIn("old", r["h"])
        self.assertEqual([r["boxOff"], r["sendOff"]], [False, False])

    def test_status_chips_after_send_without_body(self):
        r = run(harness("wkcPost('s1','secret')"))
        self.assertIn("<span class=wkcst>", r["h"])
        self.assertIn('<i class="wkcs on cur">Reply</i>', r["h"])
        self.assertNotIn("secret", r["h"])
        self.assertNotIn("answer", r["h"])
        self.assertIn("→ <b>s1</b>", r["h"])

    def test_codex_turn_end_status_and_no_confirm(self):
        r = run(harness("(E.wkcbox.value='hi', wkcSend())", watch="false", turn="true"))
        self.assertIn("Delivered when its next turn ends · if idle at the prompt, after the next input", r["h"])
        self.assertNotIn("No mailbox watch", r["h"])
        self.assertEqual([r["q"], r["ask"], r["last"]], ["", None, {"id": "n1", "to": "s1"}])

    def test_no_watch_claude_still_confirms(self):
        r = run(harness("(E.wkcbox.value='hi', wkcSend())", watch="false"))
        self.assertIn("No mailbox watch", r["h"])
        self.assertIn("Send anyway?", r["q"])
        self.assertIsNone(r["last"])


if __name__ == "__main__":
    unittest.main()
