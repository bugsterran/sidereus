"""A Claude session and a Gemini session in the same folder must stay two sessions (2026-09-24 user:
«클로드 랑 제미나이 같은 프로젝트면 같이 해석하는것같은데»). Python paths directly, JS paths through node."""
import json
import os
import re
import shutil
import subprocess
import time
import unittest
from datetime import datetime

from tests._i18n_js import i18n_prelude
from tests._load import sidereus, js_fn
from tests._node import node_e

att = sidereus("attention")
work = sidereus("work")
JS = os.path.join(os.path.dirname(__file__), "..", "web", "js")


def _fn(fname, name):
    # fname is kept for readability only; lookup is by name so JS file splits don't break this test.
    return js_fn(name)


def _node(sess, body, fns):
    js = "\n".join(["let SESS = " + json.dumps(sess) + ";"] + [_fn(f, n) for f, n in fns] + [body])
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


CC = {"sid": "cc-1", "cwd": "/w/p", "plat": "cc", "state": "wait", "mbox": "me-p", "repos": ["/w/p", "/w/lib"]}
GM = {"sid": "gm-1", "cwd": "/w/p", "plat": "gm", "state": "think", "mbox": "", "repos": []}


class AttentionOwner(unittest.TestCase):
    def setUp(self):
        self._cf, att._conflicts = att._conflicts, (lambda rows, now: [])
        att._TF.update(at=0.0, idx={})

    def tearDown(self):
        att._conflicts = self._cf

    def test_claude_card_not_given_to_fresher_gemini_row(self):
        c = {"kind": "fcut", "cwd": "/w/p", "at": datetime.fromtimestamp(time.time() - 60).isoformat()}
        rows = [dict(CC, ageSec=500), dict(GM, ageSec=5)]
        out = att.attention(rows, [c], read="", read_ids=[])["rows"]
        self.assertEqual([r["sid"] for r in out], ["cc-1"])


class AllowedCwds(unittest.TestCase):
    def setUp(self):
        self._s, self._a = work.sessions_rows, list(work._ALLOW)

    def tearDown(self):
        work.sessions_rows = self._s
        work._ALLOW[:] = self._a

    def test_gemini_row_does_not_replace_claude_row(self):
        for order in ([CC, GM], [GM, CC]):
            work.sessions_rows = lambda o=order, **k: [dict(x) for x in o]
            work._ALLOW[:] = [0, {}]
            self.assertEqual(work._allowed_cwds()["/w/p"]["sid"], "cc-1")

    def test_gemini_only_folder_still_allowed(self):
        work.sessions_rows = lambda **k: [dict(GM)]
        work._ALLOW[:] = [0, {}]
        self.assertEqual(work._allowed_cwds()["/w/p"]["sid"], "gm-1")


