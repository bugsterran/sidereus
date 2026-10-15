"""10-feed.js receipt(): only a full ack is green (`rd ok`); a partial ack (n<total) is `rd part`."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def _receipt(acks, audience):
    js = ("const T=s=>s, esc=s=>String(s), CUR={}; let ACKSINCE=0;"
          "const ACK={m1:{ack:%s}};" % json.dumps([{"who": w} for w in acks])
          + js_fn("readersOf") + js_fn("receipt") +
          "process.stdout.write(JSON.stringify(receipt({id:'m1',from:'me',t:1,audience:%s})));" % json.dumps(audience))
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ReceiptAck(unittest.TestCase):
    def test_partial_ack_is_not_green(self):
        out = _receipt(["a", "b"], ["a", "b", "c", "d", "e"])
        self.assertIn('class="rd part"', out)
        self.assertIn("2/5", out)

    def test_full_ack_is_green(self):
        out = _receipt(["a", "b"], ["a", "b"])
        self.assertIn('class="rd ok"', out)

    def test_single_recipient_ack_is_green(self):
        self.assertIn('class="rd ok"', _receipt(["a"], ["a"]))


if __name__ == "__main__":
    unittest.main()
