"""Rail «Attention» count (web/js/42-activity.js actRows) equals the header chip (attnBadgeN): a session whose
attention row was marked Done or Later is not counted again from its ask/blocked/abort flags."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

FNS = ("attnRows", "attnBadgeN", "attnRowId", "attnAckKey", "attnAckParse", "attnAckHit",
       "actGone", "actNeedOf", "actRows")


ROWS = [{"sid": "s1", "cwd": "/w/a", "sigs": [{"k": "ask", "since": 100, "pts": 50}]},
        {"sid": "s2", "cwd": "/w/b", "sigs": [{"k": "blocked", "since": 200, "pts": 90}]}]


def run(ack, snz, sess, rows=None):
    src = (
        "const T = s => s, softErr = () => {}, attnTone = () => 'warn', attnWhy = () => '';\n"
        "const ALARM_TERM_KINDS = new Set(['ask', 'blocked']), ATTN_ACK_TOL = 5;\n"
        "const attnPolOf = k => k === 'done' ? 'list' : 'badge';\n"
        "const ACK = " + json.dumps(ack) + ", SNZ = " + json.dumps(snz) + ";\n"
        "const attnAckLoad = () => Object.assign({}, ACK), attnSnzLoad = () => Object.assign({}, SNZ);\n"
        "const attnAckSave = () => {}, attnSnzSave = () => {};\n"
        "const SESS = " + json.dumps(sess) + ";\n"
        "const ATTN = {rows: " + json.dumps(ROWS if rows is None else rows) + "};\n"
        + "\n".join(js_fn(n) for n in FNS) + "\n"
        "process.stdout.write(JSON.stringify({head: attnBadgeN(), rail: actRows().pills.map(p => p.x.sid || p.x.cwd)}));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


SESS = [{"sid": "s1", "cwd": "/w/a", "state": "ask"}, {"sid": "s2", "cwd": "/w/b", "state": "run", "blocked": True},
        {"sid": "s3", "cwd": "/w/c", "state": "abort"}]


@unittest.skipUnless(shutil.which("node"), "node not installed")
class RailMatchesHeader(unittest.TestCase):
    def test_nothing_acked(self):
        r = run({}, {}, SESS)
        self.assertEqual(sorted(r["rail"]), ["s1", "s2", "s3"])
        self.assertEqual(r["head"], 2)   # s3 has no attention row: rail-only abort, unchanged

    def test_acked_ask_drops_from_rail(self):
        r = run({"s1": {"s": "ask", "t": 100}}, {}, SESS)
        self.assertEqual(r["head"], 1)
        self.assertNotIn("s1", r["rail"])
        self.assertEqual(len([s for s in r["rail"] if s != "s3"]), r["head"])
        r = run({"s1": {"s": "ask", "t": 100}}, {}, SESS[:2])
        self.assertEqual(len(r["rail"]), r["head"])

    def test_snoozed_blocked_drops_from_rail(self):
        r = run({}, {"s2|blocked": "clear"}, SESS)
        self.assertEqual(r["head"], 1)
        self.assertNotIn("s2", r["rail"])
        self.assertIn("s1", r["rail"])


def asked_again(since):
    return [dict(ROWS[0], sigs=[{"k": "ask", "since": since, "pts": 50}]), ROWS[1]]


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ReAskShowsAgain(unittest.TestCase):
    def test_later_then_new_question(self):
        snz = {"s1|ask": {"u": "clear", "t": 100}}
        r = run({}, snz, SESS[:2], asked_again(100))
        self.assertEqual((r["head"], r["rail"]), (1, ["s2"]))
        r = run({}, snz, SESS[:2], asked_again(400))
        self.assertEqual(r["head"], 2)
        self.assertEqual(sorted(r["rail"]), ["s1", "s2"])

    def test_legacy_snooze_without_since_still_hides(self):
        r = run({}, {"s1|ask": "clear"}, SESS[:2], asked_again(400))
        self.assertEqual((r["head"], r["rail"]), (1, ["s2"]))

    def test_ack_then_new_question_under_higher_top(self):
        def rows(since):
            return [{"sid": "s1", "cwd": "/w/a", "sigs": [{"k": "ctx95", "since": 50, "pts": 95},
                                                           {"k": "ask", "since": since, "pts": 50}]}]
        ack = {"s1": {"s": "ask,ctx95", "t": 50, "a": 100}}
        sess = SESS[:1]
        self.assertEqual(run(ack, {}, sess, rows(100)), {"head": 0, "rail": []})
        self.assertEqual(run(ack, {}, sess, rows(400)), {"head": 1, "rail": ["s1"]})
        self.assertEqual(run({"s1": {"s": "ask,ctx95", "t": 50}}, {}, sess, rows(400))["head"], 0)   # legacy ack: as before

    def test_ack_then_new_question_top_ask(self):
        ack = {"s1": {"s": "ask", "t": 100}}
        r = run(ack, {}, SESS[:2], asked_again(400))
        self.assertEqual(r["head"], 2)
        self.assertEqual(sorted(r["rail"]), ["s1", "s2"])

    def test_sidless_ack_keeps_other_sessions_in_same_cwd(self):
        rows = [{"sid": "", "cwd": "/w/a", "sigs": [{"k": "ask", "since": 100, "pts": 50}]},
                {"sid": "s7", "cwd": "/w/a", "sigs": [{"k": "ask", "since": 150, "pts": 50}]}]
        sess = [{"sid": "", "cwd": "/w/a", "state": "ask"}, {"sid": "s5", "cwd": "/w/a", "state": "run", "blocked": True},
                {"sid": "s7", "cwd": "/w/a", "state": "ask"}]
        r = run({"cwd:/w/a": {"s": "ask", "t": 100}}, {}, sess, rows)
        self.assertEqual(r["head"], 1)
        self.assertEqual(sorted(r["rail"]), ["s5", "s7"])


if __name__ == "__main__":
    unittest.main()
