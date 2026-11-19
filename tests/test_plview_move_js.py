"""Tools / Connections moved from the Tokens tab to the Pipelines view switch (48-pipeline.js PLVIEWS · plViewSeg · plSetView · plPaint).
R1 switch order + routing · R2 Tokens has no switch · R3 old stored tkview lands on Pipelines · R4 harness off keeps Tools/Connections."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_switch
from tests._load import ROOT, js_fn
from tests._node import node_e

_JS = os.path.join(ROOT, "web", "js")


def _read(name):
    with open(os.path.join(_JS, name), encoding="utf-8") as f:
        return f.read()


_PL = _read("48-pipeline.js")
_PLVIEWS = re.search(r"^const PLVIEWS = \[[^\]]*\];", _PL, re.M).group(0)
_INIT = re.search(r"^let PLVIEW = \(\(\) => \{.*?\n\}\)\(\);", _PL, re.M | re.S).group(0)

# Recorders: storage writes, tab switches, repaints, toolbar slot, sub-view painters, Harness incident clears.
_PRE = ("let LANG = 'ko';\n" + i18n_switch() +
        "const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '\"': '&quot;', \"'\": '&#39;'}[c]));\n"
        "var FEATS = {}, LS = {}, MV = [], PAINTS = 0, TB = [], DRAWN = [], CLR = 0, SAVE = 0, RESTORE = 0, mainView = 'pipe';\n"
        "const PLS = {off: false};\n"
        "const box = {innerHTML: ''};\n"
        "const document = {getElementById: id => id === 'feed' ? box : null, activeElement: null, querySelector(){ return null; }};\n"
        "function lsSet(k, v){ LS[k] = v; } function setMainView(v){ MV.push(v); mainView = v; }\n"
        "function plPipeTopSave(){ SAVE++; } function plPipeTopRestore(){ RESTORE++; } function hnGoClear(){ CLR++; }\n"
        "function hnHtml(){ return ''; } function tbSlot(k, h){ TB.push([k, h]); }\n"
        "function paintTools(b){ DRAWN.push('tools'); } function paintMcpConn(b){ DRAWN.push('conn'); }\n"
        "function paintPipe(b, p){ DRAWN.push('pipe'); }\n"
        + _PLVIEWS + "\nlet PLVIEW = 'pipe';\n"
        + "\n".join(js_fn(n) for n in ("plHnOn", "plViewSeg", "plSetView", "plPaint", "plSubPaint")) + "\n")


def _js(body, pre=_PRE):
    r = subprocess.run(node_e(pre + body), capture_output=True, text=True, encoding="utf-8", timeout=30)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def _segs(html):
    return re.findall(r'data-plv="(\w+)">([^<]*)<', html)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PlViewMove(unittest.TestCase):
    def test_r1_switch_order_and_labels(self):
        h = _js("console.log(JSON.stringify(plViewSeg()))")
        self.assertEqual(_segs(h), [("pipe", "파이프라인"), ("harness", "하네스 리포트"), ("tools", "도구"), ("conn", "연결")])
        self.assertEqual(h.count('aria-pressed="true'), 1)
        self.assertIn('class="wkrgb on" aria-pressed="true" data-plv="pipe"', h)

    def test_r4_harness_off_keeps_tools_and_connections(self):
        off, rem = _js("FEATS.harness = false; const a = plViewSeg(); PLVIEW = 'harness';"
                       " console.log(JSON.stringify([a, plViewSeg()]))")
        self.assertEqual([k for k, _ in _segs(off)], ["pipe", "tools", "conn"])
        self.assertIn('class="wkrgb on" aria-pressed="true" data-plv="pipe"', rem)   # a remembered Harness shows the pipeline body

    def test_r1_conn_is_highlighted(self):
        h = _js("PLVIEW = 'conn'; console.log(JSON.stringify(plViewSeg()))")
        self.assertIn('class="wkrgb on" aria-pressed="true" data-plv="conn"', h)

    def test_r1_set_view_on_tab_repaints(self):
        r = _js("PLVIEW = 'harness'; plSetView('tools'); const a = [PLVIEW, LS['sidereus.plview'], CLR, SAVE, DRAWN.slice(), MV.slice()];"
                " plSetView('pipe'); console.log(JSON.stringify([a, PLVIEW, CLR, SAVE, RESTORE, DRAWN, MV]))")
        a, view, clr, save, restore, drawn, mv = r
        self.assertEqual(a, ["tools", "tools", 1, 0, ["tools"], []])   # leaving Harness clears the incident once
        self.assertEqual([view, clr, save, restore, drawn, mv], ["pipe", 1, 0, 1, ["tools", "pipe"], []])

    def test_r1_set_view_saves_pipe_scroll_only_on_tab(self):
        r = _js("plSetView('conn'); const a = SAVE; PLVIEW = 'pipe'; mainView = 'token'; plSetView('tools');"
                " console.log(JSON.stringify([a, SAVE, MV, PLVIEW, LS['sidereus.plview'], DRAWN]))")
        self.assertEqual(r, [1, 1, ["pipe"], "tools", "tools", ["conn"]])   # off the tab: open it, no repaint of the old tab
        self.assertEqual(_js("plSetView('junk'); console.log(JSON.stringify(PLVIEW))"), "pipe")

    def test_r1_plpaint_routes_sub_views(self):
        r = _js("PLVIEW = 'tools'; plPaint(); PLVIEW = 'conn'; plPaint(); PLVIEW = 'pipe'; plPaint(); PLVIEW = 'harness'; plPaint();"
                " mainView = 'token'; PLVIEW = 'tools'; plPaint(); console.log(JSON.stringify([DRAWN, TB.map(x => x[0])]))")
        self.assertEqual(r[0], ["tools", "conn", "pipe", "pipe"])
        self.assertEqual(r[1], ["pipe", "pipe"])   # the switch stays in the toolbar for Tools / Connections
        tb = _js("PLVIEW = 'tools'; plPaint(); console.log(JSON.stringify(TB[0][1]))")
        self.assertEqual(len(_segs(tb)), 4)

    def test_r1_poll_keeps_focus_in_tool_lists(self):
        r = _js("PLVIEW = 'tools'; document.activeElement = {closest: s => s === '.tvw' ? {} : null};"
                " plPaint(true); const a = DRAWN.length; plPaint(); console.log(JSON.stringify([a, DRAWN.length]))")
        self.assertEqual(r, [0, 1])

    def test_r1_direct_paint_pipe_routes_too(self):
        self.assertIn("if(typeof plSubPaint === 'function' && plSubPaint(box, fromPoll)) return;", _PL)   # 48b plPoll calls paintPipe directly

    def test_r1_backspace_deletes_stage_only_in_pipelines_view(self):
        src = _read("48d-pipeline-cv-input.js")
        h = re.search(r"^document\.addEventListener\('keydown', e => \{\n  if\(mainView !== 'pipe' \|\| \(e\.key !== 'Delete'.*?^\}\);", src, re.M | re.S).group(0)
        pre = ("let mainView = 'pipe', PLVIEW = 'pipe', DEL = 0, KD = null;\n"
               "const document = {addEventListener(t, f){ if(t === 'keydown') KD = f; }};\n"
               "function plCurEnt(){ return {sel: {k: 'n', id: 'a'}}; } function plRO(){ return false; } function plDelSel(){ DEL++; }\n" + h + "\n")
        r = _js("const out = {}; for(const v of ['conn', 'tools', 'harness', 'pipe']){ PLVIEW = v; DEL = 0;"
                " KD({key: 'Backspace', target: {tagName: 'DIV', closest(){ return null; }}, preventDefault(){}}); out[v] = DEL; }"
                " console.log(JSON.stringify(out))", pre=pre)
        self.assertEqual(r, {"conn": 0, "tools": 0, "harness": 0, "pipe": 1})   # a stage picked in Edit is never deleted unseen

    def _init(self, moved, stored):
        pre = ("var LS = {}; const STORE = %s; let mvTkMoved = %s;\n" % (json.dumps(stored), json.dumps(moved))
               + "function lsGet(k, d){ return Object.prototype.hasOwnProperty.call(STORE, k) ? STORE[k] : d; } function lsSet(k, v){ LS[k] = v; }\n"
               + _PLVIEWS + "\n" + _INIT + "\n")
        return _js("console.log(JSON.stringify([PLVIEW, LS]))", pre=pre)

    def test_r3_plview_init(self):
        self.assertEqual(self._init("tools", {"sidereus.plview": "harness"}), ["tools", {"sidereus.plview": "tools"}])
        self.assertEqual(self._init("conn", {}), ["conn", {"sidereus.plview": "conn"}])
        self.assertEqual(self._init("", {"sidereus.plview": "conn"}), ["conn", {}])
        self.assertEqual(self._init("", {"sidereus.plview": "junk"}), ["pipe", {}])
        self.assertEqual(self._init("", {}), ["pipe", {}])

    def test_r2_token_tab_has_no_sub_views(self):
        tk = _read("46-tokens-tab.js")
        for gone in ("TKVIEW", "tkViewSeg", "data-tv", "paintTools", "paintMcpConn"):
            self.assertNotIn(gone, tk)
        self.assertIn("if(lsGet('sidereus.tkview', null) !== null) lsDel('sidereus.tkview');", tk)

    def test_r3_load_order(self):
        names = sorted(os.listdir(_JS))
        self.assertLess(names.index("05-i18n.js"), names.index("46-tokens-tab.js"))
        # ⚠48 reads mvTkMoved (set in 05), not the stored key 46 deletes, so 46 running first is safe.
        self.assertNotIn("sidereus.tkview", _PL)

    def test_r5_no_token_view_jumps_left(self):
        for name in sorted(os.listdir(_JS)):
            if name.endswith(".js"):
                s = _read(name)
                self.assertNotIn("TKVIEW", s, name)
                if name != "46-tokens-tab.js":
                    self.assertNotIn("sidereus.tkview", s.replace("UIS['sidereus.tkview']", ""), name)


if __name__ == "__main__":
    unittest.main()
