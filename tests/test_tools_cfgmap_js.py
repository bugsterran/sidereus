"""Harness «Config map» (47b hnCfgHtml, a fold in the report) and the Tools tab list (47-tools.js paintTools) — R3: «Check results» steps cross both.
Claude Code skill/MCP rows: no Config map boxes (R1), stage chips (R2) and check results (R3) on the Tools list rows joined by `tid`."""
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
_NX = os.path.join(ROOT, "web", "js", "47g-harness-next.js")
# Recorders replace the plain stubs: localStorage writes, view switches, repaints and the next-frame callback.
_REC = ("var LS = [], MV = [], SV = [], TLV = [], TLP = [], RAF = [], SCR = [], QSEL = null, TLVIEW = 'tools';"
        " function lsSet(k, v){ LS.push([k, v]); } function setMainView(v){ MV.push(v); mainView = v; }"
        " function plSetView(v){ SV.push(v); mainView = 'pipe'; PLVIEW = v; } function tlSetView(v){ TLV.push(v); mainView = 'tools'; TLVIEW = v; }"
        " function tlPaint(p){ TLP.push(p); } function requestAnimationFrame(f){ RAF.push(f); }\n")
# Fake views: rows of level bad in the Harness fold (.hncfgw) and the Tools tab list (.tvw); RUN() fires the queued next frames.
_ROWS = ("const ROW = id => ({dataset: {hnvd: id}, closest(){ return null; }, classList: {add(){}, remove(){}}, scrollIntoView(){}});"
         " const BOX = ids => { const rs = ids.map(ROW); return {querySelectorAll(s){ return s === '[data-hnvdl=\"bad\"]' ? rs : []; }}; };"
         " var VIEWS = {}; QSEL = s => VIEWS[s] || null; const RUN = () => RAF.splice(0).forEach(f => f());")
_DOC = ("const LST = {}; const document = {addEventListener(t, f){ (LST[t] = LST[t] || []).push(f); },"
        " querySelector(s){ return QSEL ? QSEL(s) : null; }};\n")
_DATA = {"ok": True, "events": [{"ev": "Stop", "hooks": [{"cmd": "c.sh", "n": 3, "vd": {"lvl": "bad", "why": "hook_missing", "id": "v1"}}]}],
         "rules": [{"path": "/w/a/AGENTS.md", "order": 1}], "agents": [{"name": "impl", "scope": "project"}],
         "mcps": [{"name": "m1", "scope": "user"}], "skills": [{"name": "sk", "scope": "user"}],
         "counts": {"skill": 1, "cmd": 2, "mcp": 3}, "evidence": [], "verdict": {"bad": 1, "check": 0, "ok": 4}}


