"""Pipelines: folder-picker error path stops before the success branch (48f plBrLoad), .error/.why reasons reach TE()
(48-pipeline.js plRemove), and a poll repaint keeps focus on a focused list row (paintPipe/plFocusKey). Run under node with stubs."""
import json
import os
import re
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import ROOT, js_fn
from tests._node import node_e

_ESC = "const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '\"': '&quot;', \"'\": '&#39;'})[c]);\n"


def _afn(file, name):
    with open(os.path.join(ROOT, "web", "js", file), encoding="utf-8") as f:
        src = f.read()
    return re.search(r"^async function " + name + r"\(.*?^}", src, re.S | re.M).group(0)


def _run(src):
    p = subprocess.run(node_e(src), capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 0, p.stderr[-600:]
    out = p.stdout
    return json.loads(out.strip().splitlines()[-1])


def _load(reply):
    return _run(_ESC + i18n_prelude("'en'", ("T", "TE")) + """
let PLBR = null, SETS = 0, PAINTS = 0;
function lsSet(){ SETS++; }
function plBrPaint(){ PAINTS++; }
const document = { querySelector(){ return null; } };
const fetch = async () => ({ json: async () => (%s) });
""" % json.dumps(reply) + _afn("48f-pipeline-browse.js", "plBrLoad") + """
(async () => {
  PLBR = { path: '/h/old', busy: false, msg: '' };
  await plBrLoad('/h/old', false);
  console.log(JSON.stringify({ path: PLBR.path, busy: PLBR.busy, msg: PLBR.msg, sets: SETS, paints: PAINTS }));
})();
""")


class BrowseErr(unittest.TestCase):
    def test_error_reply_keeps_path_and_clears_busy(self):
        out = _load({"ok": False, "msg": "nope"})
        self.assertEqual((out["path"], out["busy"], out["sets"], out["msg"]), ("/h/old", False, 0, "nope"))
        self.assertEqual(out["paints"], 2)

    def test_null_json_does_not_throw(self):
        out = _load(None)
        self.assertEqual((out["path"], out["busy"], out["sets"], out["msg"]), ("/h/old", False, 0, "Could not read the folder"))


class ErrorField(unittest.TestCase):
    def _remove(self, reply):
        return _run(_ESC + i18n_prelude("'en'", ("T", "TE")) + """
let SAID = '';
const confirm = () => true, alert = s => { SAID = s; };
async function plProjPost(){ return %s; }
""" % json.dumps(reply) + _afn("48-pipeline.js", "plRemove") + """
(async () => { await plRemove('/p'); console.log(JSON.stringify(SAID)); })();
""")

    def test_error_only_reply_shows_reason(self):
        self.assertIn("disk is full", self._remove({"ok": False, "error": "disk is full"}))

    def test_why_only_reply_shows_reason(self):
        self.assertIn("not a project", self._remove({"ok": False, "why": "not a project"}))


_DOM = r"""
let ACTIVE = null, ROUND = 0;
function mkEl(i){
  const at = [{ name: 'tabindex', value: '0' }, { name: 'data-plrow', value: String(i) }, { name: 'aria-label', value: 'row ' + i + ' r' + ROUND }];
  return { tagName: 'DIV', attributes: at, hasAttribute: n => at.some(a => a.name === n), getAttribute: n => (at.find(a => a.name === n) || {}).value,
           focus(){ ACTIVE = this; }, closest: () => null };
}
function match(el, sel){
  const tag = sel.match(/^[a-z]+/)[0];
  if(el.tagName.toLowerCase() !== tag) return false;
  const re = /\[([\w-]+)="((?:[^"\\]|\\.)*)"\]/g; let m;
  while((m = re.exec(sel))) if(el.getAttribute(m[1]) !== m[2].replace(/\\(.)/g, '$1')) return false;
  return true;
}
const box = { els: [], _plw: '',
  set innerHTML(h){ ROUND++; this.els = [0, 1, 2].map(mkEl); this._h = h; },
  querySelector(s){ return s === '.plw' && this._h ? { style: { setProperty(){} } } : null; },
  querySelectorAll(s){ return this.els.filter(e => match(e, s)); },
  contains(e){ return this.els.indexOf(e) >= 0; } };
const document = { body: { classList: { contains: () => false } }, get activeElement(){ return ACTIVE; } };
const performance = { now: () => 0 };
let PLDRAG = null, PLS = { off: false, proj: '/p', projs: null }, SESS = [], BODY = 'a';
function plLoadProjs(){} function plHnOn(){ return false; } function tbSlot(){} function plViewSeg(){ return ''; }
function plNowPickApply(){} function plNowShown(){ return false; } function plMainBody(){ return BODY; } function plAfterPaint(){}
"""


class FocusKeep(unittest.TestCase):
    def test_poll_repaint_keeps_focused_row(self):
        out = _run(_ESC + "const T = s => s;\n" + _DOM + js_fn("plFocusKey") + "\n" + js_fn("paintPipe") + """
paintPipe(box, false);
box.els[1].focus();
BODY = 'b';   // live run: the HTML changes every poll
paintPipe(box, true);
console.log(JSON.stringify([ROUND, box.els.indexOf(ACTIVE), ACTIVE.getAttribute('data-plrow')]));
""")
        self.assertEqual(out, [2, 1, "1"])


if __name__ == "__main__":
    unittest.main()
