"""resumeCmd (web/js/40b) quotes cwd POSIX-style and rejects non-hex sids; attention «재개 복사» and 41b use it."""
import json
import os
import re
import shutil
import subprocess
import unittest
from tests._node import node_e

WEB = os.path.join(os.path.dirname(__file__), "..", "web", "js")


def _fn(src, name):
    return re.search(r"^function " + name + r"\(.*?^}", src, re.S | re.M).group(0)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ResumeCmdTest(unittest.TestCase):
    def run_js(self, cases):
        with open(os.path.join(WEB, "40b-sessions-list.js"), encoding="utf-8") as fh:
            src = fh.read()
        js = "\n".join([_fn(src, "shq"), _fn(src, "resumeCmd"),
                        "console.log(JSON.stringify(%s.map(a => resumeCmd(a[0], a[1]))));" % json.dumps(cases)])
        r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_quoting(self):
        sid = "0a1b2c3d-4e5f-6789-abcd-ef0123456789"
        out = self.run_js([["/Users/me/my proj", sid], ["/w/it's $x `y`", sid], ["", sid],
                           ["/w", "abc; rm -rf /"], ["/w", "short"]])
        self.assertEqual(out[0], "cd '/Users/me/my proj' && claude --resume " + sid)
        self.assertEqual(out[1], "cd '/w/it'\\''s $x `y`' && claude --resume " + sid)
        self.assertEqual(out[2], "claude --resume " + sid)
        self.assertEqual(out[3:], ["", ""])

    def test_callers_share_helper(self):
        for f, pat in (("17-attention.js", "resumeCmd(cwd, sid,"), ("41b-sesrecent.js", "resumeCmd(r.cwd, r.sid,")):
            with open(os.path.join(WEB, f), encoding="utf-8") as fh:
                src = fh.read()
            self.assertIn(pat, src)
            self.assertNotIn("claude --resume ' + ", src)


if __name__ == "__main__":
    unittest.main()
