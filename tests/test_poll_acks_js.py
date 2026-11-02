"""web/js/95-poll.js pollAcksTake/pollAcksQ: a state body without `acks` keeps ACK, one with `acks` replaces it,
and the poll URL carries acksV only after the first state and while connected."""
import json
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def run(steps):
    """steps: [["take", body] | ["q", {stateIn, fails}]] -> list of {ack, ackv} / query strings."""
    js = ("let ACK = {old: 1}, ACKV = '', STATE_IN = false; const CONN = {fails: 0};\n"
          + js_fn("pollAcksQ") + "\n" + js_fn("pollAcksTake") + "\n"
          "const out = []; for(const [k, v] of %s){\n"
          "  if(k === 'take'){ pollAcksTake(v); out.push({ack: ACK, ackv: ACKV}); }\n"
          "  else { STATE_IN = v.stateIn; CONN.fails = v.fails; out.push(pollAcksQ()); } }\n"
          "console.log(JSON.stringify(out));" % json.dumps(steps))
    return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


class PollAcks(unittest.TestCase):
    def test_body_without_acks_keeps_ack_and_with_acks_replaces(self):
        out = run([["take", {"acks": {"m1": 1}, "acksV": "1-2-3"}],
                   ["take", {"acksV": "1-2-3"}],
                   ["take", {"acks": {"m2": 2}, "acksV": "4-5-6"}]])
        self.assertEqual(out[0], {"ack": {"m1": 1}, "ackv": "1-2-3"})
        self.assertEqual(out[1], {"ack": {"m1": 1}, "ackv": "1-2-3"})
        self.assertEqual(out[2], {"ack": {"m2": 2}, "ackv": "4-5-6"})

    def test_omitted_for_another_version_drops_ours(self):
        out = run([["take", {"acks": {"m1": 1}, "acksV": "1-2-3"}], ["take", {"acksV": "9-9-9"}],
                   ["q", {"stateIn": True, "fails": 0}]])
        self.assertEqual(out[1], {"ack": {"m1": 1}, "ackv": ""})
        self.assertEqual(out[2], "")

    def test_url_carries_acks_v_only_after_first_state_and_while_up(self):
        out = run([["q", {"stateIn": False, "fails": 0}],
                   ["take", {"acks": {}, "acksV": "1-2-3"}],
                   ["q", {"stateIn": False, "fails": 0}],
                   ["q", {"stateIn": True, "fails": 0}],
                   ["q", {"stateIn": True, "fails": 2}]])
        self.assertEqual([out[0], out[2], out[3], out[4]], ["", "", "&acksV=1-2-3", ""])

    def test_no_version_from_server_never_sends_one(self):
        out = run([["take", {"acks": {"m1": 1}}], ["q", {"stateIn": True, "fails": 0}]])   # demo world / old server
        self.assertEqual(out[1], "")


if __name__ == "__main__":
    unittest.main()
