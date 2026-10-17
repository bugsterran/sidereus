"""Timeline empty window (web/js/74 paintTl): the toolbar range controls are drawn and wired even when
no rows came back — they are the only way to widen the window out of «최근 N시간 없음»."""
import json
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_fn
from tests._node import node_e


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlEmptyCtl(unittest.TestCase):
    def run_paint(self, rows, lang='en'):
        src = i18n_prelude(repr(lang)) + js_fn("paintTl") + js_fn("tlEmptyMsg") + r"""
const calls = [];
let mainView = 'time', SESS = [{}], tlReqAt = 0;
const box = {innerHTML: ''};
const document = {getElementById: id => id === 'feed' ? box : null};
const esc = s => s;
const tbSet = (k, h) => calls.push(['tbSet', k, h]);
const tlCtlHtml = () => '<CTL>', tlgChipHtml = () => '<GIT>', tlgWire = () => calls.push(['gitwire']);
const tlWireCtl = () => calls.push(['wire']);
let TLD = {ok: true, hours: 12, rows: ROWS};
try{ paintTl(); }catch(e){ calls.push(['threw']); }
process.stdout.write(JSON.stringify({calls, html: box.innerHTML}));
""".replace("ROWS", json.dumps(rows))
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        return json.loads(r.stdout)

    def test_empty_rows_still_set_and_wire_controls(self):
        R = self.run_paint([])
        self.assertIn(["tbSet", "time", "<CTL><GIT>"], R["calls"])   # the git chip stays without subagent rows
        self.assertIn(["gitwire"], R["calls"])
        self.assertIn(["wire"], R["calls"])
        self.assertIn("No subagents ran in the last 12h", R["html"])
        self.assertNotIn(["threw"], R["calls"])
        self.assertIn("최근 12시간 안에 돈 서브에이전트가 없습니다", self.run_paint([], 'ko')["html"])


if __name__ == "__main__":
    unittest.main()
