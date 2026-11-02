"""Ended sessions live only in «Recently ended sessions»: no #sfold in #sess, done rows not in #sess,
the palette jump to a done session opens the merged list (web/js/40b buildSessions, 40 cpGo)."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

STUB = r"""
const FIN = {value: 'old'};
const els = {sess: {id: 'sess', html: ''}, sesrec: {id: 'sesrec', offsetParent: {}, scrolled: 0, scrollIntoView(){ this.scrolled++; },
  querySelector: q => q === '.srecf' ? FIN : null}};
const document = {getElementById: id => els[id] || null, querySelectorAll: () => []};
const morphHtml = (box, h) => { box.html = h; };
const setHtml = morphHtml;
const esc = s => String(s), T = s => s;
const TV = o => o.msg.replace('{n}', o.vars.n);
let sessHover = false, sessDirty = false, cpFlash = '';
let stFil = '', idleMin = 0, gitFil = '';
const ACC_OTH = {sess: true}, STORE = {}, CALLS = [];
const UIS = {getItem: k => STORE[k] || null, setItem: (k, v) => { STORE[k] = String(v); }};
const SREC = {open: false, rows: [{sid: 'zz'}], err: true, q: 'nomatch', at: 99};
const SESS = [{id: 'a', sid: 'a', state: 'tool'}, {id: 'b', sid: 'b', state: 'done'}, {id: 'c', sid: 'c', state: 'done', plat: 'cx'}];
const buildFilters = () => {}, isIdle = () => true, hasGit = () => true;
const acctPick = () => null, acctInPick = () => true, acctOthHtml = () => '';
const wfFoldBtns = () => '', sessRowHtml = x => '<row ' + x.id + '>';
const sessFit = () => {}, buildInvite = () => {}, sessClick = () => {}, softErr = () => {};
const cpClose = () => {}, sesdrReveal = () => {}, note = m => CALLS.push('note:' + m), saveFil = () => {}, buildTodo = () => {};
const srecLoad = () => CALLS.push('load:' + SREC.at + ':' + cpFlash), srecPaint = () => CALLS.push('paint');
const setTimeout = () => {};
"""


def _js(body):
    src = STUB + js_fn("buildSessions") + "\n" + js_fn("cpKey") + "\n" + js_fn("cpGo") + "\n" + body
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SessEndedMerged(unittest.TestCase):
    def test_no_fold_and_done_rows_absent(self):
        o = _js("buildSessions(); console.log(JSON.stringify({h: els.sess.html}));")
        self.assertNotIn("sfold", o["h"])
        self.assertIn("<row a>", o["h"])
        self.assertNotIn("<row b>", o["h"])
        self.assertNotIn("<row c>", o["h"])
        self.assertNotIn("hidden by filter", o["h"])     # done rows are not counted as filtered

    def test_filter_hidden_counts_live_rows_only(self):
        o = _js("stFil = 'ask'; buildSessions(); console.log(JSON.stringify({h: els.sess.html}));")
        self.assertIn("1 hidden by filter", o["h"])

    def test_cpgo_done_opens_recent(self):
        o = _js("cpGo(SESS[2]); console.log(JSON.stringify({open: SREC.open, err: SREC.err, st: STORE['sidereus.sesrec'],"
                " calls: CALLS, scrolled: els.sesrec.scrolled, flash: cpFlash, q: SREC.q, fin: FIN.value, go: SREC.go}));")
        self.assertTrue(o["open"])
        self.assertFalse(o["err"])
        self.assertEqual(o["st"], "1")
        self.assertEqual(o["calls"], ["load:0:s:c", "paint"])   # sid not in rows: cache bypassed, flash key set
        self.assertEqual(o["scrolled"], 1)
        self.assertEqual((o["q"], o["fin"], o["go"]), ("", "", "c"))   # filter cleared, row target kept for srecPaint

    def test_cpgo_known_row_keeps_cache(self):
        o = _js("SREC.rows = [{sid: 'c'}]; cpGo(SESS[2]); console.log(JSON.stringify({calls: CALLS}));")
        self.assertEqual(o["calls"], ["load:99:s:c", "paint"])


if __name__ == "__main__":
    unittest.main()
