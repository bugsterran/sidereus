"""«파이프라인» canvas model (web/js/48c-pipeline-graph.js): graph <-> stages, chain order, loop-back -> onFail, checks.
Pure functions only, run under node."""
import json
import os
import re
import subprocess
import unittest

from tests._load import ROOT, js_all, js_fn
from tests._node import node_e

FNS = ("plTk", "plgFrom", "plgNode", "plgOrder", "plgStages", "plgKey", "plgCheck", "plgRemove", "plgConnect", "plgAdd", "plgLayout",
       "plgInsert", "plgLoopLanes", "plgLoopPath", "plgGap", "plgRowH", "plgCols", "plgFlowPath", "plgRulesSplit", "plgRulesJoin", "plDraftText", "plgSlots", "plgFam", "plgChain", "plgLine", "plgMove", "plgInsertAt", "plgPathPts", "plgEdgeAt", "plMarkers", "plHeadsSvg", "plgColor", "plgW", "plgH", "plgSumW", "plgPush", "plgRows", "plgAlign", "plVG",
       "plgTpl", "plgHue", "plgPfc", "plgAddTpl", "plgGraded", "plgGuards", "plgShow", "plgBase", "plgFreeTitle")


def _js(body):
    src = js_all()
    consts = "\n".join(re.search(r"^const %s[^\n]*$" % c, src, re.M).group(0)
                       for c in ("PLG_TITLES", "PLG_MODELS", "PLG_KEYS", "PLG_W", "PLG_GFAM"))
    consts += "\n" + re.search(r"^const PLG_FAM = [\s\S]*?\};$", src, re.M).group(0)
    consts += "\n" + re.search(r"^const PLG_RULES = [\s\S]*?\]\];$", src, re.M).group(0)
    # plgCheck messages go through T()/TV(); English source is enough here (Korean is pinned by the dictionary).
    i18n = "const T = s => s; const TV = j => j.msg.replace(/\\{(\\w+)\\}/g, (a, k) => k in j.vars ? String(j.vars[k]) : a);"
    # plgShow: a minimal English stage-name table (the real one is 06-i18n-w.js PLG_NAMES).
    i18n += "\nvar LANG = 'en'; const PLG_NAMES = {en: {'설계': 'Design', '구현': 'Implement', '검증': 'Verify', '리뷰': 'Review'}};"
    code = i18n + "\n" + consts + "\n" + "\n".join(js_fn(f) for f in FNS) + "\n{\n" + body + "\n}\n"   # block: a test may declare its own T
    return json.loads(subprocess.run(node_e(code), capture_output=True, text=True, check=True).stdout)


P = {"name": "demo", "defaults": {"model": "inherit", "retry": 0}, "stages": [
    {"title": "설계", "agent": "designer", "instr": "spec", "produces": "slices"},
    {"title": "구현", "agent": "impl", "fanout": "slices"},
    {"title": "검증", "agent": "verifier", "model": "sonnet", "onFail": {"goto": "구현", "max": 2}},
    {"title": "리뷰", "agent": "reviewer", "onFail": {"goto": "구현", "max": 1, "then": "재검증"}},
    {"title": "재검증", "agent": "verifier", "onlyOnJump": True}]}


def run(ops):
    return _js("const G = plgFrom(%s);\n%s" % (json.dumps(P), ops))


