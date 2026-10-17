"""web/js/17-attention.js inline row actions: «Done» acks one request only, «Later» / «Reply» render per row,
the reply box shows the recipient (never a body), Enter sends one /api/dm, Esc closes without scrolling."""
import json
import re
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

STUBS = r"""
const LS = {}; const LANG = 'ko'; function T(s){ return s; }
function esc(s){ return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function lsJson(k, d){ return k in LS ? JSON.parse(JSON.stringify(LS[k])) : d; }
function lsSetJson(k, v){ LS[k] = JSON.parse(JSON.stringify(v)); }
function apolOf(k){ return 'badge'; }
let ATTN = null, attnMenu = '', attnHtml = '', SESS = [], PRES = {}, POSTS = [], NOTES = [], REPLY = {ok: true, id: 'm1'};
const CPFB = {key: '', ok: false, until: 0, box: ''};
function tlLiveOf(){ return null; } function acctRowCls(){ return ''; } function acctTip(){ return ''; }
function agoAt(){ return '1m'; } function extTid(){ return ''; } function resumeCmd(){ return ''; }
function cpfbLabel(k, i){ return i; } function cpfbBox(){ return ''; } function attnTermSid(){ return ''; }
function termBtnHtml(s){ return '<button data-term="' + esc(s.sid || '') + '">Terminal</button>'; }
function note(s){ NOTES.push(s); } function buildAttn(){}
async function postJSON(u, b){ POSTS.push([u, b]); return REPLY; }
"""
FNS = ("attnPolOf", "attnWhy", "attnLbl", "attnLife", "attnTone", "attnAckLoad", "attnAckSave", "attnRowId", "attnAckKey",
       "attnAckParse", "attnAckHit", "attnDone", "attnSnzLoad", "attnSnzSave", "attnRows", "attnSess", "attnName",
       "attnRpTo", "attnRpHTML", "attnRpClose", "attnRpKey", "attnRowHTML", "attnSeenKeys", "attnSeen")


def run(body, lang="ko", t="function T(s){ return s; }"):
    src = js_all()
    stubs = STUBS.replace("const LANG = 'ko'; function T(s){ return s; }", "const LANG = '%s'; %s" % (lang, t))
    consts = "\n".join(re.search(r"^const " + n + r"\b.*?;$", src, re.M | re.S).group(0)
                       for n in ("ATTN_APOL", "ATTN_LIST_ONLY", "ATTN_ACK_TOL", "ATTN_LBL", "ATTN_AFTER"))
    rp = re.search(r"^let attnRp = .*?;$", src, re.M).group(0)
    rp += "\n" + re.search(r"^async function attnRpSend\(.*?^}$", src, re.M | re.S).group(0)   # js_fn skips async
    js = stubs + consts + "\n" + rp + "\n" + "\n".join(js_fn(n) for n in FNS) + "\n(async () => {\n" + body + "\n})();"
    return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


def row(sid, k="ask", since=1000):
    return {"sid": sid, "cwd": "/w/" + sid, "project": sid, "sigs": [{"k": k, "pts": 90, "since": since}]}


def sess(sid, login=True):
    return {"sid": sid, "cwd": "/w/" + sid, "plat": "cc", "mbox": "mb-" + sid, "mboxSrc": "identity" if login else "guess"}


class DoneOneRequest(unittest.TestCase):
    """R3: «Done» hides only that request; a new request from the same session shows again."""

    def test_done_then_new_request(self):
        out = run("""
          ATTN = {rows: %s}; const a = attnRows();
          const s1 = a.shown.find(x => x.id === 's1'); attnDone(s1.id, s1.key);
          const b = attnRows().shown.map(x => x.id);
          ATTN = {rows: %s}; const c = attnRows().shown.map(x => x.id);
          console.log(JSON.stringify({b, c, low: attnDone('s3', '')}));
        """ % (json.dumps([row("s1"), row("s2")]), json.dumps([row("s1", since=1900), row("s2")])))
        self.assertEqual(out["b"], ["s2"])                 # only s1 left; s2 untouched
        self.assertEqual(sorted(out["c"]), ["s1", "s2"])   # new episode of s1 shows again
        self.assertFalse(out["low"])                       # low-priority rows (key '') are never acked


