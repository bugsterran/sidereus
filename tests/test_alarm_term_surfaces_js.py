"""Waiting-for-me surfaces -> terminal: toast (toastAct), attention row (attnRowGo), activity pill (actGo) and
OS notification (ntfClick) call termGo(sid) for a blocked/ask session whose tab can be raised; otherwise each
keeps its old behaviour (mark read / cpGo / window focus)."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

FNS = ("termLive", "termCanFocus", "termJumpSid", "alarmTermSid", "toastAct", "attnTermSid", "attnRowGo",
       "actKey", "actPill", "actTermSid", "actGo", "ntfClick")


def run(sess, body, term_app="auto"):
    """Runs body with stubs; returns {'term': [...], 'cp': [...], 'read': [...], 'focus': n}."""
    src = (
        "const ALARM_TERM_KINDS = new Set(['ask', 'blocked']);\n"
        "let TERM_APP = " + json.dumps(term_app) + ";\n"
        "const SESS = " + json.dumps(sess) + ";\n"
        "const out = {term: [], cp: [], read: [], focus: 0};\n"
        "function termGo(sid){ out.term.push(sid); }\n"
        "function cpGo(x){ out.cp.push(x.sid); }\n"
        "function markCardsRead(ks){ out.read.push(...ks); }\n"
        "function faAct(){} function softErr(){} function actPopClose(){} function actHovHide(){}\n"
        "function attnSess(r){ return SESS.find(s => s.sid === r.sid) || null; }\n"
        "const FA_ACTS = {}, ckey = c => c.kind + '|' + c.sid;\n"
        "let actData = {pills: []};\n"
        "var window = {focus(){ out.focus++; }};\n"
        + "\n".join(js_fn(n) for n in FNS) + "\n"
        + body + "\nprocess.stdout.write(JSON.stringify(out));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


LIVE = [{"sid": "s1", "state": "idle", "term": {"app": "iterm"}}]
DONE = [dict(LIVE[0], state="done")]
NOFOCUS = [{"sid": "s1", "state": "idle", "term": {"app": "other"}}]
BODY = "{target: {closest: () => null}}"


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ToastClick(unittest.TestCase):
    def go(self, sess, kind="ask", target=BODY):
        return run(sess, "toastAct({kind: " + json.dumps(kind) + ", sid: 's1'}, " + target + ");")

    def test_ask_jumps_and_marks_read(self):
        o = self.go(LIVE)
        self.assertEqual((o["term"], o["read"]), (["s1"], ["ask|s1"]))

    def test_blocked_jumps(self):
        self.assertEqual(self.go(LIVE, "blocked")["term"], ["s1"])

    def test_fallback_marks_read_only(self):
        for sess in (DONE, NOFOCUS, []):
            o = self.go(sess)
            self.assertEqual((o["term"], o["read"]), ([], ["ask|s1"]))
        self.assertEqual(self.go(LIVE, "done")["term"], [])

    def test_button_click_does_not_jump(self):
        o = self.go(LIVE, target="{target: {closest: s => s === '[data-fread]' ? {} : null}}")
        self.assertEqual(o["term"], [])


@unittest.skipUnless(shutil.which("node"), "node not installed")
class AttentionRow(unittest.TestCase):
    def go(self, sess, ks, term_app="auto"):
        r = {"sid": "s1", "cwd": "/w", "sigs": [{"k": k} for k in ks]}
        return run(sess, "attnRowGo(" + json.dumps(r) + ", 's1', '/w');", term_app)

    def test_blocked_row_jumps(self):
        self.assertEqual(self.go(LIVE, ["blocked"]), {"term": ["s1"], "cp": [], "read": [], "focus": 0})

    def test_ask_among_others_jumps(self):
        self.assertEqual(self.go(LIVE, ["ctx85", "ask"])["term"], ["s1"])

    def test_fallback_scrolls_to_card(self):
        for sess, ks, app in ((LIVE, ["ctx95"], "auto"), (DONE, ["ask"], "auto"), (LIVE, ["ask"], "off")):
            o = self.go(sess, ks, app)
            self.assertEqual((o["term"], o["cp"]), ([], ["s1"]), (ks, app))


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ActivityPill(unittest.TestCase):
    def go(self, sess, need):
        return run(sess, "actData = {pills: [{x: SESS[0] || {sid: 's1'}, need: " + json.dumps(need) + "}]}; actGo('s1');")

    def test_need_pill_jumps(self):
        for need in ("ask", "blocked"):
            o = self.go(LIVE, need)
            self.assertEqual((o["term"], o["cp"]), (["s1"], []), need)

    def test_fallback_reveals_row(self):
        self.assertEqual(self.go(LIVE, "ctx85")["cp"], ["s1"])
        self.assertEqual(self.go(LIVE, "")["term"], [])
        self.assertEqual(self.go(NOFOCUS, "ask")["cp"], ["s1"])


@unittest.skipUnless(shutil.which("node"), "node not installed")
class OsNotification(unittest.TestCase):
    def go(self, sess, ks):
        e = {"sid": "s1", "ks": ks, "r": {"sid": "s1", "cwd": "/w"}}
        return run(sess, "ntfClick(" + json.dumps(e) + ");")

    def test_blocked_jumps_without_focusing_sidereus(self):
        self.assertEqual(self.go(LIVE, ["blocked"]), {"term": ["s1"], "cp": [], "read": [], "focus": 0})

    def test_fallback_focuses_and_opens(self):
        for sess, ks in ((LIVE, ["abort"]), (DONE, ["ask"]), (NOFOCUS, ["blocked"])):
            o = self.go(sess, ks)
            self.assertEqual((o["term"], o["cp"], o["focus"]), ([], ["s1"], 1), ks)


if __name__ == "__main__":
    unittest.main()
