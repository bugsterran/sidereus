"""Token tab «Tools» view hosts the Harness «Config map» (47b hnCfgHtml via 47-tools.js paintTools) — R3, plus the R4 jump from the report."""
import json
import os
import subprocess
import unittest

from tests._i18n_js import i18n_switch
from tests._load import ROOT
from tests._node import node_e
from tests.test_harness_js import _STUB

_HN = os.path.join(ROOT, "web", "js", "47b-harness.js")
_TL = os.path.join(ROOT, "web", "js", "47-tools.js")
# Recorders replace the plain stubs: localStorage writes, view switches, repaints and the next-frame callback.
_REC = ("var LS = [], MV = [], TKP = 0, RAF = [], SCR = [], QSEL = null;"
        " function lsSet(k, v){ LS.push([k, v]); } function setMainView(v){ MV.push(v); mainView = v; } function paintToken(){ TKP++; }"
        " function requestAnimationFrame(f){ RAF.push(f); }\n")
_DOC = ("const LST = {}; const document = {addEventListener(t, f){ (LST[t] = LST[t] || []).push(f); },"
        " querySelector(s){ return QSEL ? QSEL(s) : null; }};\n")
_DATA = {"ok": True, "events": [{"ev": "Stop", "hooks": [{"cmd": "c.sh", "n": 3, "vd": {"lvl": "bad", "why": "hook_missing", "id": "v1"}}]}],
         "rules": [{"path": "/w/a/AGENTS.md", "order": 1}], "agents": [{"name": "impl", "scope": "project"}],
         "mcps": [{"name": "m1", "scope": "user"}], "skills": [{"name": "sk", "scope": "user"}],
         "counts": {"skill": 1, "cmd": 2, "mcp": 3}, "evidence": [], "verdict": {"bad": 1, "check": 0, "ok": 4}}


