"""Alarm card click -> terminal: alarmTermClick (web/js/15-alarms.js) calls termGo(sid) for an ask/blocked card
whose session is live and focusable, and does nothing otherwise (95-poll's read-marking stays the fallback)."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def run(card, sess, term_app="auto", group=False, target_sel=None):
    """Returns the sids termGo was called with after one click on the card."""
    src = (
        "const ALARM_TERM_KINDS = new Set(['ask', 'blocked']);\n"
        "let TERM_APP = " + json.dumps(term_app) + ";\n"
        "const calls = [];\n"
        "function termGo(sid){ calls.push(sid); }\n"
        "const ckey = c => c.at + '|' + c.kind + '|' + c.project;\n"
        "const CARD = " + json.dumps(card) + ";\n"
        "const CARDS = [CARD], SESS = " + json.dumps(sess) + ";\n"
        "const AGROUPS = [{items: [CARD, {at: 'old', kind: 'ask', project: 'p', sid: 'other'}]}];\n"
        "const GROUP = " + json.dumps(group) + ", SEL = " + json.dumps(target_sel) + ";\n"
        "const el = {hasAttribute: a => a === 'data-gi' && GROUP,"
        " getAttribute: a => a === 'data-gi' ? '0' : ckey(CARD)};\n"
        "const target = {closest: s => (SEL && s.indexOf(SEL) >= 0) ? {} : (s === '.card[data-ck]' ? el : null)};\n"
        + js_fn("termLive") + "\n" + js_fn("termCanFocus") + "\n"
        + js_fn("termJumpSid") + "\n" + js_fn("alarmTermSid") + "\n" + js_fn("alarmTermClick") + "\n"
        "alarmTermClick({target});\n"
        "process.stdout.write(JSON.stringify(calls));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


ASK = {"at": "2026-10-13T10:00:00", "kind": "ask", "project": "p", "sid": "s1"}
LIVE = [{"sid": "s1", "state": "idle", "term": {"app": "iterm"}}]


@unittest.skipUnless(shutil.which("node"), "node not installed")
class AlarmTermClick(unittest.TestCase):
    def test_ask_live_focusable_calls_termgo(self):
        self.assertEqual(run(ASK, LIVE), ["s1"])

    def test_blocked_kind_also_jumps(self):
        self.assertEqual(run(dict(ASK, kind="blocked"), LIVE), ["s1"])

    def test_group_uses_newest_member(self):
        self.assertEqual(run(ASK, LIVE, group=True), ["s1"])

    def test_fallback_when_session_done(self):
        self.assertEqual(run(ASK, [dict(LIVE[0], state="done")]), [])

    def test_fallback_when_not_focusable(self):
        self.assertEqual(run(ASK, [{"sid": "s1", "state": "idle", "term": {"app": "other"}}]), [])
        self.assertEqual(run(ASK, LIVE, term_app="off"), [])

    def test_fallback_when_no_session_or_sid(self):
        self.assertEqual(run(ASK, []), [])
        self.assertEqual(run(dict(ASK, sid=""), LIVE), [])

    def test_other_kinds_untouched(self):
        for k in ("wait", "done", "fcut", "agent"):
            self.assertEqual(run(dict(ASK, kind=k), LIVE), [], k)

    def test_buttons_do_not_jump(self):
        self.assertEqual(run(ASK, LIVE, target_sel="[data-gx]"), [])


if __name__ == "__main__":
    unittest.main()
