"""«Pipelines» tab (web/js/48-pipeline.js plBody): a 400 «not an allowed project» says how to get in (run a Claude session
there once), in English and Korean; other failures keep «Could not read the pipelines». Pure function under node; no live files."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import ROOT, js_fn
from tests._node import node_e

STUBS = """
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const I18N = { ko: {} };
"""


def _run(status, lang="en", msg=""):
    with open(os.path.join(ROOT, "web", "js", "06-i18n-v.js"), encoding="utf-8") as fh:
        ko = fh.read()
    fns = "\n".join(js_fn(f) for f in ("T", "plBody"))
    body = ("const PLS = { proj: '/p', data: { '/p': { ok: false, status: %d, msg: %s } } };\n"
            "console.log(JSON.stringify(plBody()));" % (status, json.dumps(msg)))
    code = "let LANG = %s;\n" % json.dumps(lang) + STUBS + ko + "\n" + fns + "\n" + body
    r = subprocess.run(node_e(code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class NotAProject(unittest.TestCase):
    def test_400_says_what_to_do(self):
        out = _run(400)
        self.assertIn("Pipelines are saved in .claude/pipelines/ inside the project", out)
        self.assertIn("Open a Claude session in this folder once", out)
        self.assertIn("<br>", out)
        self.assertNotIn("400", out)
        self.assertNotIn("Could not read", out)

    def test_400_korean(self):
        out = _run(400, lang="ko")
        self.assertIn("Claude 세션을 연 적 있는 폴더에서만", out)
        self.assertIn("«+ 새 파이프라인»", out)

    def test_other_failure_unchanged(self):
        out = _run(500, msg="boom")
        self.assertIn("Could not read the pipelines — boom", out)
        self.assertNotIn("Claude session", out)


if __name__ == "__main__":
    unittest.main()