class Graph(unittest.TestCase):
    def test_round_trip(self):
        out = run("const c = plgCheck(G); console.log(JSON.stringify({errs: c.errs, st: plgStages(G, c.order)}));")
        self.assertEqual(out["errs"], [])
        want = [dict(s, ui={"x": 44 + i * 248, "y": 24}) for i, s in enumerate(P["stages"])]
        self.assertEqual(out["st"], want)

    def test_reorder_by_edges(self):
        # rewire 설계 -> 검증 -> 구현? no: move 리뷰 before 검증 by edges: 구현 -> 리뷰 -> 검증 -> 재검증
        out = run("G.flow = [['n1','n2'],['n2','n4'],['n4','n3'],['n3','n5']]; G.loops = G.loops.filter(l => l.from !== 'n4');"
                  "const c = plgCheck(G); console.log(JSON.stringify({errs: c.errs, t: plgStages(G, c.order).map(s => s.title)}));")
        self.assertEqual(out["t"], ["설계", "구현", "리뷰", "검증", "재검증"])
        self.assertEqual(out["errs"], [])

    def test_branch_merge_cycle(self):
        out = run("plgConnect(G, 'flow', 'n5', 'n1'); const a = plgCheck(G).errs.map(e => e.msg);"
                  "G.flow.push(['n1','n3']); const b = plgCheck(G).errs.map(e => e.msg);"
                  "console.log(JSON.stringify({a, b}));")
        self.assertTrue(any(m.startswith("Cycle") for m in out["a"]), out["a"])
        self.assertTrue(any(m.startswith("Branch") for m in out["b"]) and any(m.startswith("Merge") for m in out["b"]), out["b"])

    def test_messages_show_stage_names_not_ids(self):
        # Cycle back to a stage names it (was the node id «n2»); built-in titles in English, custom titles as typed.
        out = run("G.flow.push(['n5','n2']); const a = plgCheck(G).errs.map(e => e.msg);"
                  "plgNode(G, 'n1').agent = 'bad name'; plgNode(G, 'n2').title = 'My step'; const b = plgCheck(G).errs.map(e => e.msg);"
                  "LANG = 'ko'; plgNode(G, 'n2').title = '구현'; const c = plgCheck(G).errs.map(e => e.msg);"
                  "console.log(JSON.stringify({a, b, c}));")
        self.assertIn("Cycle: the flow returns to Implement — connect loop-backs with the bottom port", out["a"])
        self.assertIn("Merge: two paths lead into Implement", out["a"])
        self.assertFalse(any("n2" in m for m in out["a"]), out["a"])
        self.assertIn("Merge: two paths lead into My step", out["b"])
        self.assertIn("Design: the agent name is not valid", out["b"])
        self.assertIn("Merge: two paths lead into 구현", out["c"])

    def test_loop_back_to_onfail(self):
        out = run("plgConnect(G, 'loop', 'n4', 'n1'); const c = plgCheck(G);"
                  "console.log(JSON.stringify({f: plgStages(G, c.order)[3].onFail, errs: c.errs}));")
        self.assertEqual(out["f"], {"goto": "설계", "max": 1, "then": "재검증"})   # replaced; max/then kept
        out = run("plgConnect(G, 'loop', 'n1', 'n3'); console.log(JSON.stringify(plgCheck(G).errs.map(e => e.msg)));")
        self.assertTrue(any("earlier stage" in m for m in out))

    def test_remove_relinks(self):
        out = run("plgRemove(G, 'n3'); const c = plgCheck(G); const s = plgStages(G, c.order);"
                  "console.log(JSON.stringify({t: s.map(x => x.title), errs: c.errs}));")
        self.assertEqual(out["t"], ["설계", "구현", "리뷰", "재검증"])
        self.assertEqual(out["errs"], [])

    def test_add_and_checks(self):
        out = run("const id = plgAdd(G, '회귀', '', 10, 300); const n = plgNode(G, id); n.agent = 'Bad Name';"
                  "const c = plgCheck(G); console.log(JSON.stringify({t: plgStages(G, c.order).map(x => x.title), e: c.errs.map(x => x.msg)}));")
        self.assertEqual(out["t"][-1], "회귀")
        self.assertTrue(any("agent name" in m for m in out["e"]))
        out = run("G.nodes[1].title = '설계'; console.log(JSON.stringify(plgCheck(G).errs.map(e => e.msg)));")
        self.assertTrue(any("twice" in m for m in out))

    def test_insert_after_selected(self):
        out = run("const id = plgInsert(G, '원인', 'n2'); const c = plgCheck(G);"
                  "console.log(JSON.stringify({t: plgStages(G, c.order).map(s => s.title), e: c.errs, x: [plgNode(G, id).ui.x, plgNode(G, 'n3').ui.x]}));")
        self.assertEqual(out["t"], ["설계", "구현", "원인", "검증", "리뷰", "재검증"])
        self.assertEqual(out["e"], [])
        self.assertEqual(out["x"], [44 + 2 * 248, 44 + 3 * 248])        # later nodes shifted right

    def test_loop_lanes_distinct(self):
        out = run("const L = plgLoopLanes(G); console.log(JSON.stringify(G.loops.map((l, i) => L[i])));")
        self.assertEqual([l["k"] for l in out], [0, 1])                  # shorter span (검증->구현) nearer the boxes
        self.assertLess(out[0]["y"], out[1]["y"])
        self.assertGreaterEqual(out[0]["y"], 24 + 100 + 34)

    def test_gap_fits_width(self):
        out = _js("console.log(JSON.stringify([plgGap(5, 3000), plgGap(5, 1100), plgGap(5, 600), plgGap(1, 100)]));")
        self.assertEqual(out, [64, 28, 28, 64])

    def test_rules_split_join(self):
        out = _js("const r = plgRulesSplit('Never commit or push.\\nkeep A\\nNever restart servers or services.');"
                  "console.log(JSON.stringify([r, plgRulesJoin(r.on, r.free), plgRulesJoin([], '  ')]));")
        self.assertEqual(out[0], {"on": [0, 1], "free": "keep A"})
        self.assertEqual(out[1], "Never restart servers or services.\nNever commit or push.\nkeep A")
        self.assertEqual(out[2], "")

    def test_rule_file_lines(self):
        out = _js("const L = PLG_RULES.concat([['x', 'Follow AGENTS.md in the repo.', 'AGENTS.md']]);"
                  "const r = plgRulesSplit('Follow AGENTS.md in the repo.\\nkeep A\\nFollow AGENTS.md in the repo.', L);"
                  "console.log(JSON.stringify([r, plgRulesJoin(r.on, r.free, L), plgRulesJoin([], r.free, L)]));")
        self.assertEqual(out[0], {"on": [5], "free": "keep A"})
        self.assertEqual(out[1], "Follow AGENTS.md in the repo.\nkeep A")        # ticked twice -> one line
        self.assertEqual(out[2], "keep A")                                        # unticked -> exactly that line gone

    def test_families(self):
        out = _js("console.log(JSON.stringify(['설계', '구현', '회귀', '리뷰', '배포 준비'].map(plgFam)));")
        self.assertEqual(out, ["plan", "build", "check", "review", "cust"])

    def test_draft_from_workflow(self):
        t = _js("console.log(JSON.stringify(plDraftText('mig', '…', [], PLG_TITLES, 'sidereus-change.js')));")
        self.assertTrue(t.startswith("파이프라인 초안 요청 — .claude/workflows/sidereus-change.js 옮기기\nRead .claude/workflows/sidereus-change.js"))
        self.assertIn("Do not run either and do not commit.", t)
        self.assertIn("custom stage", t)

    def test_draft_from_rule_doc(self):
        t = _js("console.log(JSON.stringify(plDraftText('flow', '…', ['impl'], PLG_TITLES, 'doc:AGENTS.md')));")
        self.assertTrue(t.startswith("파이프라인 초안 요청 — AGENTS.md 에서 옮기기\nRead AGENTS.md in this repo, find the work/delegation flow"))
        self.assertIn("write .claude/pipelines/flow.json", t)
        self.assertIn("Do not run it and do not commit.", t)
        self.assertIn("Agents here: impl", t)

    def test_draft_dm_text(self):
        t = _js("console.log(JSON.stringify(plDraftText('bugfix', '버그 고치는 절차', ['a-b'], PLG_TITLES)));")
        self.assertTrue(t.startswith("파이프라인 초안 요청 — '버그 고치는 절차'\nWrite .claude/pipelines/bugfix.json"))
        self.assertIn("Do not run it and do not commit.", t)
        self.assertIn('"name":"bugfix"', t)
        self.assertIn("Agents here: a-b", t)
        self.assertIn("설계 · 구현", t)

    def test_draft_names_project(self):
        t = _js("console.log(JSON.stringify(plDraftText('bugfix', 'x', [], PLG_TITLES, '', '/Users/me/work/my-app/')));")
        self.assertTrue(t.startswith("Project: my-app (/Users/me/work/my-app)\n파이프라인 초안 요청 — 'x'\n"))
        w = _js("console.log(JSON.stringify(plDraftText('b', 'x', [], PLG_TITLES, 'doc:AGENTS.md', 'C:\\\\src\\\\proj')));")
        self.assertTrue(w.startswith("Project: proj (C:\\src\\proj)\n"))

    def test_draft_stage_lines_skills_rules(self):
        ctx = {"tasks": {"설계": "Read the request; change nothing. PASS when done.\nmore", "구현": "x" * 200, "zz": "not a title"},
               "skills": ["s%d" % i for i in range(45)]}
        t = _js("console.log(JSON.stringify(plDraftText('b', 'x', [], PLG_TITLES, '', '', %s)));" % json.dumps(ctx))
        self.assertIn("\n  설계 — Read the request; change nothing.\n", t)           # first sentence only
        self.assertIn("\n  구현 — " + "x" * 119 + "…\n", t)                          # capped at 120
        self.assertNotIn("zz", t)                                                     # only recommended titles
        self.assertNotIn("  검증 —", t)                                                # no task -> no line
        self.assertIn("Skills here (optional \"skill\" per stage): s0, s1", t)
        self.assertIn("s39 (+5 more)\n", t)
        self.assertNotIn("s40", t)
        self.assertIn("Rules: docs/EXTENDING.md › Pipeline, if present in this repo.", t)
        bare = _js("console.log(JSON.stringify(plDraftText('b', 'x', [], PLG_TITLES)));")
        self.assertIn("Skills here (optional \"skill\" per stage): (none)", bare)

    def test_draft_ctx_scopes_skills(self):
        out = _js(js_fn("plDraftCtx") + "\nvar PLS = {projs: {projects: [{path: '/w/other'}]}, data: {'/w/app': {}}};"
                  "\nfunction plPickSkills(sk, cur, proj, projs){ return (sk || []).filter(k => k.scope === 'project').concat([{name: projs.join('|')}]); }"
                  "\nconsole.log(JSON.stringify([plDraftCtx({skills: [{name: 'own', scope: 'project'}, {name: 'u', scope: 'user'}], default_tasks: {'설계': 'a'}}, '/w/app'), plDraftCtx(null, '/w/app')]));")
        self.assertEqual(out[0], {"tasks": {"설계": "a"}, "skills": ["own", "/w/other|/w/app"]})
        self.assertEqual(out[1], {"tasks": {}, "skills": ["/w/other|/w/app"]})
        src = open(os.path.join(ROOT, "web", "js", "48e-pipeline-new.js"), encoding="utf-8").read()
        self.assertEqual(src.count("PLS.proj, plDraftCtx(d, PLS.proj))"), 3)   # preview, live refresh, sent body

    def test_draft_session_option(self):
        out = _js(js_fn("plDraftOpt") + "\nconst sid8 = s => String(s).slice(0, 8);"
                  "\nconsole.log(JSON.stringify([plDraftOpt({project: 'app', id: 's-app', doing: 'Fix the login bug', sid: 'abcdef1234', model: 'opus', login: true}),"
                  " plDraftOpt({project: 'app', id: '', doing: '', sid: 'abcdef1234', model: '', login: false}),"
                  " plDraftOpt({project: 'app', id: 'm', doing: 'y'.repeat(60), sid: 'abcdef1234', model: 'opus', login: true})]));")
        self.assertEqual(out[0], "app · s-app · Fix the login bug · abcdef12 · opus")
        self.assertEqual(out[1], "app · abcdef12 · not logged in to the mailbox")
        self.assertEqual(out[2], "app · m · " + "y" * 47 + "… · abcdef12 · opus")

    def test_draft_agents_use_picker(self):
        # plPickAgents (48b) is stubbed: the draft must take its names, not the raw project agent list.
        out = _js(js_fn("plDraftAgents") + "\nfunction plPickAgents(ag, cur, proj){ return (ag || []).filter(a => a.scope === 'project' || a.name.startsWith(String(proj).split('/').pop() + '-')).concat([{name: 'general-purpose'}]); }"
                  "\nconsole.log(JSON.stringify([plDraftAgents({agents: [{name: 'impl', scope: 'project'}, {name: 'x', scope: 'user'}, {name: 'app-rev', scope: 'user'}]}, '/w/app'), plDraftAgents(null)]));")
        self.assertEqual(out, [["impl", "app-rev", "general-purpose"], ["general-purpose"]])
        src = open(os.path.join(ROOT, "web", "js", "48e-pipeline-new.js"), encoding="utf-8").read()
        self.assertEqual(src.count("plDraftAgents(d, PLS.proj), PLG_TITLES"), 3)   # preview, live refresh, sent body

    def test_snake_rows(self):
        out = run("plgLayout(G, 28, 3); const L = plgLoopLanes(G);"
                  "console.log(JSON.stringify({u: G.nodes.map(n => [n.ui.x, n.ui.y]), L: G.loops.map((l, i) => L[i]),"
                  " f: plgFlowPath(plgNode(G, 'n3').ui, plgNode(G, 'n4').ui), c: [plgCols(7, 1100, 0.8), plgCols(4, 1100, 0.8)]}));")
        rh = 100 + 62 + 34 * 2   # 62 = row gap with the live label above each node
        self.assertEqual(out["u"], [[44, 24], [256, 24], [468, 24], [44, 24 + rh], [256, 24 + rh]])
        self.assertIn(" H", out["f"])                                   # row wrap connector, not a curve through boxes
        self.assertEqual(out["L"][0], {"k": 0, "y": 24 + 100 + 34})       # 검증->구현 same row
        cross = out["L"][1]                                             # 리뷰 (row 2) -> 구현 (row 1)
        self.assertEqual((cross["y"], cross["y2"]), (24 + rh + 100 + 34, 24 + 100 + 68))
        self.assertEqual(out["c"], [4, 4])

    def test_wrap_cols_one_row_at_min_zoom(self):
        # plWrapCols: one row readable at >= PL_ZMIN stays one row (4 stages, 832px canvas went 3+1); a long chain still wraps
        fns = "const PL_ZMIN = 0.8;\n" + "\n".join(js_fn(f) for f in ("plFitRaw", "plWrapCols"))
        out = _js(fns + "\nconst mk = k => plgFrom({name: 'x', defaults: {model: 'inherit', retry: 0}, stages: Array.from({length: k}, (_, i) => ({title: 's' + i, agent: 'a'}))});"
                  "console.log(JSON.stringify([plWrapCols(mk(4), 832, 700), plWrapCols(mk(7), 785, 700), plWrapCols(mk(7), 1016, 700)]));")
        self.assertEqual(out[0], 4)
        self.assertLess(out[1], 7)
        self.assertLess(out[2], 7)

    def test_variable_widths(self):
        # content-sized nodes (G.wd, measured by 48d): layout gap, edge endpoints and lanes use the real width, not PLG_W
        out = run("G.wd = {n1: 300, n2: 250}; plgLayout(G, 28, 9); const L = plgLoopLanes(G), pt = id => plgNode(G, id).ui;"
                  "console.log(JSON.stringify({x: G.nodes.map(n => n.ui.x), f: plgFlowPath(pt('n1'), pt('n2'), plgW(G, 'n1')),"
                  " l: plgLoopPath(pt('n3'), pt('n2'), L[0], plgW(G, 'n3'), plgW(G, 'n2')).d, k: L[0].k,"
                  " c: [plgCols(5, 1000, 0.8, [300, 250, 184, 184, 184]), plgGap(2, 1000, [300, 250])]}));")
        self.assertEqual(out["x"], [44, 372, 650, 862, 1074])
        self.assertTrue(out["f"].startswith("M344 74 "))                 # right side of the 300px node
        self.assertTrue(out["f"].endswith(" 372 74"))
        k = out["k"]
        self.assertTrue(out["l"].startswith("M%d 124 " % (650 + 92 + 14 * k)))
        self.assertTrue(out["l"].endswith(" L%d 124" % (372 + 125 - 14 * k)))
        self.assertEqual(out["c"], [2, 64])                  # wrapped rows sized by the widest node

    def test_push_overlaps_display_only(self):
        # saved files place nodes 248px apart; a 320px node must push its right neighbours (display only, draft stays clean)
        out = run("plgNode(G, 'n4').ui.y = 30; const k0 = plgKey(G); G.wd = {n1: 320}; const px = plgPush(G);"
                  "console.log(JSON.stringify({px, same: plgKey(G) === k0, x: G.nodes.map(n => n.ui.x)}));")
        self.assertEqual(out["px"], {"n2": 392, "n3": 604, "n4": 816})  # n5 (1036) already clears 816 + 184 + 28
        self.assertTrue(out["same"])
        self.assertEqual(out["x"], [44, 292, 540, 788, 1036])

    def test_align_middle_display_only(self):
        # same saved y, heights 100/140/100 -> equal displayed middles; another row untouched; draft unchanged
        out = run("G.nodes.forEach((n, i) => { n.ui = {x: 44 + 248 * i, y: i < 3 ? 24 : 400}; }); G.ht = {n1: 100, n2: 140, n3: 100, n4: 100, n5: 160};"
                  "const k0 = plgKey(G), py = plgAlign(G), V = plVG({G}), px = plgPush(G);"
                  "console.log(JSON.stringify({py, mid: V.nodes.map(n => n.ui.y + plgH(G, n.id) / 2), same: plgKey(G) === k0,"
                  " y: G.nodes.map(n => n.ui.y), vx: V.nodes.map(n => n.ui.x), px}));")
        self.assertEqual(out["mid"][:3], [94, 94, 94])
        self.assertEqual(out["py"], {"n1": 44, "n3": 44, "n4": 430})   # n4/n5 form their own row
        self.assertTrue(out["same"])
        self.assertEqual(out["y"], [24, 24, 24, 400, 400])
        self.assertEqual(out["px"], {})
        self.assertEqual(out["vx"], [44, 292, 540, 788, 1036])

    def test_layout_keeps_colour(self):
        out = run("plgNode(G, 'n2').ui.color = '#f472b6'; plgLayout(G, 28, 3); console.log(JSON.stringify(plgNode(G, 'n2').ui));")
        self.assertEqual(out, {"x": 256, "y": 24, "color": "#f472b6"})

    def test_lanes_clear_status_pills(self):
        # status pill = CSS .plls: fully above the node, left -1px, bottom 6px above it, h 22, w <= node + 24 (43-pipeline.css); no loop lane or flow edge may cross it
        out = run("plgLayout(G, 28, 3); const L = plgLoopLanes(G), pt = id => plgNode(G, id).ui;"
                  "console.log(JSON.stringify({n: G.nodes.map(n => [n.ui.x, n.ui.y]),"
                  " d: G.loops.map((l, i) => plgLoopPath(pt(l.from), pt(l.to), L[i]).d).concat(G.flow.map(e => plgFlowPath(pt(e[0]), pt(e[1]))))}));")
        rects = [(x - 1 - 2, y + 1 - 6 - 22 - 2, x + 184 + 24 + 2, y + 1 - 6 + 2) for x, y in out["n"]]
        for d in out["d"]:
            nums, pts, cur = re.findall(r"([MLHVQC])([^MLHVQC]*)", d), [], (0, 0)
            for c, a in nums:
                v = [float(t) for t in a.split()]
                cur = {"M": lambda: (v[0], v[1]), "L": lambda: (v[0], v[1]), "H": lambda: (v[0], cur[1]), "V": lambda: (cur[0], v[0]),
                       "Q": lambda: (v[2], v[3]), "C": lambda: (v[4], v[5])}[c]()
                pts.append(cur)
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                for t in range(51):
                    px, py = x1 + (x2 - x1) * t / 50, y1 + (y2 - y1) * t / 50
                    for r in rects:
                        self.assertFalse(r[0] < px < r[2] and r[1] < py < r[3], (d, px, py, r))

    def test_status_pill_css_matches_lane_check(self):
        # the rects above assume this geometry; a CSS change must move the test with it
        import pathlib
        css = (pathlib.Path(__file__).resolve().parent.parent / "web" / "css" / "43-pipeline.css").read_text(encoding="utf-8")
        rule = re.search(r"html\[data-ui=next\] \.plw \.plnd \.plls\{([^}]*)\}", css).group(1)
        for d in ("left:-1px", "bottom:calc(100% + 6px)", "height:22px", "max-width:calc(100% + 24px)"):
            self.assertIn(d, rule)
        self.assertNotIn("plstreak", css)                                  # the running-node border streak was removed

    def test_edge_ends_on_node_borders(self):
        out = run("plgLayout(G, 28, 3); const L = plgLoopLanes(G), pt = id => plgNode(G, id).ui;"
                  "console.log(JSON.stringify({f: G.flow.map(e => [pt(e[0]), pt(e[1]), plgFlowPath(pt(e[0]), pt(e[1]))]),"
                  " l: G.loops.map((l, i) => [pt(l.from), pt(l.to), plgLoopPath(pt(l.from), pt(l.to), L[i]).d])}));")

        def ends(d):
            pts, cur = [], (0, 0)
            for c, a in re.findall(r"([MLHVQC])([^MLHVQC]*)", d):
                v = [float(t) for t in a.split()]
                cur = {"M": (v[:2]), "L": v[:2], "H": [v[0], cur[1]], "V": [cur[0], v[0]], "Q": v[2:4], "C": v[4:6]}[c]
                pts.append(cur)
            return pts[0], pts[-1]
        for a, b, d in out["f"]:                                   # flow: right-middle of source -> left-middle of target
            (x1, y1), (x2, y2) = ends(d)
            self.assertLessEqual(max(abs(x1 - (a["x"] + 184)), abs(y1 - (a["y"] + 50)), abs(x2 - b["x"]), abs(y2 - (b["y"] + 50))), 1, d)
        for a, b, d in out["l"]:                                   # loop: bottom border of source -> bottom border of target
            (x1, y1), (x2, y2) = ends(d)
            self.assertLessEqual(max(abs(y1 - (a["y"] + 100)), abs(y2 - (b["y"] + 100))), 1, d)
            self.assertTrue(a["x"] < x1 < a["x"] + 184 and b["x"] < x2 < b["x"] + 184, d)
        refx = [float(x) for x in re.findall(r"refX=([\d.]+) refY=5", js_all())]
        self.assertTrue(refx and all(0 <= (r - 8) * 0.9 <= 1 for r in refx), refx)   # chevron tip (x=8 of 10, scale .9) within 1px of the border

    def test_tall_node_geometry(self):
        # a gate result line grows a card to 118px (G.ht): anchors, lanes and row spacing follow the measured height
        out = run("G.ht = {n3: 118, n4: 118}; plgLayout(G, 28, 3); const L = plgLoopLanes(G), pt = id => plgNode(G, id).ui, h = id => plgH(G, id);"
                  "console.log(JSON.stringify({n: G.nodes.map(n => [n.ui.x, n.ui.y, h(n.id)]), rh: plgRowH(G),"
                  " f: G.flow.map(e => plgFlowPath(pt(e[0]), pt(e[1]), 184, h(e[0]), h(e[1]))),"
                  " l: G.loops.map((l, i) => [plgLoopPath(pt(l.from), pt(l.to), L[i], 184, 184, h(l.from), h(l.to)).d, L[i].y])}));")
        self.assertEqual(out["rh"], 118 + 62 + 34 * 2)
        y3 = out["n"][2][1]
        self.assertTrue(out["f"][1].endswith(" %g %g" % (out["n"][2][0], y3 + 59)), out["f"][1])   # into n3's real side-centre
        self.assertTrue(out["l"][0][0].startswith("M") and (" %g" % (y3 + 118)) in out["l"][0][0].split(" L")[0], out["l"][0][0])
        bad = []
        for d in out["f"] + [x[0] for x in out["l"]]:
            pts, cur = [], (0, 0)
            for c, a in re.findall(r"([MLHVQC])([^MLHVQC]*)", d):
                v = [float(t) for t in a.split()]
                cur = {"M": v[:2], "L": v[:2], "H": [v[0], cur[1]], "V": [cur[0], v[0]], "Q": v[2:4], "C": v[4:6]}[c]
                pts.append(cur)
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                for t in range(41):
                    px, py = x1 + (x2 - x1) * t / 40, y1 + (y2 - y1) * t / 40
                    bad += [(d, px, py) for x, y, hh in out["n"] if x + 2 < px < x + 182 and y + 2 < py < y + hh - 2]
        self.assertEqual(bad, [])
        for _, ly in out["l"]:                                      # loop labels (20px pills) sit clear of every tall box
            self.assertFalse(any(x for x, y, hh in out["n"] if y - 10 < ly < y + hh + 10 and hh > 100 and ly > y), ly)

    def _crossings(self, nodes, paths, ends_ok=2):
        """sampled points of every path strictly inside a node box (shrunk by `ends_ok` so border endpoints pass)"""
        bad = []
        for d in paths:
            pts, cur = [], (0, 0)
            for c, a in re.findall(r"([MLHVQC])([^MLHVQC]*)", d):
                v = [float(t) for t in a.split()]
                cur = {"M": v[:2], "L": v[:2], "H": [v[0], cur[1]], "V": [cur[0], v[0]], "Q": v[2:4], "C": v[4:6]}[c]
                pts.append(cur)
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                for t in range(41):
                    px, py = x1 + (x2 - x1) * t / 40, y1 + (y2 - y1) * t / 40
                    bad += [(d, px, py) for x, y in nodes if x + ends_ok < px < x + 184 - ends_ok and y + ends_ok < py < y + 100 - ends_ok]
        return bad

    def test_loop_u_for_free_placed_node(self):
        # ★2026-10-01 screenshot: 재현 원인 수정 리뷰 in a row, 라이브 검증 dragged lower-right, loop 라이브 검증 -> 수정
        Q = {"name": "bf", "defaults": {"model": "inherit", "retry": 0}, "stages": [
            {"title": "재현", "agent": "a"}, {"title": "원인", "agent": "a"}, {"title": "수정", "agent": "a"}, {"title": "리뷰", "agent": "a"},
            {"title": "라이브 검증", "agent": "a", "onFail": {"goto": "수정", "max": 1}}]}
        out = _js("const G = plgFrom(%s); plgLayout(G, 64, 9); const r = plgNode(G, 'n4').ui; plgNode(G, 'n5').ui = {x: r.x + 248, y: r.y + 170};"
                  "const L = plgLoopLanes(G), pt = id => plgNode(G, id).ui;"
                  "console.log(JSON.stringify({n: G.nodes.map(n => [n.ui.x, n.ui.y]), a: pt('n5'), b: pt('n3'),"
                  " l: plgLoopPath(pt('n5'), pt('n3'), L[0]).d, f: G.flow.map(e => plgFlowPath(pt(e[0]), pt(e[1])))}));" % json.dumps(Q))
        d = out["l"]
        self.assertEqual(len(re.findall("Q", d)) + len(re.findall("[HV]", d)), 2, d)          # U: two rounded bends
        xs = [float(x) for x in re.findall(r"(?<=[MLQ])\s*(-?[\d.]+)", d)]
        self.assertGreaterEqual(min(xs), min(out["a"]["x"], out["b"]["x"]) - 30, d)
        self.assertEqual(self._crossings(out["n"], [d] + out["f"]), [])

    def test_no_box_crossings_two_rows(self):
        out = run("plgLayout(G, 28, 3); const L = plgLoopLanes(G), pt = id => plgNode(G, id).ui;"
                  "console.log(JSON.stringify({n: G.nodes.map(n => [n.ui.x, n.ui.y]),"
                  " d: G.loops.map((l, i) => plgLoopPath(pt(l.from), pt(l.to), L[i]).d).concat(G.flow.map(e => plgFlowPath(pt(e[0]), pt(e[1]))))}));")
        self.assertEqual(self._crossings(out["n"], out["d"]), [])

    def test_reorder_move(self):
        out = run("const T = () => plgLine(G).map(id => plgNode(G, id).title), r = [];"
                  "const id = t => G.nodes.find(n => n.title === t).id, L0 = JSON.stringify(G.loops);"
                  "r.push(plgMove(G, id('설계'), -1), plgMove(G, id('재검증'), 1));"      # first ◀ / last ▶ refused
                  "plgMove(G, id('설계'), 1); r.push(T());"                                   # first -> second
                  "plgMove(G, id('재검증'), -1); r.push(T());"                              # last -> before 리뷰
                  "plgMove(G, id('검증'), -1); r.push(T(), JSON.stringify(G.loops) === L0, G.flow.length);"
                  "console.log(JSON.stringify(r));")
        self.assertEqual(out[:2], [False, False])
        self.assertEqual(out[2], ["구현", "설계", "검증", "리뷰", "재검증"])
        self.assertEqual(out[3], ["구현", "설계", "검증", "재검증", "리뷰"])
        self.assertEqual(out[4], ["구현", "검증", "설계", "재검증", "리뷰"])
        self.assertEqual(out[5:], [True, 4])                                   # loop-backs untouched; still one line

    def test_insert_on_edge(self):
        out = run("plgLayout(G, 28, 9); const id = t => G.nodes.find(n => n.title === t).id, T = () => plgLine(G).map(k => plgNode(G, k).title);"
                  "const a = plgNode(G, id('검증')).ui, b = plgNode(G, id('리뷰')).ui;"
                  "const p = {x: (a.x + 184 + b.x) / 2, y: a.y + 53}, hit = plgEdgeAt(G, p, id('설계'), 10), miss = plgEdgeAt(G, {x: p.x, y: p.y + 40}, id('설계'), 10);"
                  "const f = G.flow[hit], ok = plgInsertAt(G, id('설계'), f[0], f[1]);"
                  "console.log(JSON.stringify([miss, ok, T(), G.flow.length, plgInsertAt(G, id('설계'), id('설계'), id('리뷰')), G.loops.length]));")
        self.assertEqual(out[0], -1)
        self.assertTrue(out[1])
        self.assertEqual(out[2], ["구현", "검증", "설계", "리뷰", "재검증"])   # old neighbours joined, inserted between
        self.assertEqual(out[3:], [4, False, 2])

    def test_every_edge_head_has_a_marker(self):
        # heads sit in their own layer above the nodes (a selected node's outline hid them); each must point at a defined marker
        out = run("plgLayout(G, 28, 3); plgNode(G, G.nodes[2].id).ui.color = '#f472b6';"
                  "const E = {G, lt: {}}; console.log(JSON.stringify([plMarkers(G), plHeadsSvg(E), G.flow.length + G.loops.length]));")
        ids = set(re.findall(r"<marker id=([\w-]+)", out[0]))
        refs = re.findall(r'marker-end="url\(#([\w-]+)\)"', out[1])
        self.assertEqual(len(refs), out[2])
        self.assertTrue(set(refs) <= ids, (refs, ids))
        self.assertIn("plaf-c-f472b6", refs)
        # ⚠ family 'check' once matched the custom 'c' prefix and got --pfc:#heck (invisible chevron)
        self.assertIn("<marker id=plaf-check class=pf-check ", out[0])
        self.assertNotIn("#heck", out[0])

    def test_running_edge_tail_meets_border(self):
        # ⚠the running node's glow washed out the line end (read as a gap); the tail is redrawn above it, clipped at the border
        out = run("plgLayout(G, 28, 3); const n = G.nodes[1], E = {G, lt: {[n.title]: {st: 'run'}}};"
                  "console.log(JSON.stringify([plHeadsSvg(E), n.ui.x, n.ui.y, G.flow.length]));")
        m = re.search(r'<clipPath id=(plrc\d+)><rect x="([\d.-]+)" y="[\d.-]+" width=32 ', out[0])
        self.assertTrue(m, out[0])
        self.assertEqual(float(m.group(2)) + 32, out[1])   # clip ends exactly at the node's left border
        p = re.search(r'<path class=plrin style="stroke:url\(#plgr\d+\)" clip-path="url\(#%s\)" d="([^"]+)"' % m.group(1), out[0])
        self.assertTrue(p, out[0])
        self.assertEqual(float(re.findall(r"[\d.-]+", p.group(1))[-2]), out[1])   # the drawn line ends on that border too
        self.assertEqual(out[0].count('marker-end="url(#plaf-'), out[3])   # the running edge keeps its chevron like every other edge
        self.assertNotIn('plrain', out[0])   # running edges carry no moving dashes (read as a blob on short edges)

    def test_custom_stage(self):
        out = run("const id = plgInsert(G, '문서 정리', 'n2'); const e1 = plgCheck(G).errs.map(e => e.msg);"
                  "plgNode(G, id).instr = 'update docs'; const c = plgCheck(G);"
                  "console.log(JSON.stringify({e1, e2: c.errs, slots: plgSlots(plgStages(G, c.order))}));")
        self.assertTrue(any("needs an instruction" in m for m in out["e1"]), out["e1"])
        self.assertEqual(out["e2"], [])
        self.assertEqual(out["slots"]["문서 정리"], "사용자 단계 1")
        self.assertEqual(out["slots"]["검증"], "검증")
        out = run("plgNode(G, 'n1').title = '사용자 단계 2'; console.log(JSON.stringify(plgCheck(G).errs.map(e => e.msg)));")
        self.assertTrue(any("reserved" in m for m in out))

    def test_dirty_key(self):
        out = run("const k0 = plgKey(G); G.nodes[0].ui = {x: 5, y: 5}; const k1 = plgKey(G); console.log(JSON.stringify(k0 !== k1));")
        self.assertTrue(out)


