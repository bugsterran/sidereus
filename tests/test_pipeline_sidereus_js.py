"""«Pipelines» tab, Sidereus tool pipeline (web/js/48h-pipeline-sidereus.js): read-only arch-map chip on the target project
from state `archRun`, stages lit from the run's stage, project chip dot through plLiveProjs."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_all, js_fn
from tests._node import node_e

FNS = ("plAgHome", "plAgRun", "plAgChip", "plAgSteps", "plAgDef", "plAgStageN", "plAgOvRow", "plAgBody", "archRunOf", "archRunEl",
       "plDescStage", "plRunName", "plLiveProjs", "plLabType", "plTagNames", "plAway", "plHomes")
PRE = "\n".join([
    "const LANG = 'ko';", i18n_prelude("LANG", ("T", "KE", "U", "TV")),
    "const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));",
    "function sid8(s){ return String(s).slice(0, 8); } function ago(s){ return s + 's'; } const LOADS = [];",
    "function plLoad(p){ LOADS.push(p); } function archHome(){ return ''; }",
    "function plStepper(st, ci, mod){ return '<STEP ci=' + ci + ' mod=' + mod + '>' + st.map(x => x.st + ':' + x.nm).join(',') + '</STEP>'; }",
    "const ARCH_PL = 'arch-map'; let ARCHRUN = {}, SIDEREUS_DIR = '/sidereus', PLAG = false; const PLS = { data: {} };",
])
RUN = {"stage": "모듈 그리기", "n": 2, "of": 3, "t0": 1000, "sid": "abcdef1234"}
DEF = {"ok": True, "pipelines": [{"name": "arch-map", "title": "아키텍처 지도", "stages": [{"title": "읽기 계획"}, {"title": "모듈 그리기"}, {"title": "검증"}]}]}


def run(body):
    const = re.search(r"^const PL_DESC_RE[^\n]*$", js_all(), re.M).group(0)
    js = PRE + "\n" + const + "\n" + "\n".join(js_fn(n) for n in FNS) + "\n" + body
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PipelineSidereus(unittest.TestCase):
    def test_chip_only_with_run(self):
        r = run("const a = plAgChip(plAgRun('/t'), false); ARCHRUN = {'/t': " + json.dumps(RUN) + ", '/sidereus': " + json.dumps(RUN) + "};"
                "console.log(JSON.stringify([a, plAgChip(plAgRun('/t'), true), plAgRun('/sidereus')]));")
        self.assertEqual(r[0], "")
        self.assertIn("data-plag", r[1])
        self.assertIn("arch-map · Sidereus", r[1])
        self.assertIn("mvdot", r[1])
        self.assertIn(" on", r[1])
        self.assertIsNone(r[2])            # the Sidereus repo shows its own file, not the borrowed chip

    def test_stages_lit_and_read_only(self):
        r = run("PLS.data['/sidereus'] = " + json.dumps(DEF) + "; const b = plAgBody(" + json.dumps(RUN) + ", 1090e3);"
                "PLS.data = {}; const c = plAgBody(" + json.dumps(RUN) + ", 1090e3);"
                "console.log(JSON.stringify([b, c, LOADS]));")
        self.assertIn("<STEP ci=1 mod=lg>done:읽기 계획,run:모듈 그리기,wait:검증</STEP>", r[0])
        self.assertIn("2/3 단계 · 모듈 그리기 · 90s", r[0])
        self.assertIn("시데레우스 파이프라인 — 보기 전용", r[0])
        for k in ("data-plsave", "data-plrun", "data-pldel"):
            self.assertNotIn(k, r[0])
        self.assertIn("run:모듈 그리기", r[1])      # definition not loaded yet: current stage only, load asked
        self.assertEqual(r[2], ["/sidereus"])

    def test_running_overview_row(self):
        # «Running» list row: stage strip + n/of + elapsed from archRun (was only «Agents 0»: no plrun on the target).
        r = run("PLS.data['/sidereus'] = " + json.dumps(DEF) + "; console.log(JSON.stringify(plAgOvRow('/t', " + json.dumps(RUN) + ", 1090e3)));")
        self.assertEqual(r["name"], "arch-map")
        self.assertEqual(r["sid"], "abcdef1234")
        self.assertEqual([(s["t"], s["st"]) for s in r["stages"]], [("읽기 계획", "done"), ("모듈 그리기", "run"), ("검증", "wait")])
        self.assertEqual(r["sumh"], "2/3 단계 · 90s")

    def test_suggested_view_carries_chip(self):
        sug = "function plCanvas(){ return {html: '<CV/>'}; } function plNewBtn(){ return '<NEW/>'; } function plNewForm(){ return ''; } let PLNEW = null;"
        r = run(sug + "\n" + js_fn("plSugBody") + "\n" + js_fn("plHeadRow") + "\nconst d = {suggest: [{title: 'S', stages: []}]};"
                "ARCHRUN = {'/t': " + json.dumps(RUN) + "};"
                "console.log(JSON.stringify([plSugBody(d, plAgChip(plAgRun('/t'), false)), plSugBody(d, plAgChip(plAgRun('/u'), false))]));")
        self.assertIn("data-plag", r[0].split("</div>")[0])   # inside the chip row
        self.assertNotIn("data-plag", r[1])

    def test_project_chip_dot(self):
        r = run("ARCHRUN = {'/t': " + json.dumps(RUN) + "};"
                "console.log(JSON.stringify([plLiveProjs([], {}, {'/t': {n: 1, names: ['change']}}), (ARCHRUN = {}, plLiveProjs([], {}, null))]));")
        self.assertEqual(r[0], {"/t": ["arch-map"]})
        self.assertEqual(r[1], {})


    def test_one_run_not_also_on_sidereus_home(self):
        # a session with the Sidereus repo in its repos: its arch-map tag must not dot the home beside the target
        x = {"sid": "abcdef1234", "cwd": "/t", "repos": ["/t", "/sidereus"], "sub": [{"lab": "general-purpose: [pl:arch-map/모듈 그리기] t"}]}
        known = {"/t": {"n": 1, "names": ["change"]}, "/sidereus": {"n": 1, "names": ["arch-map"]}}
        r = run("function plTk(t){ return t; } ARCHRUN = {'/t': " + json.dumps(RUN) + "}; const x = " + json.dumps(x) + ", k = " + json.dumps(known) + ";"
                "const a = plLiveProjs([x], {}, k); ARCHRUN = {}; console.log(JSON.stringify([a, plLiveProjs([x], {}, k)]));")
        self.assertEqual(r[0], {"/t": ["arch-map"]})
        self.assertEqual(r[1], {"/sidereus": ["arch-map"]})   # no target run known: the home keeps the tag

BFNS = ("plBorrows", "plBorrowOf", "plRO", "plBorrowLab", "plBorrowChip", "plBorrowChips", "plBorrowLv", "plBorrowBody", "plCur", "plOvPick")
BPRE = "\n".join([
    "function strShort(p){ return p.slice(p.lastIndexOf('/') + 1); } let DIRTY = false; function plDirty(){ return DIRTY; } const LS = {}; function lsSet(k, v){ LS[k] = v; }",
    "let PLNEW = null, PAINTS = 0, SESS = [], PLVIEW = 'pipe'; function plPaint(){ PAINTS++; } function plLiveHead(lv){ return lv ? '<HEAD ' + lv.sid + '>' : ''; }",
    "function plRunTable(lv){ return lv ? '<TABLE/>' : ''; } let CVLT = null; function plCanvas(p, d, lt){ CVLT = lt; return {html: '<CV ' + p.name + '/>', ok: true}; }",
    "function plPrLive(r){ return Object.values(r.stages || {}).some(s => s.o === 'run'); }",
    "function plPrLv(sid, pr, st){ return {sid, pr, lt: {x: pr.name}, run: {run: plPrLive(pr)}}; }",
])
BOR = {"name": "arch-map", "ok": True, "title": "Map", "from": "/sidereus", "builtin": True, "sha": "1",
       "stages": [{"title": "읽기 계획"}, {"title": "모듈 그리기"}, {"title": "검증"}]}


def brun(body):
    return run(BPRE + "\n" + "\n".join(js_fn(n) for n in BFNS) + "\n" + body)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PipelineBorrow(unittest.TestCase):
    def test_run_row_opens_borrowed_detail(self):
        # «Running» row click (plOvPick) on a project that does not define arch-map opens the borrowed row, stages lit from archRun.
        d = {"ok": True, "pipelines": [{"name": "bugfix", "ok": True}], "borrowed": [BOR]}
        r = brun("PLS.data['/t'] = " + json.dumps(d) + "; ARCHRUN = {'/t': " + json.dumps(RUN) + "};"
                 "plOvPick('/t', 'arch-map'); const p = plCur(); const h = plBorrowBody(PLS.data['/t'], p, '<L/>');"
                 "console.log(JSON.stringify([p.name, p.from, h, CVLT]));")
        self.assertEqual(r[:2], ["arch-map", "/sidereus"])
        self.assertIn("<CV arch-map/>", r[2])
        self.assertIn("<HEAD abcdef1234>", r[2])
        self.assertIn("<TABLE/>", r[2])
        self.assertIn("/sidereus에 정의됨 — 여기서는 보기 전용", r[2])
        for k in ("data-plsave", "data-plrun", "data-pldel"):
            self.assertNotIn(k, r[2])
        self.assertEqual({k: v["st"] for k, v in r[3].items()}, {"읽기 계획": "done", "모듈 그리기": "run", "검증": "wait"})

    def test_read_only_canvas(self):
        # Borrowed view: plRO gates the canvas edit handlers (48d); even after a stray edit no «Undo»/Save shows.
        d = {"ok": True, "pipelines": [{"name": "bugfix", "ok": True}], "borrowed": [BOR]}
        r = brun("PLS.data['/t'] = " + json.dumps(d) + "; PLS.proj = '/t'; PLS.sel = 'bugfix'; const own = plRO();"
                 "PLS.sel = 'arch-map'; DIRTY = true; const h = plBorrowBody(PLS.data['/t'], plCur(), '');"
                 "console.log(JSON.stringify([own, plRO(), h]));")
        self.assertEqual(r[:2], [False, True])
        for k in ("data-plreset", "data-plsave"):
            self.assertNotIn(k, r[2])
        with open(os.path.join(os.path.dirname(__file__), "..", "web", "js", "48d-pipeline-cv-input.js"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("if(node && plRO()){ E.sel", src)                    # node press selects, never drags or connects
        self.assertIn("if(E && E.sel && !plRO())", src)                    # Delete key
        self.assertIn("if(!E || !e.dataTransfer || plRO()) return;", src)  # palette drop
        self.assertIn("if(pan && plRO()) return;", src)                    # panel change

    def test_chips_live_borrowed_only(self):
        # Borrowed pipelines leave the combobox; one head-row chip per borrowed pipeline RUNNING here, none for an ended run.
        d = {"ok": True, "pipelines": [], "borrowed": [BOR, {"name": "deploy", "from": "/w/app", "ok": True}, {"name": "old", "from": "/w/app", "ok": True}]}
        r = brun("PLS.data['/t'] = " + json.dumps(d) + "; PLS.proj = '/t'; ARCHRUN = {'/t': " + json.dumps(RUN) + "};"
                 "SESS = [{sid: 'x', cwd: '/t', plrun: [{name: 'deploy', proj: '/w/app', t1: 5, stages: {a: {o: 'run'}}},"
                 "  {name: 'old', proj: '/w/app', t1: 9, stages: {a: {o: 'done'}}}]}];"
                 "const a = plBorrowChips(PLS.data['/t']); PLS.sel = 'deploy'; const b = plBorrowChips(PLS.data['/t']);"
                 "ARCHRUN = {}; SESS = []; const c = plBorrowChips(PLS.data['/t']);"
                 "console.log(JSON.stringify([a, b, c]));")
        a, b, c = r
        self.assertEqual(a.count("data-plbor="), 2)
        self.assertIn('data-plbor="arch-map"', a)
        self.assertIn("arch-map · Sidereus 내장", a)
        self.assertIn("deploy · app에서", a)
        self.assertIn("mvdot", a)
        self.assertNotIn('data-plbor="old"', a)                    # listed by the server, run ended: no chip
        self.assertNotIn(" on", a)
        self.assertIn('plbor on" data-plbor="deploy"', b)          # selected chip is on
        self.assertEqual(c, "")                                    # no live run: no chip

    def test_plrun_lighting_from_session_in_project(self):
        r = brun("SESS = [{sid: 'x', cwd: '/t', plrun: [{name: 'deploy', proj: '/w/app', t1: 5, stages: {}}]},"
                 "{sid: 'y', cwd: '/u', plrun: [{name: 'deploy', proj: '/w/app', t1: 9, stages: {}}]}];"
                 "const p = {name: 'deploy', from: '/w/app', stages: []};"
                 "console.log(JSON.stringify([plBorrowLv('/t', p).sid, plBorrowLv('/v', p)]));")
        self.assertEqual(r, ["x", None])


if __name__ == "__main__":
    unittest.main()