LIVE = ("20-session-state.js", "tlLiveOf")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class JsLookups(unittest.TestCase):
    def test_timeline_gemini_child_attaches_by_parent_sid(self):
        # parent Claude sid is live at /w/p; the child's own cwd is a subdir -> still under /w/p's bucket
        head = {"sess": True, "plat": "", "cwd": "/w/p", "items": [{"sid": "cc-1", "segs": [[1, 2]], "start": 1, "end": 2}]}
        kid = {"sess": False, "plat": "gm", "cwd": "/w/p/sub", "type": "gemini -p",
               "items": [{"parent": "cc-1", "segs": [[1, 2]], "start": 1, "end": 2}]}
        gmh = {"sess": True, "plat": "gm", "cwd": "/w/p", "items": [{"segs": [[1, 2]], "start": 1, "end": 2}]}
        o = _node([CC, GM], "const r = tlSessions(" + json.dumps([head, kid, gmh]) + ", 0, 10);"
                  "console.log(JSON.stringify(r.sessOrder.map(v => [v.cwd, v.plat, !!v.head, v.kids.length])));",
                  [LIVE, ("74-timeline.js", "tlSessions")])
        self.assertIn(["/w/p", "", True, 1], o)
        self.assertIn(["/w/p", "gm", True, 0], o)
        self.assertEqual(len(o), 2)

    def test_headless_bucket_ranks_by_claude_state(self):
        # no Claude head in window, only a Gemini child: rank must use the Claude row (wait=2), not the Gemini one (think=0)
        kid = {"sess": False, "plat": "gm", "cwd": "/w/p", "type": "gemini -p",
               "items": [{"parent": "zz", "segs": [[1, 2]], "start": 1, "end": 2}]}
        o = _node([CC, GM], "const r = tlSessions(" + json.dumps([kid]) + ", 0, 10);"
                  "console.log(JSON.stringify(r.sessOrder.map(v => [v.cwd, v.plat])));",
                  [LIVE, ("74-timeline.js", "tlSessions")])
        self.assertEqual(o, [["/w/p", ""]])

    def test_worktab_claude_state_ignores_gemini(self):
        o = _node([GM, CC], "console.log(JSON.stringify(wtLive({tid: 'sess:/w/p', cwd: '/w/p'})));",
                  [LIVE, ("35b-worklog-view.js", "tidSid"),("65-worktabs.js", "wtLive")])
        self.assertFalse(o)                      # Claude is `wait`; the Gemini `think` must not leak in

    def test_branch_tid_not_split_by_gemini_sibling(self):
        o = _node([CC, GM], "console.log(JSON.stringify([brSessTid(SESS[0]), brSessTid(SESS[1])]));",
                  [("35b-worklog-view.js", "extTid"),("89-branch-worktree.js", "brSessTid")])
        self.assertEqual(o, ["sess:/w/p", "ext:gm|gm-1"])

    def test_attention_sid_row_no_cross_plat_fallback(self):
        o = _node([GM], "console.log(JSON.stringify([attnSess({sid: 'cc-gone', cwd: '/w/p'}), "
                        "attnSess({sid: '', cwd: '/w/p'})]));",
                  [LIVE, ("17-attention.js", "attnSess")])
        self.assertEqual(o, [None, None])

    def test_drawer_gemini_line_only_while_live(self):
        stub = (i18n_prelude("'ko'", ("T", "TV", "U")) + "const fmtTok = n => String(n);"
                "const AILG = {gm: ['제미나이'], cx: ['Codex(OpenAI)']}, I18N = {en: {'제미나이': 'Gemini'}};")
        o = _node([], stub + "console.log(JSON.stringify(sessGms([{plat: 'gm', model: 'm', dur: 3, done: true},"
                            " {plat: 'gm', cmd: 'gemini -p', model: 'm2', dur: 5, run: true, done: false},"
                            " {plat: 'cx', model: 'm3', dur: 7, done: false}]).map(x => x.lab)));",
                  [("20-session-state.js", "ago"), ("40-sessions.js", "platName"), ("40-sessions.js", "sessGms")])
        # label = server `cmd` (CHILD_LABEL); without it, the platform's product name — no Gemini literal in JS
        self.assertEqual(o, ["Codex · m3 · 7초 · 대기", "gemini -p · m2 · 5초 · 실행 중"])

    def test_compose_target_per_platform(self):
        stub = ("let PRES = {}, wtFocus = 0, wtPanes = [], wtabs = [{key: 'c', cwd: '/w/p', tid: 'sess:/w/p'},"
                " {key: 'g', cwd: '/w/p', tid: 'ext:gm|gm-1'}]; let wk = 'c'; const wtKeyOf = () => wk;")
        o = _node([GM, CC], stub + "const a = wkcTarget(); wk = 'g'; const b = wkcTarget();"
                  "console.log(JSON.stringify([a.row.sid, a.id, b.row.sid, b.id]));",
                  [("17-attention.js", "mboxIn"), ("36-wkcompose.js", "wkcTarget")])
        self.assertEqual(o, ["cc-1", "me-p", "gm-1", ""])


if __name__ == "__main__":
    unittest.main()
