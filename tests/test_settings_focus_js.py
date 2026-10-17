"""Settings «Preferences»: mail-watch skips /api/pipelines with the pipeline feature off (90d-mailwatch.js mwLoadProjs);
focus survives a repaint that drops the pressed button (mwFocusAfter · 90-settings.js cfgRefocus). Fake DOM only."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e


def _async_fn(name):
    src = js_all()
    return re.compile(r"^async function " + name + r"\(.*?^}", re.S | re.M).search(src).group(0)


JS = r"""
const R = {};
let calls = [];
let MW_PROJS = null, MW_LD = false, FEATS = {pipeline: false};
const getJSON = async u => { calls.push(u); return {ok: true, projects: []}; };
const mwRepaint = () => {};
(async () => {
  await mwLoadProjs(); R.off = calls.slice(); R.offProjs = MW_PROJS;
  FEATS = {}; await mwLoadProjs(); R.on = calls.slice();
  // fake elements: dataset + focus record
  let focused = null;
  const el = (ds, tag) => ({dataset: ds, tag, focus(){ focused = this; }});
  const g = el({mwg: ''}, 'input'), p1 = el({mwp: 'on', mwpath: '/a'}, 'button'), p2 = el({mwp: 'off', mwpath: '/a'}, 'button');
  const sec = {querySelectorAll: () => [g, p1, p2], querySelector: s => s === 'input[data-mwg]' ? g : null};
  mwFocusAfter(sec, {dataset: {mwp: 'off', mwpath: '/a'}}); R.path = focused === p2;
  mwFocusAfter(sec, {dataset: {mwsave: ''}}); R.save = focused === g;
  // cfgRefocus: pressed «저장» gone → first enabled control of the same key
  let CFGCAT = 'me';
  const ck = el({k: 'mpf'}, 'input');
  const box = {querySelector: s => s === '[data-k="mpf"]:not([disabled])' ? ck : null};
  focused = null; cfgRefocus(box, 'mpf', 'save'); R.cfg = focused === ck;
  const tab = el({cat: 'me'}, 'button');
  const box2 = {querySelector: s => s === '.cfgnv[data-cat="me"]' ? tab : null};
  focused = null; cfgRefocus(box2, 'mpf', 'save'); R.tab = focused === tab;
  process.stdout.write(JSON.stringify(R));
})();
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SettingsFocusJs(unittest.TestCase):
    def test_pipeline_off_and_focus(self):
        fns = [_async_fn("mwLoadProjs"), js_fn("mwFocusAfter")]
        src = "\n".join(fns) + "\n" + JS.replace("let CFGCAT = 'me';", "let CFGCAT = 'me';\n" + js_fn("cfgRefocus"))
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        R = json.loads(r.stdout)
        self.assertEqual(R["off"], [])                     # no /api/pipelines request with the feature off
        self.assertIsNone(R["offProjs"])
        self.assertEqual(R["on"], ["/api/pipelines"])
        self.assertTrue(R["path"] and R["save"] and R["cfg"] and R["tab"])


if __name__ == "__main__":
    unittest.main()
