"""«Request a red check» (48m): preview with recipient + exact body, send only on confirm, disabled without a logged-in session.
Pure functions under node with stubs; no live files, no network."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

STUBS = """
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s;
let PLS = { proj: '/p' }, POSTS = [], NOTES = [], CANDS = [];
const EV = { ok: true, sugg: [{ code: 'redcheck', stage: '검증', cmd: 'sidereus redcheck --pipeline ci --stage 검증 --repo /p' }] };
function plCur(){ return { name: 'ci' }; } function plEvalOf(){ return EV; } function plEvalCands(){ return CANDS; }
function plEvalSgList(ev){ return ev.sugg; } function plPaint(){} function hhmm(){ return '10:00'; } function note(m){ NOTES.push(m); }
function archChkCandLabel(c){ return [c.proj, c.sid, c.id].filter(Boolean).join(' · '); }
async function postJSON(u, b){ POSTS.push([u, b]); return { ok: true }; }
let SCROLLS = [];
const document = { querySelector: q => ({ scrollIntoView: o => SCROLLS.push([q, o]) }) };
"""


def _run(body):
    src = js_all()
    decl = re.search(r"^let PLRR = .*$", src, re.M).group(0) + "\n" + re.search(r"^const PLRR_OFF = .*$", src, re.M).group(0)
    send = re.search(r"^async function plRedReqSend\([\s\S]*?^}$", src, re.M).group(0)
    code = STUBS + decl + "\n" + "\n".join(js_fn(n) for n in ("plRedReqState", "plRedReqBody", "plRedReqBtn", "plRedReqHtml", "plRedReqCmd", "plRedReqReveal")) \
        + "\n" + send + "\n(async () => {" + body + "})();"
    r = subprocess.run(node_e(code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


LIVE = "CANDS = [{sid: 's1', id: 'agent-1', login: true, proj: 'p', ran: true}];"


@unittest.skipUnless(shutil.which("node"), "node not installed")
class RedReq(unittest.TestCase):
    def test_r5_disabled_without_logged_in_session(self):
        r = _run("const a = plRedReqBtn('검증', []); const b = plRedReqBtn('검증', [{sid: 's', login: false}]);"
                 "const c = plRedReqBtn('검증', [{sid: 's', login: true}]); console.log(JSON.stringify([a, b, c]));")
        a, b, c = r
        for h in (a, b):
            self.assertIn(" disabled", h)
            self.assertIn("Open a Claude Code session in this project and log in to the mailbox to request it", h)
        self.assertNotIn("disabled", c)
        self.assertIn('data-plrrq="검증"', c)

    def test_r3_preview_then_send_on_confirm_only(self):
        r = _run(LIVE + "const S = plRedReqState(); S.stage = '검증'; S.sid = 's1';"
                 "const pv = plRedReqHtml(S, plRedReqCmd(EV, '검증'), CANDS); const before = POSTS.length;"
                 "await plRedReqSend(); const after = plRedReqHtml(PLRR, null, CANDS);"
                 "console.log(JSON.stringify([pv, before, POSTS, NOTES, after]));")
        pv, before, posts, notes, after = r
        self.assertEqual(before, 0)                       # the preview alone sends nothing
        self.assertIn("agent-1", pv)                      # recipient shown
        self.assertIn("sidereus redcheck --pipeline ci --stage 검증 --repo /p\nTarget repository: /p", pv)
        self.assertIn("Run the command above", pv)
        self.assertIn("temporary clone", pv)
        self.assertIn("data-plrrgo", pv)
        self.assertEqual(len(posts), 1)
        url, b = posts[0]
        self.assertEqual(url, "/api/dm")
        self.assertEqual(b["plreq"], {"kind": "req", "pipeline": "redcheck", "repo": "/p", "name": "ci", "stage": "검증"})
        self.assertTrue(b["relay"])
        self.assertEqual(b["to"], "agent-1")
        self.assertTrue(b["body"].startswith("sidereus redcheck --pipeline ci --stage 검증 --repo /p\n"))
        self.assertEqual(notes, ["Red check requested → p · s1 · agent-1 · 10:00"])
        self.assertIn("Red check requested", after)
        self.assertNotIn("data-plrrgo", after)            # preview closed after sending

    def test_body_names_project_path(self):
        r = _run(LIVE + "const S = plRedReqState(); S.stage = '검증'; S.sid = 's1';"
                 "const pv = plRedReqHtml(S, 'cmd', CANDS); await plRedReqSend(); console.log(JSON.stringify([pv, POSTS]));")
        pv, posts = r
        self.assertIn("Target repository: /p", pv)
        self.assertIn("Target repository: /p", posts[0][1]["body"])

    def test_send_scrolls_sent_line_into_view(self):
        r = _run(LIVE + "const S = plRedReqState(); S.stage = '검증'; S.sid = 's1';"
                 "await plRedReqSend(); console.log(JSON.stringify(SCROLLS));")
        self.assertEqual(r, [["#plevp .plrrok", {"block": "nearest"}]])

    def test_open_scrolls_preview_into_view(self):
        src = js_all()
        click = re.search(r"if\(\(b = t\.closest\('\[data-plrrq\]'\)\)\)\{[\s\S]*?return;\n  \}", src).group(0)
        self.assertRegex(click, r"plPaint\(\); if\(S\.stage\) plRedReqReveal\('\.plrrv'\)")
        r = _run("plRedReqReveal('.plrrv'); const h = plRedReqHtml({stage: 'x', k: '/p\\nci', sid: ''}, 'c', []);"
                 "console.log(JSON.stringify([SCROLLS, h.indexOf('plrrv') >= 0]));")
        self.assertEqual(r, [[["#plevp .plrrv", {"block": "nearest"}]], True])

    def test_reveal_missing_element_is_noop(self):
        r = _run("document.querySelector = () => null; plRedReqReveal('.plrrv'); console.log(JSON.stringify(SCROLLS));")
        self.assertEqual(r, [])

    def test_guard_not_logged_in_never_posts(self):
        r = _run("CANDS = [{sid: 's1', id: 'a', login: false}]; const S = plRedReqState(); S.stage = '검증'; S.sid = 's1';"
                 "const h = plRedReqHtml(S, 'cmd', CANDS); await plRedReqSend(); console.log(JSON.stringify([h, POSTS]));")
        h, posts = r
        self.assertRegex(h, r"data-plrrgo disabled")
        self.assertEqual(posts, [])

    def test_viewer_runs_nothing(self):
        src = re.search(r"^// «Request a red check» in the 48i[\s\S]*?(?=^// «)", js_all(), re.M)
        body = js_fn("plRedReqBody")
        self.assertNotIn("fetch(", body)
        self.assertIsNotNone(src)


if __name__ == "__main__":
    unittest.main()
