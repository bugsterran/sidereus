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


def run(ack, snz, sess):
    src = (
        "const T = s => s, softErr = () => {}, attnTone = () => 'warn', attnWhy = () => '';\n"
        "const ALARM_TERM_KINDS = new Set(['ask', 'blocked']), ATTN_ACK_TOL = 5;\n"
        "const attnPolOf = k => k === 'done' ? 'list' : 'badge';\n"
        "const ACK = " + json.dumps(ack) + ", SNZ = " + json.dumps(snz) + ";\n"
        "const attnAckLoad = () => Object.assign({}, ACK), attnSnzLoad = () => Object.assign({}, SNZ);\n"
        "const attnAckSave = () => {}, attnSnzSave = () => {};\n"
        "const SESS = " + json.dumps(sess) + ";\n"
        "const ATTN = {rows: [{sid: 's1', cwd: '/w/a', sigs: [{k: 'ask', since: 100, pts: 50}]},"
        " {sid: 's2', cwd: '/w/b', sigs: [{k: 'blocked', since: 200, pts: 90}]}]};\n"
        + "\n".join(js_fn(n) for n in FNS) + "\n"
        "process.stdout.write(JSON.stringify({head: attnBadgeN(), rail: actRows().pills.map(p => p.x.sid)}));")
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


if __name__ == "__main__":
    unittest.main()