class RowActions(unittest.TestCase):
    """R1: one-click actions on each row; the reply box previews the recipient only."""

    def html(self, login=True, open_=False, k="ask"):
        return run("""
          SESS = [%s]; ATTN = {rows: [%s]}; const x = attnRows().shown.concat(attnRows().low)[0];
          if(%s){ attnRp = {id: x.id, to: 'mb-s1', draft: 'secret draft', busy: false}; }
          console.log(JSON.stringify(attnRowHTML(x)));
        """ % (json.dumps(sess("s1", login)), json.dumps(row("s1", k)), "true" if open_ else "false"))

    def test_buttons(self):
        h = self.html()
        for a in ('data-aa="rp"', 'data-aa="done"', 'data-aa="later"', "data-term="):
            self.assertIn(a, h)
        self.assertNotIn("atrp", h)

    def test_not_logged_in_reply_disabled(self):
        h = self.html(login=False)
        self.assertNotIn('data-aa="rp"', h)
        self.assertIn("disabled", h)

    def test_composer_shows_recipient_never_body(self):
        h = self.html(open_=True)
        self.assertIn("mb-s1", h)
        self.assertIn('data-aa="rps"', h)
        self.assertNotIn("secret draft", h)


class ReplySend(unittest.TestCase):
    def test_enter_sends_once_and_esc_closes(self):
        out = run("""
          const ev = (key, v) => ({key, isComposing: false, target: {value: v, matches: s => s === '.atrpi'},
                                   preventDefault(){}, stopPropagation(){}});
          attnRp = {id: 's1', to: 'mb-s1', draft: '', busy: false};
          attnRpKey(ev('Enter', '  hi  '), null); await new Promise(r => setTimeout(r, 0));
          const sent = {posts: POSTS.slice(), open: attnRp.id};
          REPLY = {ok: false, error: 'x'}; attnRp = {id: 's1', to: 'mb-s1', draft: 'keep', busy: false};
          await attnRpSend(() => {}); const failKeeps = attnRp.draft;
          let focused = null;
          const btn = {focus(o){ focused = o; }};
          const el = {querySelectorAll: () => [{getAttribute: () => 's1', querySelector: () => btn}]};
          attnRpKey(ev('Escape', 'keep'), el);
          console.log(JSON.stringify({sent, failKeeps, closed: attnRp.id, focused}));
        """)
        self.assertEqual(out["sent"]["posts"], [["/api/dm", {"to": "mb-s1", "body": "hi"}]])
        self.assertEqual(out["sent"]["open"], "")
        self.assertEqual(out["failKeeps"], "keep")
        self.assertEqual(out["closed"], "")
        self.assertEqual(out["focused"], {"preventScroll": True})


class SeenBgdone(unittest.TestCase):
    """bgdone rows: «Seen» posts the row's card keys to /api/cards/read and drops the row locally; done rows untouched."""

    def test_seen_posts_keys_and_drops_row(self):
        bg = {"sid": "s1", "cwd": "/w/s1", "project": "s1",
              "sigs": [{"k": "bgdone", "pts": 10, "since": 1000, "keys": ["t1|agent|s1", "t2|agent|s1"]}]}
        dn = {"sid": "s2", "cwd": "/w/s2", "project": "s2", "sigs": [{"k": "done", "pts": 10, "since": 1000}]}
        out = run("""
          ATTN = {rows: %s}; SESS = [];
          const low = attnRows().low, h = low.map(attnRowHTML);
          const ok = attnSeen(ATTN.rows[0]), no = attnSeen(ATTN.rows.find(r => r.sid === 's2'));
          console.log(JSON.stringify({h, ok, no, posts: POSTS, left: ATTN.rows.map(r => r.sid)}));
        """ % json.dumps([bg, dn]))
        self.assertIn('data-aa="seen"', out["h"][0] if 's1' in out["h"][0] else out["h"][1])
        self.assertEqual(sum('data-aa="seen"' in x for x in out["h"]), 1)   # never on a done row
        self.assertTrue(out["ok"])
        self.assertFalse(out["no"])
        self.assertEqual(out["posts"], [["/api/cards/read", {"keys": ["t1|agent|s1", "t2|agent|s1"]}]])
        self.assertEqual(out["left"], ["s2"])


class BlockedToolName(unittest.TestCase):
    """The blocked row keeps the tool name in every language; only the fixed phrase is translated."""

    CASES = """console.log(JSON.stringify([
      attnWhy({k: 'blocked', why: 'Write waiting for approval', tool: 'Write'}),
      attnWhy({k: 'blocked', why: 'Bash waiting for approval'}),
      attnWhy({k: 'blocked', why: 'waiting for approval', tool: ''}),
      attnWhy({k: 'blocked', why: 'waiting for approval'})]));"""

    def test_en_keeps_tool_name(self):
        out = run(self.CASES, lang="en")
        self.assertEqual(out, ["Write waiting for approval", "Bash waiting for approval",
                               "Waiting for permission", "Waiting for permission"])

    def test_ko_unchanged(self):
        ko = "function T(s){ return s === 'waiting for approval' ? '승인 대기' : s; }"
        out = run(self.CASES, lang="ko", t=ko)
        self.assertEqual(out, ["Write 승인 대기", "Bash 승인 대기", "승인 대기", "승인 대기"])


if __name__ == "__main__":
    unittest.main()
