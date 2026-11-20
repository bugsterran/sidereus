"""Tools / Session tools live in their own «Tools» tab (47a-tools-tab.js TLVIEWS · tlViewSeg · tlSetView · tlPaint);
the Pipelines switch is «Pipelines | Harness report» (48-pipeline.js PLVIEWS · plViewSeg · plSetView · plPaint).
R1 switch order + routing · R2 Tokens has no switch · R4 old stored tools/conn views are rewritten."""
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
_TL = _read("47a-tools-tab.js")
_PLVIEWS = re.search(r"^const PLVIEWS = \[[^\]]*\];", _PL, re.M).group(0)
_INIT = re.search(r"^let PLVIEW = \(\(\) => \{.*?\n\}\)\(\);", _PL, re.M | re.S).group(0)
_TLVIEWS = re.search(r"^const TLVIEWS = \[[^\]]*\];", _TL, re.M).group(0)
_TLINIT = re.search(r"^let TLVIEW = \(\(\) => \{.*?\n\}\)\(\);", _TL, re.M | re.S).group(0)

# Recorders: storage writes, tab switches, repaints, toolbar slot, sub-view painters, Harness incident clears.
_PRE = ("let LANG = 'ko';\n" + i18n_switch() +
        "const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '\"': '&quot;', \"'\": '&#39;'}[c]));\n"
        "var FEATS = {}, LS = {}, MV = [], PAINTS = 0, TB = [], DRAWN = [], CLR = 0, SAVE = 0, RESTORE = 0, mainView = 'pipe';\n"
        "const PLS = {off: false};\n"
        "const box = {innerHTML: ''};\n"
        "const document = {getElementById: id => id === 'feed' ? box : null, activeElement: null, querySelector(){ return null; }, hidden: false};\n"
        "function lsSet(k, v){ LS[k] = v; } function setMainView(v){ MV.push(v); mainView = v; }\n"
        "function plPipeTopSave(){ SAVE++; } function plPipeTopRestore(){ RESTORE++; } function hnGoClear(){ CLR++; }\n"
        "function hnHtml(){ return ''; } function tbSlot(k, h){ TB.push([k, h]); }\n"
        "function paintTools(b){ DRAWN.push('tools'); } function paintMcpConn(b){ DRAWN.push('conn'); }\n"
        "function paintPipe(b, p){ DRAWN.push('pipe'); }\n"
        + _PLVIEWS + "\nlet PLVIEW = 'pipe';\n" + _TLVIEWS + "\nlet TLVIEW = 'tools';\n"
        + "\n".join(js_fn(n) for n in ("plHnOn", "plViewSeg", "plSetView", "plPaint", "tlViewSeg", "tlSetView", "tlPaint", "tlPoll")) + "\n")