CAT ={"groups": [{"id": "build", "en": "Build"}, {"id": "quality", "en": "Quality"}, {"id": "review", "en": "Review"}], "items": [
    {"id": "implement", "group": "build", "title": {"ko": "구현", "en": "Implement"}, "role": "build", "gate": "", "tools": []},
    {"id": "lint", "group": "quality", "title": {"ko": "린트·정적 분석", "en": "Lint"}, "role": "check", "model": "sonnet",
     "instr": "Run the runner.", "gate": "python3 /a/scripts/arch_checks.py --verify --last --category security",
     "loop": {"to": ["구현", "수정"], "max": 2}, "tools": []},
    {"id": "review", "group": "review", "title": {"ko": "리뷰", "en": "Review"}, "agent": "my-reviewer", "gate": "", "tools": []}]}


class Catalog(unittest.TestCase):
    """«Stage catalog» adds (48c plgAddTpl): gate prefilled, role -> agent, loop-back only to an earlier stage; guards serialise."""

    def _run(self, ops):
        empty = {"name": "e", "defaults": {"model": "inherit", "retry": 0}, "stages": []}
        return _js("const G = plgFrom(%s), cat = %s;\n%s" % (json.dumps(empty), json.dumps(CAT), ops))

    def test_add_prefills_gate_and_loop(self):
        out = self._run("const a = plgAddTpl(G, plgTpl(cat, 'lint'), {}); const i = plgAddTpl(G, plgTpl(cat, '구현'), {roles: {build: 'impl'}});"
                        "const r = plgAddTpl(G, plgTpl(cat, 'review'), {}, i);"
                        "console.log(JSON.stringify({a, n: G.nodes, loops: G.loops, o: plgOrder(G).order, errs: plgCheck(G).errs}));")
        n = {x["id"]: x for x in out["n"]}
        lint = n[out["a"]]
        self.assertEqual((lint["title"], lint["agent"], lint["model"], lint["instr"]), ("린트·정적 분석", "general-purpose", "sonnet", "Run the runner."))
        self.assertEqual(lint["gate"], CAT["items"][1]["gate"])
        self.assertEqual(out["loops"], [])                                        # 구현 came later: no loop-back
        self.assertEqual([n[x]["title"] for x in out["o"]], ["린트·정적 분석", "구현", "리뷰"])   # «+ Add» after the selected stage
        self.assertEqual(n["n2"]["agent"], "impl")
        self.assertEqual(n["n3"]["agent"], "my-reviewer")
        self.assertNotIn("gate", n["n2"])                                         # gate "" = judgment stage, nothing written
        self.assertEqual(out["errs"], [])
        out = self._run("const i = plgAddTpl(G, plgTpl(cat, 'implement'), {}); const a = plgAddTpl(G, plgTpl(cat, 'lint'), {}, {x: 10, y: 300});"
                        "console.log(JSON.stringify({loops: G.loops, ui: plgNode(G, a).ui, st: plgStages(G, plgOrder(G).order)}));")
        self.assertEqual(out["loops"], [{"from": "n2", "to": "n1", "max": 2}])
        self.assertEqual(out["ui"], {"x": 10, "y": 300})
        self.assertEqual(out["st"][1]["gate"], CAT["items"][1]["gate"])
        self.assertIsNone(self._run("console.log(JSON.stringify(plgAddTpl(G, plgTpl(cat, 'nope'), {})));"))

    def test_in_use_adds_numbered_copy(self):
        out = self._run("const a = plgAddTpl(G, plgTpl(cat, 'lint'), {}), b = plgAddTpl(G, plgTpl(cat, 'lint'), {}), c = plgAddTpl(G, plgTpl(cat, 'lint'), {});"
                        "plgNode(G, b).title = 'x'; const d = plgAddTpl(G, plgTpl(cat, 'lint'), {});"   # a freed number is reused
                        "const v = plgAddTpl(G, plgTpl(cat, '구현'), {}), v2 = plgAddTpl(G, plgTpl(cat, '구현'), {dt: {'구현': 'Run the gate.'}});"
                        "PLG_CAT = {'린트·정적 분석': 'quality'};"
                        "console.log(JSON.stringify({t: [a, c, d, v, v2].map(x => plgNode(G, x).title), c: plgNode(G, c), v: plgNode(G, v), v2: plgNode(G, v2),"
                        " fam: plgFam('린트·정적 분석 3'), tpl: plgTpl(cat, '린트·정적 분석 2'),"
                        " base: ['검증 2', '검증 1', '검증', 'v 10', ''].map(plgBase), long: plgFreeTitle({nodes: [{title: 'a'.repeat(40)}]}, 'a'.repeat(40)).length,"
                        " show: (LANG = 'en', plgShow('구현 2')), errs: plgCheck(G).errs}));")
        self.assertEqual(out["t"], ["린트·정적 분석", "린트·정적 분석 3", "린트·정적 분석 2", "구현", "구현 2"])
        self.assertEqual((out["c"]["instr"], out["c"]["gate"], out["c"]["model"]), ("Run the runner.", CAT["items"][1]["gate"], "sonnet"))
        self.assertNotIn("instr", out["v"])                                       # recommended title: the runner default applies
        self.assertEqual(out["v2"]["instr"], "Run the gate.")                     # its copy is custom: default carried as the task
        self.assertEqual((out["fam"], out["tpl"]), ("qual", None))             # colour by base; template lookup exact only
        self.assertEqual(out["base"], ["검증", "검증 1", "검증", "v", ""])
        self.assertEqual(out["long"], 40)
        self.assertEqual(out["show"], "Implement 2")
        self.assertEqual(out["errs"], [])

    def test_typed_copy_title_kept(self):
        out = self._run("plgAddTpl(G, plgTpl(cat, '구현'), {}); const t = '구현 2', id = plgAddTpl(G, plgTpl(cat, t), {}) || plgInsert(G, t, '');"
                        "console.log(JSON.stringify(G.nodes.map(n => n.title)));")
        self.assertEqual(out, ["구현", "구현 2"])                                # same path as 48d «+ Custom stage» with a typed name

    def test_family_from_group(self):
        out = self._run("const a = plgFam('린트·정적 분석'); PLG_CAT = {'린트·정적 분석': 'quality', '코드 지도': 'understand'};"
                        "console.log(JSON.stringify([a, plgFam('린트·정적 분석'), plgFam('코드 지도'), plgFam('설계'), plgFam('x')]));")
        self.assertEqual(out, ["cust", "qual", "und", "plan", "cust"])
        # every group gets its own family and every family has a CSS hue in both themes
        fams = self._run("console.log(JSON.stringify([Object.values(PLG_GFAM), PLG_FAMS]));")
        self.assertEqual(len(set(fams[0])), len(fams[0]))
        with open(os.path.join(ROOT, "web", "css", "43-pipeline.css"), encoding="utf-8") as fh:
            css = fh.read()
        for f in fams[1]:
            self.assertIn(".pf-%s{--pf:var(--plf-%s)}" % (f, f), css)
            self.assertIn("--plf-%s:" % f, css)

    def test_guards_serialise(self):
        out = self._run("plgAddTpl(G, plgTpl(cat, 'implement'), {}); plgAddTpl(G, plgTpl(cat, 'lint'), {});"
                        "const k0 = plgKey(G); G.guards = {requireGates: ['구현', '린트·정적 분석', 'gone'], maxLoopBacks: 3};"
                        "const a = plgGuards(G), k1 = plgKey(G); G.guards.maxLoopBacks = 11; const b = plgGuards(G);"
                        "console.log(JSON.stringify({a, b, dirty: k0 !== k1, none: plgGuards({nodes: []})}));")
        self.assertEqual(out["a"], {"requireGates": ["린트·정적 분석"], "maxLoopBacks": 3})   # only graded stages that exist
        self.assertEqual(out["b"], {"requireGates": ["린트·정적 분석"]})                    # out-of-range limit dropped
        self.assertTrue(out["dirty"])
        self.assertEqual(out["none"], {})

    def test_guards_round_trip_from_file(self):
        p = dict(P, guards={"requireGates": ["검증"], "maxLoopBacks": 2})
        p["stages"] = [dict(s) for s in P["stages"]]
        p["stages"][2]["gate"] = "bash t.sh"
        out = _js("const G = plgFrom(%s); console.log(JSON.stringify(plgGuards(G)));" % json.dumps(p))
        self.assertEqual(out, {"requireGates": ["검증"], "maxLoopBacks": 2})

    def test_hue(self):
        out = run("const n = plgNode(G, 'n1'); const a = plgHue(n), p = plgPfc(n); n.ui.color = '#123456';"
                  "console.log(JSON.stringify([a, p, plgHue(n)]));")
        self.assertEqual(out, ["", "", "#123456"])


