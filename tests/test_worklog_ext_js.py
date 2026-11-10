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

    def test_R1_log_renders_feed_R2_without_log_keeps_ext(self):
        stubs = (STUBS + """
const agFeedLine = (cx, f) => '<p class=fd>' + f.kind + ':' + (f.kind === 'say' ? f.text : f.s.tool) + '</p>';
const agBodyHtml = (d, head, body) => '<div class=agb>' + head.join(' | ') + '</div>' + body;
const agEditWas = new Map();
const agFileList = () => [];
const sz = n => String(n);
const ago = n => String(n);
""")
        body = """
const lg = {ok: true, ext: true, log: true, plat: 'pi', sid: 'abc', state: 'idle', events: [],
  first: '2026-01-01T00:00:00Z', last: '2026-01-01T00:05:00Z',
  steps: [{t: '2026-01-01T00:01:00Z', tool: 'bash'}], says: [{t: '2026-01-01T00:02:00Z', text: 'done'}]};
const R = {
  body: agentBody(lg),
  sum: wkSum(lg),
  noLog: agentBody({ok: true, ext: true, plat: 'pi', src: 'file', state: 'idle', events: []}),
};
process.stdout.write(JSON.stringify(R));
"""
        src = (stubs + i18n() + "\n" + jconst("esc") + "\n" + js_fn("extBody") + "\n" + js_fn("agentBody") + "\n" + js_fn("wkSum") + "\n" + body)
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        R = json.loads(r.stdout)
        # R1: log set -> the normal feed, not the hook/session-file note
        self.assertIn("<p class=fd>run:bash</p>", R["body"])
        self.assertIn("<p class=fd>say:done</p>", R["body"])
        self.assertNotIn("extnt", R["body"])
        self.assertNotIn("세션 이벤트", R["sum"])
        self.assertNotIn("훅 이벤트", R["sum"])
        self.assertIn("최근", R["sum"])
        # R2: no session file (no log) -> the existing ext empty state
        self.assertIn("extnt", R["noLog"])
        self.assertIn("기록된 이벤트", R["noLog"])


if __name__ == "__main__":
    unittest.main()
