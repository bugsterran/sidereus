"""«Ask to check» on background-shell attention rows (17-attention.js): button on bgidle/bglong rows only, disabled with the
«Reply» reason when not logged in, preview posts nothing, Confirm posts one /api/dm, then «Check requested» and no re-send."""
import json
import re
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

NOW = 1_800_000_000
STUBS = r"""
const LS = {}; const LANG = 'en'; function T(s){ return s; } Date.now = () => %d * 1000;
function esc(s){ return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function lsJson(k, d){ return k in LS ? JSON.parse(JSON.stringify(LS[k])) : d; }
function lsSetJson(k, v){ LS[k] = JSON.parse(JSON.stringify(v)); }
const ALARM_TERM_KINDS = new Set(['ask', 'blocked']);
function apolOf(k){ return 'badge'; }
let ATTN = null, attnMenu = '', attnHtml = '', SESS = [], PRES = {}, POSTS = [], NOTES = [], REPLY = {ok: true, id: 'm1'};
function tlLiveOf(){ return null; } function acctRowCls(){ return ''; } function acctTip(){ return ''; }
function agoAt(t){ return Math.floor(Date.now() / 1000) - t < 60 ? 'just now' : 'earlier'; }
function extTid(){ return ''; } function resumeCmd(){ return ''; } function U(n, u){ return n + u; } function PL(n, w){ return n + ' ' + w; }
function cpfbLabel(k, i){ return i; } function cpfbBox(){ return ''; } function attnTermSid(){ return ''; }
function termBtnHtml(){ return ''; } function note(s){ NOTES.push(s); }
async function postJSON(u, b){ POSTS.push([u, b]); return REPLY; }
""" % NOW
FNS = ("mboxIn", "attnPolOf", "attnWhy", "attnLbl", "attnLife", "attnTone", "attnAckLoad", "attnAckSave", "attnRowId", "attnAckKey",
       "attnAckParse", "attnAckHit", "attnSnzLoad", "attnSnzSave", "attnRows", "attnSess", "attnName", "attnSeenKeys",
       "attnRpTo", "attnRpHTML", "attnRpClose", "attnRowHTML",
       "attnAskSig", "attnAskBody", "attnAskHTML", "attnAskLoad", "attnAskSave", "attnAskRow", "attnAskOpen", "attnAskAt")


def run(body):
    src = js_all()
    consts = "\n".join(re.search(r"^const " + n + r"\b.*?;$", src, re.M | re.S).group(0)
                       for n in ("ATTN_APOL", "ATTN_LIST_ONLY", "ATTN_ACK_TOL", "ATTN_LBL", "ATTN_AFTER", "ATTN_BG_KINDS"))
    lets = "\n".join(re.search(r"^let " + n + r" = .*?;$", src, re.M).group(0) for n in ("attnRp", "attnAsk"))
    send = js_fn("attnAskSend")
    js = STUBS + consts + "\n" + lets + "\n" + send + "\n" + "\n".join(js_fn(n) for n in FNS) + "\n(async () => {\n" + body + "\n})();"
    return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


def row(k, since=NOW - 40 * 60):
    return {"sid": "s1", "cwd": "/w/s1", "project": "s1", "sigs": [{"k": k, "pts": 30, "since": since, "why": "x"}]}


def sess(login=True):
    return {"sid": "s1", "cwd": "/w/s1", "plat": "cc", "mbox": "mb-s1", "mboxSrc": "identity" if login else "guess"}


HTML = "const html = () => { const a = attnRows(); return attnRowHTML(a.shown.concat(a.low)[0]); };\n"


class AskToCheck(unittest.TestCase):
    def html(self, k, login=True):
        return run("SESS = [%s]; ATTN = {rows: [%s]};\n%s console.log(JSON.stringify(html()));"
                   % (json.dumps(sess(login)), json.dumps(row(k)), HTML))

    def test_button_only_on_bg_rows(self):
        for k in ("bgidle", "bglong"):
            self.assertIn('data-aa="ask"', self.html(k))
        for k in ("ask", "ctx85", "done"):
            self.assertNotIn("Ask to check", self.html(k))

    def test_disabled_with_reply_reason_when_not_logged_in(self):
        h = self.html("bglong", login=False)
        self.assertNotIn('data-aa="ask"', h)
        self.assertIn('<button class=atb disabled title="Not logged into the mailbox — cannot receive">Ask to check</button>', h)

    def test_preview_confirm_once_then_mark(self):
        out = run("""
          SESS = [%s]; ATTN = {rows: [%s]};
          %s
          const r = ATTN.rows[0], opened = attnAskOpen('s1', r, SESS[0]);
          const prev = html(), postsAfterPreview = POSTS.length;
          await attnAskSend(() => {});
          const after = html(); attnHtml = ''; const again = html();
          console.log(JSON.stringify({opened, prev, postsAfterPreview, posts: POSTS, after, again, open: attnAsk.id}));
        """ % (json.dumps(sess()), json.dumps(row("bglong")), HTML))
        body = "Background task running 40 min — check whether it is still needed or stuck, and report back"
        self.assertTrue(out["opened"])
        self.assertIn("→ <b>mb-s1</b>", out["prev"])
        self.assertIn("<pre class=atpre>" + body + "</pre>", out["prev"])
        self.assertIn('data-aa="asks"', out["prev"])
        self.assertEqual(out["postsAfterPreview"], 0)
        self.assertEqual(out["posts"], [["/api/dm", {"to": "mb-s1", "body": body}]])
        self.assertEqual(out["open"], "")
        for h in (out["after"], out["again"]):
            self.assertIn("Check requested · just now", h)
            self.assertNotIn("atpre", h)

    def test_old_mark_hidden_on_new_episode(self):
        out = run("""
          SESS = [%s]; ATTN = {rows: [%s]}; LS.mbAttnAsk = {s1: {t: %d}};
          %s console.log(JSON.stringify(html()));
        """ % (json.dumps(sess()), json.dumps(row("bgidle", since=NOW - 16 * 60)), NOW - 3600, HTML))
        self.assertNotIn("Check requested", out)

    def test_body_numbers_only(self):
        out = run("console.log(JSON.stringify([attnAskBody('bgidle', 17.9), attnAskBody('bglong', 31)]));")
        self.assertEqual(out[0], "Background shell quiet 17 min — check whether it is still needed or stuck, and report back")
        self.assertTrue(out[1].startswith("Background task running 31 min"))
        for b in out:
            self.assertNotIn("Idle shells", b)
            self.assertNotIn("Long background", b)


if __name__ == "__main__":
    unittest.main()