WRAP = "".join(js_fn(f) + "\n" for f in ("plFitRaw", "plWrapCols", "plWrapBest", "plWrapFirst"))


class Fit(unittest.TestCase):
    """plFit (48d): saved positions fit the whole chain; «정렬» (keepZ) keeps the zoom and re-flows to fit it."""

    def _fit(self, body):
        zc = re.search(r"^const PL_ZMIN[^\n]*$", js_all(), re.M).group(0)
        return run(zc + "\n" + js_fn("plFit") + "\n" + js_fn("plFitKey") + "\nconst E = {G: G}; const vis = cw => { const z = E.view.z;"
                   " return G.nodes.filter(n => (n.ui.x + plgW(G, n.id)) * z + E.view.x <= cw).length; };\n" + body)

    def test_saved_positions_fit_all(self):
        out = self._fit("plgLayout(G, 64, 9); plFit(E, {clientWidth: 600, clientHeight: 400}, false);"   # one row, 1264px wide
                        "console.log(JSON.stringify([E.view.z, vis(600)]));")
        self.assertLess(out[0], 0.8)                 # below the old 80% floor
        self.assertEqual(out[1], 5)                  # every stage on canvas

    def test_first_paint_wraps_when_unreadable(self):
        # narrow canvas: one saved row fits only at the 40% floor -> wrapped rows show every stage at a larger zoom
        out = self._fit(WRAP + "plgLayout(G, 64, 9); const cv = {clientWidth: 350, clientHeight: 426}; plFit(E, cv, false); const z0 = E.view.z;"
                        "plWrapFirst(E, cv); console.log(JSON.stringify([z0, E.view.z, vis(350), E.laid, E.touched]));")
        self.assertEqual(out[0], 0.4)
        self.assertGreater(out[1], out[0])
        self.assertEqual(out[2:4], [5, True])
        self.assertFalse(out[4])                     # an auto wrap is not a user action: later resizes may re-fit

    def test_align_keeps_zoom(self):
        out = self._fit("E.view = {x: 0, y: 0, z: 0.8}; plFit(E, {clientWidth: 550, clientHeight: 400}, true, true);"
                        "console.log(JSON.stringify([E.view.z, vis(550)]));")
        self.assertEqual(out, [0.8, 5])

    def test_align_and_fit_share_first_paint_wrap(self):
        # «정렬» keeps a zoom that still fits, falls back to the best fit when it would not; «화면에 맞추기» = first-paint zoom.
        out = self._fit(WRAP + "plgLayout(G, 64, 9); const cv = {clientWidth: 350, clientHeight: 426};"
                        "plFit(E, cv, false); plWrapFirst(E, cv); const zf = E.view.z;"
                        "E.view.z = 0.3; plWrapBest(E, cv, true); const keep = E.view.z;"
                        "E.view.z = 1.5; plWrapBest(E, cv, true); const big = [E.view.z, vis(350)];"
                        "plgLayout(G, 64, 9); plWrapBest(E, cv, false);"
                        "console.log(JSON.stringify([zf, keep, big, E.view.z, vis(350)]));")
        self.assertEqual(out[1], 0.3)
        self.assertEqual(out[2], [out[0], 5])
        self.assertEqual(out[3:], [out[0], 5])


if __name__ == "__main__":
    unittest.main()
