"""web/js/17-attention.js grouping: blocked/ask rows sit in «Needs your response» on top (never folded),
every other row under «For your information» (folded past ATTN_MAX)."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

STUBS = r"""
const LS = {}; const LANG = 'en'; function T(s){ return s; }
function esc(s){ return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function lsJson(k, d){ return k in LS ? JSON.parse(JSON.stringify(LS[k])) : d; }
function lsSetJson(k, v){ LS[k] = JSON.parse(JSON.stringify(v)); }
let apolOf = k => 'badge';
const ALARM_TERM_KINDS = new Set(['ask', 'blocked']);
let ATTN = null, attnMenu = '', attnHtml = '', attnMore = false, attnLow = false, SESS = [];
let attnRp = {id: '', to: '', draft: '', busy: false};
const ACC_OTH = {};
function acctPick(){ return ''; } function acctOthHtml(){ return ''; } function acctInPick(){ return true; }
function tlLiveOf(){ return null; } function acctRowCls(){ return ''; } function acctTip(){ return ''; }
function agoAt(){ return '1m'; } function extTid(){ return ''; } function resumeCmd(){ return ''; }
function CLK(){ return '10:00'; } function hhmm(){ return '10:00'; } function U(n, u){ return n + u; } function PL(n, w){ return n + ' ' + w; }
function cpfbLabel(k, i){ return i; } function cpfbBox(){ return ''; } function attnTermSid(){ return ''; }
function termBtnHtml(){ return ''; } function attnRpTo(){ return {id: ''}; } function attnRpHTML(){ return ''; }
const EL = {innerHTML: '', querySelector(){ return null; }, contains(){ return false; }};
const document = {getElementById(){ return EL; }, activeElement: null};
"""
FNS = ("attnPolOf", "attnWhy", "attnLbl", "attnLife", "attnTone", "attnAckLoad", "attnAckSave", "attnRowId", "attnAckKey",
       "attnAckParse", "attnAckHit", "attnDone", "attnSnzLoad", "attnSnzSave", "attnRows", "attnBadgeN", "attnSess",
       "attnName", "attnSeenKeys", "attnRowHTML", "buildAttn")


def run(rows, body="", more=False):
    src = js_all()
    consts = "\n".join(re.search(r"^const " + n + r"\b.*?;$", src, re.M | re.S).group(0)
                       for n in ("ATTN_MAX", "ATTN_APOL", "ATTN_LIST_ONLY", "ATTN_ACK_TOL", "ATTN_LBL", "ATTN_AFTER"))
    js = (STUBS + consts + "\n" + "\n".join(js_fn(n) for n in FNS) + "\n"
          + "ATTN = {rows: " + json.dumps(rows) + "}; attnMore = " + json.dumps(more) + ";\n" + body + "\n"
          + "buildAttn(); const a = attnRows();\n"
          + "process.stdout.write(JSON.stringify({h: EL.innerHTML, badge: attnBadgeN(), shown: a.shown.length,"
          + " resp: a.resp.map(x => x.id), info: a.info.map(x => x.id)}));")
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def row(sid, *sigs):
    return {"sid": sid, "cwd": "/w/" + sid, "project": sid,
            "sigs": [{"k": k, "pts": p, "since": 1000} for k, p in sigs]}


def order(h):
    """Header kinds and row ids in render order."""
    return re.findall(r'class="ath (resp|fyi)"|data-aid="([^"]+)"', h)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class AttentionGroups(unittest.TestCase):
    def test_R1_groups_and_order(self):
        o = run([row("f1", ("ctx95", 70)), row("b1", ("blocked", 95)), row("a1", ("ask", 50))])
        seq = [a or b for a, b in order(o["h"])]
        self.assertEqual(seq, ["resp", "b1", "a1", "fyi", "f1"])
        self.assertIn("Needs your response", o["h"])
        self.assertIn("For your information", o["h"])

    def test_R1_demoted_ask_is_not_response(self):
        demote = "apolOf = k => k === 'ask' ? 'list' : 'badge';"
        o = run([row("a1", ("ask", 50))], body=demote + " attnLow = true;")   # open the low fold so the row renders
        self.assertIn('data-aid="a1"', o["h"])
        self.assertNotIn("atr resp", o["h"])
        self.assertNotIn('class="ath resp"', o["h"])
        o = run([row("m1", ("fail", 60), ("ask", 50))], body=demote)
        self.assertEqual((o["resp"], o["info"]), ([], ["m1"]))
        self.assertNotIn('class="ath resp"', o["h"])

    def test_R2_mixed_row_once(self):
        o = run([row("m1", ("fail", 60), ("ask", 50)), row("f1", ("ctx95", 70))])
        self.assertEqual(o["h"].count('data-aid="m1"'), 1)
        self.assertEqual((o["resp"], o["info"]), (["m1"], ["f1"]))
        seq = [a or b for a, b in order(o["h"])]
        self.assertLess(seq.index("m1"), seq.index("fyi"))

    def test_R3_mark_and_sort(self):
        o = run([row("f1", ("fail", 60)), row("a1", ("ask", 50))])
        self.assertEqual(o["resp"], ["a1"])
        self.assertRegex(o["h"], r'class="atr resp" data-akey="[^"]*" data-aid="a1"')
        self.assertNotRegex(o["h"], r'class="atr resp"[^>]*data-aid="f1"')
        self.assertIn('<div class="ath resp">Needs your response <b>1</b>', o["h"])
        seq = [a or b for a, b in order(o["h"])]
        self.assertLess(seq.index("a1"), seq.index("f1"))

    def test_R4_header_hidden_and_fold(self):
        o = run([row("f%d" % i, ("ctx95", 70)) for i in range(7)])
        self.assertNotIn('class="ath resp"', o["h"])
        self.assertEqual(o["h"].count('class="atr'), 5)
        self.assertIn("+2 more", o["h"])
        o = run([row("a%d" % i, ("ask", 50)) for i in range(7)])
        self.assertEqual(o["h"].count('class="atr resp'), 7)
        self.assertNotIn("more", o["h"])
        self.assertNotIn('class="ath fyi"', o["h"])

    def test_R4_acked_resp_leaves_no_header(self):
        o = run([row("a1", ("ask", 50)), row("f1", ("ctx95", 70))],
                body="const x = attnRows().resp[0]; attnDone(x.id, x.key);")
        self.assertNotIn('class="ath resp"', o["h"])
        self.assertIn('class="ath fyi"', o["h"])
        self.assertNotIn('data-aid="a1"', o["h"])

    def test_assumption_badge_counts_both(self):
        o = run([row("a1", ("ask", 50)), row("b1", ("blocked", 95)), row("f1", ("ctx95", 70)), row("m1", ("mailidle", 40))])
        self.assertEqual((o["badge"], o["shown"]), (4, 4))
        self.assertIn("m1", o["info"])


if __name__ == "__main__":
    unittest.main()
