"""Work popup for external CLI sessions (35-worklog.js extBody): the source note follows d.src."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import i18n, jconst
from tests._node import node_e

STUBS = """
var document = {getElementById: () => null};
const aiLogo = p => '<i class=ailg-' + p + '></i>';
const stateLbl = s => s;
const agoAt = () => '';
"""

BODY = """
const base = {ext: true, plat: 'pi', state: 'idle', tool: 'bash', events: []};
const R = {
  file: extBody(Object.assign({}, base, {src: 'file'})),
  hook: extBody(Object.assign({}, base, {plat: 'cursor', tool: '<t>'})),
  sumFile: wkSum({ok: true, ext: true, src: 'file', state: 'idle', events: [{}]}),
  sumHook: wkSum({ok: true, ext: true, state: 'idle', events: [{}]}),
};
process.stdout.write(JSON.stringify(R));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class WorklogExt(unittest.TestCase):
    def test_note_depends_on_src(self):
        src = (STUBS + i18n() + "\n" + jconst("esc") + "\n" + js_fn("extBody") + "\n" + js_fn("wkSum") + "\n" + BODY)
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        R = json.loads(r.stdout)
        self.assertIn("세션 파일에서 읽습니다", R["file"])
        self.assertNotIn("훅", R["file"].split("extnt>")[1].split("</div>")[0])
        self.assertIn("<td>bash</td>", R["file"])
        self.assertNotIn("세션 파일에서 읽습니다", R["hook"])
        self.assertIn("&lt;t&gt;", R["hook"])
        self.assertTrue(R["sumFile"].startswith("세션 이벤트 1"))
        self.assertTrue(R["sumHook"].startswith("훅 이벤트 1"))


if __name__ == "__main__":
    unittest.main()