def _js(body, pre=_PRE):
    r = subprocess.run(node_e(pre + body), capture_output=True, text=True, encoding="utf-8", timeout=30)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def _segs(html, attr="plv"):
    return re.findall(r'data-%s="(\w+)">([^<]*)<' % attr, html)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PlViewMove(unittest.TestCase):
    def test_r1_pipelines_switch_is_pipe_and_harness(self):
        h = _js("console.log(JSON.stringify(plViewSeg()))")
        self.assertEqual(_segs(h), [("pipe", "파이프라인"), ("harness", "하네스 리포트")])
        self.assertEqual(h.count('aria-pressed="true'), 1)
        self.assertIn('class="wkrgb on" aria-pressed="true" data-plv="pipe"', h)

    def test_r1_harness_off_or_pipeline_404_has_no_switch(self):
        r = _js("FEATS.harness = false; const a = plViewSeg(); FEATS.harness = true; PLS.off = true;"
                " console.log(JSON.stringify([a, plViewSeg()]))")
        self.assertEqual(r, ["", ""])

    def test_r1_tools_switch_order_and_labels(self):
        h = _js("console.log(JSON.stringify(tlViewSeg()))")
        self.assertEqual(_segs(h, "tlv"), [("tools", "도구"), ("conn", "세션 도구")])
        self.assertEqual(h.count('aria-pressed="true'), 1)
        self.assertIn('class="wkrgb on" aria-pressed="true" data-tlv="tools"', h)
        h = _js("TLVIEW = 'conn'; console.log(JSON.stringify(tlViewSeg()))")
        self.assertIn('class="wkrgb on" aria-pressed="true" data-tlv="conn"', h)

    def test_r1_tools_switch_english(self):
        h = _js("LANG = 'en'; console.log(JSON.stringify(tlViewSeg()))")
        self.assertEqual(_segs(h, "tlv"), [("tools", "Tools"), ("conn", "Session tools")])

    def test_r1_pl_set_view_on_tab_repaints(self):
        r = _js("PLVIEW = 'harness'; plSetView('pipe'); const a = [PLVIEW, LS['sidereus.plview'], CLR, RESTORE, DRAWN.slice(), MV.slice()];"
                " plSetView('harness'); console.log(JSON.stringify([a, PLVIEW, SAVE, DRAWN, MV]))")
        a, view, save, drawn, mv = r
        self.assertEqual(a, ["pipe", "pipe", 1, 1, ["pipe"], []])   # leaving Harness clears the incident once
        self.assertEqual([view, save, drawn, mv], ["harness", 1, ["pipe", "pipe"], []])
        self.assertEqual(_js("plSetView('tools'); console.log(JSON.stringify(PLVIEW))"), "pipe")   # old sub-view keys are no longer Pipelines views

    def test_r1_tl_set_view_on_tab_repaints(self):
        r = _js("mainView = 'tools'; tlSetView('conn'); const a = [TLVIEW, LS['sidereus.tlview'], DRAWN.slice(), MV.slice()];"
                " tlSetView('tools'); console.log(JSON.stringify([a, TLVIEW, DRAWN, MV, TB.map(x => x[0])]))")
        self.assertEqual(r, [["conn", "conn", ["conn"], []], "tools", ["conn", "tools"], [], ["tools", "tools"]])
        self.assertEqual(_js("mainView = 'tools'; tlSetView('junk'); console.log(JSON.stringify(TLVIEW))"), "tools")

    def test_r1_tl_set_view_off_tab_opens_tools(self):
        r = _js("mainView = 'pipe'; tlSetView('conn'); console.log(JSON.stringify([MV, mainView, TLVIEW, LS['sidereus.tlview'], DRAWN]))")
        self.assertEqual(r, [["tools"], "tools", "conn", "conn", []])   # off the tab: open it, no repaint of the old tab

    def test_r1_paint_routes_by_tab(self):
        r = _js("plPaint(); PLVIEW = 'harness'; plPaint(); tlPaint();"
                " mainView = 'tools'; plPaint(); tlPaint(); TLVIEW = 'conn'; tlPaint();"
                " console.log(JSON.stringify([DRAWN, TB.map(x => x[0])]))")
        self.assertEqual(r, [["pipe", "pipe", "tools", "conn"], ["tools", "tools"]])

    def test_r1_poll_keeps_focus_in_tool_lists(self):
        r = _js("mainView = 'tools'; document.activeElement = {closest: s => s === '.tvw' ? {} : null};"
                " tlPoll(); const a = DRAWN.length; tlPaint(); document.hidden = true; tlPoll();"
                " console.log(JSON.stringify([a, DRAWN.length]))")
        self.assertEqual(r, [0, 1])

    def test_r1_pipeline_has_no_tool_views_left(self):
        for gone in ("plSubPaint", "paintTools", "paintMcpConn", "PLVIEW === 'conn'", "mvTkMoved"):
            self.assertNotIn(gone, _PL)

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

    def _init(self, stored):
        pre = ("var LS = {}; const STORE = %s;\n" % json.dumps(stored)
               + "function lsGet(k, d){ return Object.prototype.hasOwnProperty.call(STORE, k) ? STORE[k] : d; } function lsSet(k, v){ LS[k] = v; }\n"
               + _PLVIEWS + "\n" + _INIT + "\n")
        return _js("console.log(JSON.stringify([PLVIEW, LS]))", pre=pre)

    def test_r4_plview_init_rewrites_moved_views(self):
        self.assertEqual(self._init({"sidereus.plview": "conn"}), ["pipe", {"sidereus.plview": "pipe"}])
        self.assertEqual(self._init({"sidereus.plview": "tools"}), ["pipe", {"sidereus.plview": "pipe"}])
        self.assertEqual(self._init({"sidereus.plview": "harness"}), ["harness", {}])
        self.assertEqual(self._init({"sidereus.plview": "junk"}), ["pipe", {}])
        self.assertEqual(self._init({}), ["pipe", {}])

    def _tlinit(self, moved, stored):
        pre = ("var LS = {}; const STORE = %s; let mvToolsMoved = %s;\n" % (json.dumps(stored), json.dumps(moved))
               + "function lsGet(k, d){ return Object.prototype.hasOwnProperty.call(STORE, k) ? STORE[k] : d; } function lsSet(k, v){ LS[k] = v; }\n"
               + _TLVIEWS + "\n" + _TLINIT + "\n")
        return _js("console.log(JSON.stringify([TLVIEW, LS]))", pre=pre)

    def test_r4_tlview_init(self):
        self.assertEqual(self._tlinit("conn", {"sidereus.tlview": "tools"}), ["conn", {"sidereus.tlview": "conn"}])
        self.assertEqual(self._tlinit("tools", {}), ["tools", {"sidereus.tlview": "tools"}])
        self.assertEqual(self._tlinit("", {"sidereus.tlview": "conn"}), ["conn", {}])
        self.assertEqual(self._tlinit("", {"sidereus.tlview": "junk"}), ["tools", {}])
        self.assertEqual(self._tlinit("", {}), ["tools", {}])

    def test_r2_token_tab_has_no_sub_views(self):
        tk = _read("46-tokens-tab.js")
        for gone in ("TKVIEW", "tkViewSeg", "data-tv", "paintTools", "paintMcpConn"):
            self.assertNotIn(gone, tk)
        self.assertIn("if(lsGet('sidereus.tkview', null) !== null) lsDel('sidereus.tkview');", tk)

    def test_r4_load_order(self):
        names = sorted(os.listdir(_JS))
        self.assertLess(names.index("05-i18n.js"), names.index("46-tokens-tab.js"))
        self.assertLess(names.index("05-i18n.js"), names.index("47a-tools-tab.js"))
        self.assertLess(names.index("47a-tools-tab.js"), names.index("47k-mcpconn.js"))
        # ⚠47a reads mvToolsMoved (set in 05), not the stored key 46 deletes, so 46 running first is safe.
        self.assertNotIn("sidereus.tkview", _PL)
        self.assertNotIn("sidereus.tkview", _TL)

    def test_r5_no_token_view_jumps_left(self):
        for name in sorted(os.listdir(_JS)):
            if name.endswith(".js"):
                s = _read(name)
                self.assertNotIn("TKVIEW", s, name)
                if name != "46-tokens-tab.js":
                    self.assertNotIn("sidereus.tkview", s.replace("UIS['sidereus.tkview']", ""), name)


if __name__ == "__main__":
    unittest.main()
