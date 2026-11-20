"""Pipeline tab «Tools» view hosts the Harness «Config map» (47b hnCfgHtml via 47-tools.js paintTools) — R3, plus the R4 jump from the report.
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
_REC = ("var LS = [], MV = [], SV = [], RAF = [], SCR = [], QSEL = null;"
        " function lsSet(k, v){ LS.push([k, v]); } function setMainView(v){ MV.push(v); mainView = v; } function plSetView(v){ SV.push(v); }"
        " function requestAnimationFrame(f){ RAF.push(f); }\n")
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

    def test_r3_paint_tools_order(self):
        h = _js(" TOOLS = {ok: true, items: [{id: 's1', kind: 'skill', name: 'sk', scope: 'user', path: '/p', on: true}]}; toolsAt = NOW;"
                " const box = {innerHTML: '', querySelector(){ return null; }}; mainView = 'pipe'; PLVIEW = 'tools'; paintTools(box);"
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
        r = _js(" mainView = 'pipe'; PLVIEW = 'tools'; HN.data = {}; var FEATS = {};"
                " fetch = u => Promise.resolve({status: 200, json: () => Promise.resolve({ok: true, events: []})});"
                " hnLoad('/w/a', true).then(() => console.log(JSON.stringify(PAINTS)))")
        self.assertEqual(r, 1)

    def test_r3_poll_repaint_skipped_while_focus_in_map(self):
        r = _js(" mainView = 'pipe'; PLVIEW = 'tools'; document.activeElement = {closest: s => s === '.hncfgw' ? {} : null};"
                " hnRepaint(true); const a = PAINTS; hnRepaint(); const b = PAINTS; document.activeElement = null;"
                " QSEL = s => s === '.hncfgw [title]:hover' ? {} : null; hnRepaint(true); const c = PAINTS; QSEL = null; hnRepaint(true);"
                " console.log(JSON.stringify([a, b, c, PAINTS]))")
        self.assertEqual(r, [0, 1, 1, 2])   # focus or hover holds a poll repaint; a non-poll repaint still paints

    def test_r4_report_jump_opens_tools(self):
        r = _js(" QSEL = s => s === '.hnw' ? {classList: {contains: () => false}} : null; mainView = 'pipe';"
                " hnVdGo('bad'); console.log(JSON.stringify([SV, HN.cfgOpen, MV, LS, RAF.length]))")
        self.assertEqual(r[0], ["tools"])   # R5: the jump goes through 48 plSetView (Pipelines › Tools)
        self.assertIs(r[1], True)
        self.assertEqual(r[2], [])
        self.assertIn(["sidereus.hncfg", "1"], r[3])
        self.assertEqual(r[4], 1)   # the step waits for the paint

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
        r = _js(" QSEL = s => s === '.hnw' ? {classList: {contains: () => false}} : null; mainView = 'pipe'; var ST = [];"
                " hnVdStep = l => ST.push(l); hnVdGo('bad'); PLVIEW = 'tools'; RAF.forEach(f => f()); const a = ST.slice();"
                " fetch = getJSON = u => Promise.resolve({ok: true, items: []}); getJSON = fetch;"
                " loadTools(true).then(() => { const b = ST.slice(); loadTools(true).then(() => console.log(JSON.stringify([a, b, ST, HN.vdPend]))); })",
                tools=True)
        self.assertEqual(r[0], [])   # next frame: list still loading, no step yet
        self.assertEqual(r[1], ["bad"])   # once after the list paints
        self.assertEqual(r[2], ["bad"])   # never again on a later load
        self.assertEqual(r[3], "")

    def test_r3_report_jump_steps_next_frame_when_list_loaded(self):
        r = _js(" QSEL = s => s === '.hnw' ? {classList: {contains: () => false}} : null; mainView = 'pipe'; var ST = []; TOOLS = {ok: true, items: []};"
                " hnVdStep = l => ST.push(l); hnVdGo('check'); PLVIEW = 'tools'; RAF.forEach(f => f()); console.log(JSON.stringify([ST, HN.vdPend]))",
                tools=True)
        self.assertEqual(r, [["check"], ""])

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
                " QSEL = s => s === '.tvw' ? w : null; hnVdStep('bad'); console.log(JSON.stringify([HN.vdAt.bad, CLS, SC]))")
        self.assertEqual(r, ["v7", ["hnvdon"], [{"block": "nearest", "inline": "nearest"}]])   # a list row outside .hncfgw is reached


if __name__ == "__main__":
    unittest.main()
