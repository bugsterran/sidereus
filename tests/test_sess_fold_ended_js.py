"""«Show {n} ended» (#sfold) toggles even while the hover guard is set (web/js/40b-sessions-list.js buildSessions)."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

STUB = r"""
const els = {sess: {id: 'sess', html: ''}, sfold: null};
const document = {getElementById: id => id === 'sfold' ? els.sfold : els[id]};
const morphHtml = (box, h) => { box.html = h;
  const m = h.match(/<div class=sfold id=sfold>([^<]*)<\/div>/); els.sfold = m ? {label: m[1]} : null; };
const setHtml = morphHtml;
const esc = s => String(s), T = s => s;
const TV = o => o.msg.replace('{n}', o.vars.n);
let sessHover = false, sessDirty = false, sessOpen = false;
const stFil = '', idleMin = 0, gitFil = '', ACC_OTH = {sess: true};
const SESS = [{id: 'a', state: 'tool'}, {id: 'b', state: 'done'}, {id: 'c', state: 'done'}];
const buildFilters = () => {}, isIdle = () => true, hasGit = () => true;
const acctPick = () => null, acctInPick = () => true, acctOthHtml = () => '';
const wfFoldBtns = () => '', sessRowHtml = x => '<row ' + x.id + '>';
const sessFit = () => {}, buildInvite = () => {}, sessClick = () => {};
"""


def _js(body):
    src = STUB + js_fn("buildSessions") + "\n" + body
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SessFoldEnded(unittest.TestCase):
    def test_click_while_hovered_opens_fold(self):
        o = _js("buildSessions(); const before = els.sfold.label;"
                "sessHover = true; els.sfold.onclick();"
                "console.log(JSON.stringify({before: before, after: els.sfold.label, open: sessOpen,"
                " dirty: sessDirty, rows: els.sess.html.includes('<row b>')}));")
        self.assertEqual(o["before"], "▸ Show 2 ended")
        self.assertTrue(o["open"])
        self.assertEqual(o["after"], "▾ Hide 2 ended")
        self.assertTrue(o["rows"])
        self.assertFalse(o["dirty"])


if __name__ == "__main__":
    unittest.main()