def _js(body, stub=_STUB, tools=False, nx=False):
    src = stub.replace("function lsSet(){} function plPaint(){ PAINTS++; } function setMainView(){}", "function plPaint(){ PAINTS++; }")
    src += _REC + i18n_switch() + _DOC
    for p in ([_TL] if tools else []) + [_HN] + ([_NX] if nx else []):
        with open(p, encoding="utf-8") as f:
            src += f.read() + "\n"
    pre = "HN.data[hnKey('/w/a')] = %s; HN.at[hnKey('/w/a')] = NOW; HN.plats = ['cc', 'cx'];" % json.dumps(_DATA)
    return json.loads(subprocess.run(node_e(src + pre + body), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


class ToolsConfigMap(unittest.TestCase):
    def test_r3_fold_contents(self):
        cc, cx = _js(" TOOLS = {ok: true, items: []}; const a = hnCfgHtml(PLS.proj); HN.plat = 'cx'; HN.data[hnKey('/w/a')] = HN.data['cc\\n/w/a'];"
                     " console.log(JSON.stringify([a, hnCfgHtml(PLS.proj)]))", tools=True)
        self.assertTrue(cc.startswith('<div class="hnw hncfgw"><details class=hncfg'))
        for t in ("구성 지도", "data-hnflow", "규칙 파일", "에이전트 ↔ 파이프라인", "data-hnplat", "data-hnvdgo=bad"):
            self.assertIn(t, cc)
            self.assertIn(t, cx)
        # R1: under Claude Code the skill/MCP boxes and count buttons are gone (the Tools list below carries those rows)
        for t in ("MCP 서버", ">sk<", ">m1<", "<b>스킬</b>", "class=hncnt", "data-hntools"):
            self.assertNotIn(t, cc)
        for t in ("MCP 서버", ">sk<", ">m1<", "<b>스킬</b>"):
            self.assertIn(t, cx)   # other CLIs keep them: the Tools list only reads Claude Code
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

    def test_r3_paint_tools_no_map_but_loads_harness(self):
        h, none, urls = _js(" TOOLS = {ok: true, items: [{id: 's1', kind: 'skill', name: 'sk', scope: 'user', path: '/p', on: true}]}; toolsAt = NOW;"
                            " const box = {innerHTML: '', querySelector(){ return null; }}; mainView = 'tools'; paintTools(box); const a = box.innerHTML;"
                            " HN.data = {}; HN.at = {}; paintTools(box); console.log(JSON.stringify([a, box.innerHTML, URLS]))", tools=True)
        self.assertNotIn("hncfg", h)   # the map is a fold in the Harness report now
        self.assertLess(h.index("wvht"), h.index("class=hnvdl>"))   # check line above the list: stepping continues here
        self.assertLess(h.index("class=hnvdl>"), h.index("class=tvwg"))
        self.assertNotIn("class=hnvdl>", none)   # no harness data: no line, never «0»
        self.assertEqual([u for u in urls if u.startswith("/api/harness?")], ["/api/harness?plat=cc&proj=%2Fw%2Fa&days=30"])   # paintTools loads it itself

    def test_r3_feature_off_and_no_project(self):
        off, none = _js(" var FEATS = {harness: false}; const a = hnCfgHtml(PLS.proj); FEATS.harness = true;"
                        " console.log(JSON.stringify([a, hnCfgHtml('')]))")
        self.assertEqual(off, "")
        self.assertIn("파이프라인 탭에서 프로젝트를 고르세요", none)
        self.assertNotIn("data-hnflow", none)

    def test_r3_load_repaints_tools_tab(self):
        r = _js(" mainView = 'tools'; HN.data = {}; var FEATS = {};"
                " fetch = u => Promise.resolve({status: 200, json: () => Promise.resolve({ok: true, events: []})});"
                " hnLoad('/w/a', true).then(() => console.log(JSON.stringify([PAINTS, TLP])))")
        self.assertEqual(r, [0, [True]])   # poll-style: 47a tlPaint holds it while focus/hover is inside .tvw

    def test_r3_repaint_routes_by_tab(self):
        r = _js(" hnRepaint(true); const a = [PAINTS, TLP.length]; mainView = 'tools'; hnRepaint(); hnRepaint(true); TLVIEW = 'conn'; hnRepaint();"
                " console.log(JSON.stringify([a, PAINTS, TLP]))")
        self.assertEqual(r, [[1, 0], 1, [False, True]])   # Harness → plPaint; Tools list → tlPaint; Session tools → neither

    def test_r3_step_past_map_lands_on_list_and_back(self):
        r = _js(_ROWS + " TOOLS = {ok: true, items: []}; HN.data[hnKey('/w/a')].verdict.bad = 3; VIEWS = {'.hncfgw': BOX(['h1', 'h2']), '.tvw': BOX(['t1'])};"
                " const at = []; const go = () => { hnVdGo('bad'); at.push(HN.vdAt.bad || ''); };"
                " go(); go(); go(); const a = [TLV.slice(), HN.vdPend, RAF.length]; RUN(); at.push(HN.vdAt.bad);"
                " go(); RUN(); at.push(HN.vdAt.bad); console.log(JSON.stringify([at, a, TLV, SV, MV, HN.vdPend]))", tools=True)
        self.assertEqual(r[0], ["h1", "h2", "", "t1", "", "h1"])   # map rows, then the list's first row, then back to the map's first
        self.assertEqual(r[1], [["tools"], "bad", 1])   # past the last map row: 47a tlSetView, the step waits one frame
        self.assertEqual(r[2], ["tools"])
        self.assertEqual(r[3], ["harness"])   # past the last list row: 48 plSetView back to the report
        self.assertEqual(r[4], [])
        self.assertEqual(r[5], "")

    def test_r3_step_wraps_when_view_holds_every_row(self):
        r = _js(_ROWS + " HN.data[hnKey('/w/a')].verdict.bad = 2; VIEWS = {'.hncfgw': BOX(['h1', 'h2'])}; const at = [];"
                " for(let i = 0; i < 3; i++){ hnVdGo('bad'); at.push(HN.vdAt.bad); } console.log(JSON.stringify([at, TLV, SV, RAF.length]))")
        self.assertEqual(r, [["h1", "h2", "h1"], [], [], 0])   # Tools list never loaded: the map draws every row, no jump

    def test_r3_arrival_with_no_rows_stops(self):
        r = _js(_ROWS + " TOOLS = {ok: true, items: []}; HN.data[hnKey('/w/a')].verdict.bad = 3; VIEWS = {'.hncfgw': BOX(['h1'])};"
                " hnVdGo('bad'); hnVdGo('bad'); VIEWS['.hncfgw'] = null; VIEWS['.tvw'] = BOX([]); RUN();"
                " console.log(JSON.stringify([TLV, SV, RAF.length, HN.vdAt.bad || '', HN.vdPend]))", tools=True)
        self.assertEqual(r, [["tools"], [], 0, "", ""])   # 0 rows on arrival: nothing, no jump back

    def _paint(self, js):
        return _js(" TOOLS = {ok: true, items: [{id: 's1', kind: 'skill', name: 'sk', scope: 'user', path: '/p', on: true},"
                   " {id: 'm1', kind: 'mcp', name: 'm1', scope: 'user', path: '/q', on: true}]}; toolsAt = NOW;"
                   " const box = {innerHTML: '', querySelector(){ return null; }}; mainView = 'pipe'; PLVIEW = 'tools';"
                   " const D = HN.data[hnKey('/w/a')];" + js + " paintTools(box); console.log(JSON.stringify(box.innerHTML))", tools=True)

    def test_r2_skill_row_stage_chip(self):
        h = self._paint(" D.skills = [{name: 'sk', scope: 'user', tid: 's1', pipes: [{pipe: 'p', stage: 's'}]},"
                        " {name: 'gone<x>', scope: '', tid: '', n: 0, pipes: [{pipe: 'p', stage: 't'}],"
                        "  vd: {lvl: 'bad', why: 'ref_missing', vp: {pipe: 'p', stage: 't'}, id: 'v7'}}];")
        row = h.split('data-tid="s1"', 1)[1].split("</tr>", 1)[0]
        self.assertIn('<td class="brn tvwnp">sk <span class=hnpc title="p / s">p · s</span></td>', row)
        miss = h.split('<tr class="tvwr tvwmiss hnvd hnvd-bad"', 1)[1].split("</tr>", 1)[0]
        self.assertNotIn("data-tid", miss)   # not installed: shown, never clickable
        self.assertNotIn("tabindex", miss)
        self.assertIn("gone&lt;x&gt;", miss)
        self.assertIn("설치 안 됨", miss)
        self.assertIn('<span class=hnpc title="p / t">p · t</span>', miss)
        self.assertIn("data-hnvdl=bad", miss)
        self.assertNotIn("<x>", h)
        self.assertLess(h.index('data-tid="s1"'), h.index("tvwmiss"))   # leftovers close their kind's section

    def test_r3_step_ends_tab_scroll_restore(self):
        # 92 mvScrollBack re-applies the tab's saved scrollTop for up to 4s after a tab switch; a hand-off step must end it first.
        with open(_HN, encoding="utf-8") as f:
            hn = f.read()
        step = hn.split("function hnVdStep(", 1)[1].split("\nfunction ", 1)[0]
        self.assertLess(step.index("mvScrollStop()"), step.index("scrollIntoView"))
        with open(os.path.join(ROOT, "web", "js", "92-mainview-tabs.js"), encoding="utf-8") as f:
            mv = f.read()
        self.assertIn("function mvScrollStop(){ ++mvScrollSeq; }", mv)
        self.assertIn("seq !== mvScrollSeq", mv)   # the restore loop stops when the sequence moves on

    def test_r2_list_chip_never_wider_than_name_cell(self):
        # 41b caps .hnpc at 220px nowrap; at 900px the Name cell is ~145px, so the list rule must cap chips to the cell.
        with open(os.path.join(ROOT, "web", "css", "41-tools.css"), encoding="utf-8") as f:
            css = f.read()
        rule = css.split(".tvwt .hnpc{", 1)[1].split("}", 1)[0]
        self.assertIn("max-width:100%", rule)
        self.assertIn("box-sizing:border-box", rule)

    def test_r2_no_harness_no_decoration(self):
        for js in (" HN.data = {}; HN.at = {};", " HN.data[hnKey('/w/a')] = {ok: false, msg: 'x'};", " HN.plat = 'cx';"):
            h = self._paint(js)
            self.assertIn('data-tid="s1"', h)
            for t in ("hnpc", "tvwmiss", "data-hnvdl", "tvwvdr"):
                self.assertNotIn(t, h, js)   # unknown harness: plain rows, never «not installed»

    def test_r3_flagged_mcp_row_in_list(self):
        h = self._paint(" D.mcps = [{name: 'm1', scope: 'user', tid: 'm1', status: 'fail', vd: {lvl: 'bad', why: 'mcp_fail', vp: {name: 'm1'}, id: 'v3'}},"
                        " {name: 'lost', scope: 'user', tid: 'mx', vd: {lvl: 'check', why: 'mcp_fail', vp: {}, id: 'v4'}}, {name: 'fine', scope: 'user', tid: 'my'}];"
                        " D.skills = [];")
        self.assertIn('<tr class="tvwr hnvd hnvd-bad" data-tid="m1" tabindex=0 data-hnvd="v3" data-hnvdl=bad>', h)
        vr = h.split('data-tid="m1"', 1)[1].split("</tr>", 2)[1]
        self.assertTrue(vr.startswith('<tr class=tvwvdr><td colspan=7><span class="hnvdr hnvd-bad">'), vr)
        self.assertIn('<tr class="tvwr tvwmiss hnvd hnvd-check" data-hnvd="v4" data-hnvdl=check>', h)   # flagged, not listed: still reachable
        self.assertNotIn(">fine<", h)   # an unflagged server with no list item is not added
        self.assertEqual(h.split("class=tvwg", 1)[1].count("data-hnvdl="), 2)   # list rows only (the Config map keeps its hook row)

    def test_r3_cc_boxes_until_tools_list_is_ok(self):
        r = _js(" const a = hnCfgHtml(PLS.proj); TOOLS = {ok: false, msg: 'x'}; const b = hnCfgHtml(PLS.proj);"
                " TOOLS = {ok: true, items: []}; console.log(JSON.stringify([a, b, hnCfgHtml(PLS.proj)]))", tools=True)
        for h in r[:2]:
            self.assertIn("MCP 서버", h)   # list not loaded / failed: the flagged rows stay reachable in Config map
            self.assertIn(">sk<", h)
        self.assertNotIn("MCP 서버", r[2])   # list ok: drawn once, in the list

    def test_r3_report_jump_waits_for_tools_list(self):
        r = _js(_ROWS + " HN.data[hnKey('/w/a')].verdict.bad = 3; VIEWS = {'.hncfgw': BOX([])}; var ST = [];"
                " hnVdStep = l => ST.push(l); hnVdGo('bad'); RAF.forEach(f => f()); const a = ST.slice();"
                " fetch = getJSON = u => Promise.resolve({ok: true, items: []}); getJSON = fetch;"
                " loadTools(true).then(() => { const b = ST.slice(); loadTools(true).then(() => console.log(JSON.stringify([a, b, ST, HN.vdPend]))); })",
                tools=True)
        self.assertEqual(r[0], [])   # next frame: list still loading, no step yet
        self.assertEqual(r[1], ["bad"])   # once after the list paints
        self.assertEqual(r[2], ["bad"])   # never again on a later load
        self.assertEqual(r[3], "")

    def test_r3_report_jump_steps_next_frame_when_list_loaded(self):
        r = _js(_ROWS + " HN.data[hnKey('/w/a')].verdict.check = 1; VIEWS = {'.hncfgw': BOX([])}; var ST = []; TOOLS = {ok: true, items: []};"
                " hnVdStep = l => ST.push(l); hnVdGo('check'); RAF.forEach(f => f()); console.log(JSON.stringify([ST, HN.vdPend, TLV]))",
                tools=True)
        self.assertEqual(r, [["check"], "", ["tools"]])

    def test_r3_next_step_fold_works_in_tools_list(self):
        r = _js(" var PS = 0; const sel = (x, k) => s => s.split(', ').includes(k) ? x : null;"
                " LST.click.forEach(f => f({stopPropagation(){ PS++; }, target: {closest: s => s === '[data-hnnxd]' ? {dataset: {hnnxd: 'k'}}"
                " : sel({}, '.tvw .hnnx')(s)}}));"
                " HN_NXS.dr = {sid: 'a'}; LST.change.forEach(f => f({target: {closest: sel({value: 'b'}, '.tvw [data-hnnxs]')}}));"
                " console.log(JSON.stringify([PS, HN_NXS.dr.sid]))", nx=True)
        self.assertEqual(r, [1, "b"])   # «Draft instruction» click and recipient pick reach 47g from a Tools list row

    def test_r3_step_finds_list_row(self):
        r = _js(" const CLS = [], SC = []; const el = {dataset: {hnvd: 'v7'}, closest(){ return null; }, classList: {add(c){ CLS.push(c); }},"
                " scrollIntoView(o){ SC.push(o); }};"
                " const w = {querySelectorAll(s){ return s === '[data-hnvdl=\"bad\"]' ? [el] : []; }};"
                " QSEL = s => s === '.tvw' ? w : null; mainView = 'tools'; hnVdStep('bad'); console.log(JSON.stringify([HN.vdAt.bad, CLS, SC]))")
        self.assertEqual(r, ["v7", ["hnvdon"], [{"block": "nearest", "inline": "nearest"}]])   # a list row outside .hncfgw is reached


if __name__ == "__main__":
    unittest.main()