def _js(body, stub=_STUB, tools=False):
    src = stub.replace("function lsSet(){} function plPaint(){ PAINTS++; } function setMainView(){}", "function plPaint(){ PAINTS++; }")
    src += _REC + i18n_switch() + _DOC
    for p in ([_TL] if tools else []) + [_HN]:
        with open(p, encoding="utf-8") as f:
            src += f.read() + "\n"
    pre = "HN.data[hnKey('/w/a')] = %s; HN.at[hnKey('/w/a')] = NOW; HN.plats = ['cc', 'cx'];" % json.dumps(_DATA)
    return json.loads(subprocess.run(node_e(src + pre + body), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


class ToolsConfigMap(unittest.TestCase):
    def test_r3_fold_contents(self):
        cc, cx = _js(" const a = hnCfgHtml(PLS.proj); HN.plat = 'cx'; HN.data[hnKey('/w/a')] = HN.data['cc\\n/w/a'];"
                     " console.log(JSON.stringify([a, hnCfgHtml(PLS.proj)]))")
        self.assertTrue(cc.startswith('<div class="hnw hncfgw"><details class=hncfg'))
        for t in ("구성 지도", "data-hnflow", "규칙 파일", "에이전트 ↔ 파이프라인", "MCP 서버", ">sk<", "class=hncnt", "data-hnplat", "data-hnvdgo=bad"):
            self.assertIn(t, cc)
        self.assertNotIn("class=hncnt", cx)   # counts jump to Claude Code's tool list only
        summ = cc.split("<summary class=hncfgs>", 1)[1].split("</summary>", 1)[0]
        self.assertIn("<i class=hncfgp>a</i>", summ)   # project name as text, never a button inside <summary>
        self.assertNotIn("<button", summ)
        self.assertIn('hnvdq hnvd-bad">문제 1', summ)

    def test_r3_open_rule(self):
        a, b = _js(" const a = hnCfgHtml(PLS.proj); HN.cfgOpen = false; console.log(JSON.stringify([a, hnCfgHtml(PLS.proj)]))")
        self.assertIn("<details class=hncfg open>", a)   # no stored choice + problems: open
        self.assertIn("<details class=hncfg>", b)
        stored = _js(" console.log(JSON.stringify(hnCfgHtml(PLS.proj)))",
                     stub=_STUB.replace("function lsGet(k, d){ return d; }", "function lsGet(k, d){ return k === 'sidereus.hncfg' ? '0' : d; }"))
        self.assertIn("<details class=hncfg>", stored)   # a stored «closed» wins over problems

    def test_r3_toggle_remembered(self):
        r = _js(" hnCfgHtml(PLS.proj); const t = e => LST.toggle.forEach(f => f({target: {classList: {contains: k => k === 'hncfg'}, open: e}}));"
                " t(true); const a = [HN.cfgOpen, LS.length]; t(false); console.log(JSON.stringify([a, HN.cfgOpen, LS]))")
        self.assertEqual(r[0], [None, 0])   # the paint's own open is not a choice
        self.assertEqual(r[1], False)
        self.assertEqual(r[2], [["sidereus.hncfg", "0"]])

    def test_r3_paint_tools_order(self):
        h = _js(" TOOLS = {ok: true, items: [{id: 's1', kind: 'skill', name: 'sk', scope: 'user', path: '/p', on: true}]}; toolsAt = NOW;"
                " const box = {innerHTML: '', querySelector(){ return null; }}; mainView = 'token'; TKVIEW = 'tools'; paintTools(box);"
                " console.log(JSON.stringify(box.innerHTML))", tools=True)
        self.assertLess(h.index("wvht"), h.index("hncfgw"))
        self.assertLess(h.index("hncfgw"), h.index("class=tvwg"))

    def test_r3_feature_off_and_no_project(self):
        off, none = _js(" var FEATS = {harness: false}; const a = hnCfgHtml(PLS.proj); FEATS.harness = true;"
                        " console.log(JSON.stringify([a, hnCfgHtml('')]))")
        self.assertEqual(off, "")
        self.assertIn("파이프라인 탭에서 프로젝트를 고르세요", none)
        self.assertNotIn("data-hnflow", none)

    def test_r3_load_repaints_tools_view(self):
        r = _js(" mainView = 'token'; TKVIEW = 'tools'; HN.data = {}; var FEATS = {};"
                " fetch = u => Promise.resolve({status: 200, json: () => Promise.resolve({ok: true, events: []})});"
                " hnLoad('/w/a', true).then(() => console.log(JSON.stringify([TKP, PAINTS])))")
        self.assertEqual(r, [1, 0])

    def test_r3_poll_repaint_skipped_while_focus_in_map(self):
        r = _js(" mainView = 'token'; TKVIEW = 'tools'; document.activeElement = {closest: s => s === '.hncfgw' ? {} : null};"
                " hnRepaint(true); const a = TKP; hnRepaint(); const b = TKP; document.activeElement = null;"
                " QSEL = s => s === '.hncfgw [title]:hover' ? {} : null; hnRepaint(true); const c = TKP; QSEL = null; hnRepaint(true);"
                " console.log(JSON.stringify([a, b, c, TKP]))")
        self.assertEqual(r, [0, 1, 1, 2])   # focus or hover holds a poll repaint; a non-poll repaint still paints

    def test_r4_report_jump_opens_tools(self):
        r = _js(" QSEL = s => s === '.hnw' ? {classList: {contains: () => false}} : null; mainView = 'pipe';"
                " hnVdGo('bad'); console.log(JSON.stringify([TKVIEW, HN.cfgOpen, MV, LS, RAF.length]))")
        self.assertEqual(r[0], "tools")
        self.assertIs(r[1], True)
        self.assertEqual(r[2], ["token"])
        self.assertIn(["sidereus.hncfg", "1"], r[3])
        self.assertEqual(r[4], 1)   # the step waits for the paint

    def test_tools_count_click_stays_in_tools(self):
        r = _js(" mainView = 'token'; TKVIEW = 'tools'; QSEL = s => s === '.tvwg' ? {scrollIntoView(o){ SCR.push(o); }} : null;"
                " const c = {closest: s => s === '.hnw' || s === '.hncfgw' ? {} : null};"
                " LST.click.forEach(f => f({target: {closest: s => s === '[data-hntools]' ? c : null}}));"
                " console.log(JSON.stringify([MV, SCR]))")
        self.assertEqual(r, [[], [{"block": "nearest"}]])


if __name__ == "__main__":
    unittest.main()
