"""«파이프라인» 실행 + lighting (web/js/48b-pipeline-run.js): run name, Workflow lighting, plrun model rendering, DM text.
Pure functions only, run under node; the runner's args.models check runs in scripts/pipeline_check.mjs (check.sh)."""
import json
import re
import subprocess
import unittest

from tests._i18n_js import i18n_switch
from tests._load import js_all, js_fn
from tests._node import node_e


def _js(expr, *fns):
    consts = "\n".join(re.search(r"^const %s[^\n]*$" % c, js_all(), re.M).group(0) for c in ("PL_RETRY_RE", "PLG_TITLES", "PL_DESC_RE", "PL_BUILTIN_AG", "PL_OS", "PL_MK"))
    names = re.search(r"^const PLG_NAMES.*?^}, ko: {} };$", js_all(), re.S | re.M).group(0)   # 06-i18n-w.js stage display names
    src = "var LANG = 'ko';\n" + i18n_switch(("T", "TV", "U", "KE")) + consts + "\n" + names + "\n" + "\n".join(js_fn(f) for f in fns + ("plTk", "plgSlots", "plgShow", "plgBase", "plgTplShow", "subWorkId", "plKnown", "plAway", "plTagNames", "plHomes", "plLabType", "plDescStage", "plStrip")) + "\nconsole.log(JSON.stringify(" + expr + "));"
    return json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


def _ag(phase, st, lab, start, end):
    return {"aid": lab, "lab": lab, "phase": phase, "st": st, "start": start, "end": end, "tok": 0}


RUN = {"name": "pipeline", "phase": "검증", "run": True, "total": 5, "done": 3, "fail": 0, "start": 100, "end": 400,
       "agents": [_ag("불러오기", "done", "load sidereus-change", 100, 110), _ag("설계", "done", "설계", 110, 200),
                  _ag("구현", "done", "구현 s1", 200, 290), _ag("구현", "done", "구현 s2", 200, 300),
                  _ag("검증", "fail", "검증", 300, 330), _ag("검증", "run", "검증 retry 1", 330, 400)]}
STAGES = [{"title": t} for t in ("설계", "구현", "검증", "리뷰")]


class Lighting(unittest.TestCase):
    def test_run_name_from_load_label(self):
        self.assertEqual(_js("plRunName(%s, {}, 's')" % json.dumps(RUN), "plRunName"), "sidereus-change")

    def test_run_name_falls_back_to_memory(self):
        run = dict(RUN, agents=RUN["agents"][1:])
        self.assertEqual(_js("plRunName(%s, {s: {name: 'bugfix', at: 1}}, 's')" % json.dumps(run), "plRunName"), "bugfix")
        self.assertEqual(_js("plRunName(%s, {}, 's')" % json.dumps(dict(RUN, name="sidereus-change")), "plRunName"), "")

    def test_stage_states(self):
        L = _js("plLight(%s, %s)" % (json.dumps(STAGES), json.dumps(RUN)), "plLight")
        self.assertEqual({k: v["st"] for k, v in L.items()}, {"설계": "done", "구현": "done", "검증": "run", "리뷰": "wait"})
        self.assertEqual((L["구현"]["n"], L["구현"]["sec"], L["구현"]["retry"]), (2, 100, 0))
        self.assertEqual((L["검증"]["n"], L["검증"]["retry"]), (2, 1))

    def test_custom_title_lights_its_slot(self):
        run = dict(RUN, agents=[_ag("설계", "done", "설계", 100, 150), _ag("사용자 단계 1", "run", "문서 정리", 150, 190)])
        st = [{"title": "설계"}, {"title": "문서 정리"}, {"title": "검증"}]
        L = _js("plLight(%s, %s)" % (json.dumps(st), json.dumps(run)), "plLight")
        self.assertEqual({k: v["st"] for k, v in L.items()}, {"설계": "done", "문서 정리": "run", "검증": "wait"})

    def test_finished_run_fail(self):
        run = dict(RUN, run=False, agents=RUN["agents"][:5])
        L = _js("plLight(%s, %s)" % (json.dumps(STAGES), json.dumps(run)), "plLight")
        self.assertEqual(L["검증"]["st"], "fail")


class Direct(unittest.TestCase):
    def test_desc_prefix(self):
        out = _js("[plDescStage('sidereus-designer: [pl:sidereus-change/설계] spec'), plDescStage('x: [pl:a/문서 정리] y'), plDescStage('x: plain'),"
                  " plDescStage('x: [pl:sidereus-change/최종 검')]", "plDescStage")
        self.assertEqual(out[:3], [{"name": "sidereus-change", "title": "설계"}, {"name": "a", "title": "문서 정리"}, None])
        self.assertIsNone(out[3])                                        # truncated label: no guess

    def test_stage_display_names(self):
        out = _js("[plgShow('설계'), plgShow('라이브 검증'), plgShow('문서 정리'), plgShow('constructor'), (LANG = 'en', plgShow('수정'))]", "plgShow")
        self.assertEqual(out, ["설계", "라이브 검증", "문서 정리", "constructor", "Fix"])   # unknown = as-is

    def test_std_names_all_have_english(self):
        from sidereus import pipeline_std
        st = sorted({t for _k, _t, _s, sts in pipeline_std.STD for t, *_ in sts})
        tp = [t for _k, t, _s, _st in pipeline_std.STD]
        en, ten = _js("(() => { LANG = 'en'; return [%s.map(plgShow), %s.map(plgTplShow)]; })()" % (json.dumps(st), json.dumps(tp)), "plgShow")
        self.assertEqual([t for t, e in zip(st, en) if e == t], [])      # every std stage has an English name
        self.assertEqual([t for t, e in zip(tp, ten) if e == t], [])     # every card title too
        self.assertEqual(_js("[plgTplShow('버그 수정'), plgShow('측정')]", "plgShow"), ["버그 수정", "측정"])   # ko = as saved

    def test_work_id_prefers_agent_id(self):
        out = _js("[subWorkId({aid: 'a05ddf57d3476b511', tid: 'toolu_01B3'}), subWorkId({aid: 'main:s'}), subWorkId({tid: 'toolu_1'}), subWorkId(null),"
                  " subWorkId({aid: '../x', tid: 'toolu_2'})]", "subWorkId")
        self.assertEqual(out, ["a05ddf57d3476b511", "", "toolu_1", "", "toolu_2"])   # aid survives SendMessage resumes; main mark = session

    def test_tooltip_strips_tag(self):
        out = _js("(() => { globalThis.KE = (k, e) => k; return [plLabTip('rv: [pl:bugfix/리뷰] 코드 리뷰'), plLabTip('main: [pl:bugfix/수정]'), plLabTip(plAgLab({aid: 'main'}))]; })()",
                  "plLabTip", "plLabParts", "plLabDesc", "plAgLab")
        self.assertEqual(out, ["rv · 코드 리뷰", "main · 직접 진행", "main · 직접 진행"])


N = 1790000000                     # fixed clock (s); tests stub Date.now = () => N * 1000
ST4 = [{"title": t} for t in ("설계", "구현", "검증", "리뷰")]


def _pag(aid, run, t0, t1, lab=None):
    return {"aid": aid, "tid": "toolu_" + aid, "lab": lab or "impl: [pl:p/구현] " + aid, "run": run, "t0": t0, "t1": t1}


# plrun row (sidereus/pl_runs.pl_model): 설계 done · 구현 running again after a 검증 loop-back · 검증 back · 리뷰 absent
PR = {"name": "p", "proj": "/x/api", "sid": "s", "cur": "구현", "end": 0, "t0": N - 600, "t1": N - 10, "stages": {
    "설계": {"o": "done", "n": 1, "t0": N - 600, "t1": N - 500, "from": {}, "ag": [_pag("a1111111", False, N - 600, N - 500, "dz: [pl:p/설계] spec")]},
    "구현": {"o": "run", "n": 2, "t0": N - 500, "t1": N - 10, "from": {"검증": 1},
             "ag": [_pag("a2222222", False, N - 500, N - 300), _pag("a3333333", True, N - 100, N)]},
    "검증": {"o": "back", "n": 1, "t0": N - 300, "t1": N - 200, "from": {}, "ag": [{"aid": "main", "tid": "", "lab": "main", "run": False, "t0": N - 300, "t1": N - 200}]}}}
MODEL = ("plPrLt", "plPrLv", "plPrLive", "plAgLab", "plWhy", "plAgLabs", "plPsOk", "plPass")


class Model(unittest.TestCase):
    """plrun → lt: render only; a stage absent from the run is wait."""
    def _lt(self, pr, st=ST4):
        return _js("plPrLt(%s, %s, %d)" % (json.dumps(pr), json.dumps(st), N * 1000), *MODEL)

    def test_plrun_maps_lt(self):
        L = self._lt(PR)
        self.assertEqual({k: v["st"] for k, v in L.items()}, {"설계": "done", "구현": "run", "검증": "back", "리뷰": "wait"})
        self.assertEqual((L["설계"]["n"], L["설계"]["sec"]), (1, 100))
        self.assertEqual((L["구현"]["n"], L["구현"]["sec"], L["구현"]["from"]), (2, 500, {"검증": 1}))   # running: now - t0
        self.assertEqual(L["구현"]["labs"], [{"lab": "impl: [pl:p/구현] a3333333", "run": True}, {"lab": "impl: [pl:p/구현] a2222222", "run": False}])
        self.assertEqual(L["검증"]["labs"], [{"lab": "main: ", "run": False}])

    def test_absent_stage_is_wait(self):
        pr = dict(PR, stages={"설계": dict(PR["stages"]["설계"]), "구현": dict(PR["stages"]["구현"], o="<x>")})
        L = self._lt(pr, ST4 + [{"title": "배포"}])
        self.assertEqual([L[t]["st"] for t in ("구현", "검증", "리뷰", "배포")], ["wait"] * 4)   # unknown outcome: wait (it lands in a class)
        self.assertEqual((L["리뷰"]["n"], L["리뷰"]["sec"], L["리뷰"]["ag"]), (0, 0, []))
        self.assertEqual(self._lt({"stages": {}}, [{"title": "설계"}])["설계"]["st"], "wait")   # no stitching: nothing recorded = nothing lit

    def test_only_on_jump_not_needed(self):
        st = [{"title": t} for t in ("구현", "리뷰")] + [{"title": "재검증", "onlyOnJump": True}, {"title": "라이브 검증"}]
        d = lambda t0: {"o": "done", "n": 1, "t0": t0, "t1": t0 + 5, "from": {}}
        base = {"구현": d(N - 300), "리뷰": d(N - 200)}
        ow = lambda pr: (lambda L: (L["재검증"]["st"], L["재검증"]["nn"], L["재검증"]["why"]))(self._lt(dict(PR, **pr), st))
        self.assertEqual(ow({"stages": base}), ("wait", False, ""))                                   # run still before it
        self.assertEqual(ow({"stages": dict(base, **{"라이브 검증": dict(d(N - 100), o="run")})}), ("skip", True, "이번엔 불필요"))   # a later stage started
        self.assertEqual(ow({"end": N, "stages": base}), ("skip", True, "이번엔 불필요"))              # ended right after review
        self.assertEqual(ow({"end": N, "stages": {"구현": d(N - 300)}}), ("wait", False, ""))         # ended earlier: review never ran either
        back = dict(base, **{"라이브 검증": d(N - 100), "구현": dict(d(N - 300), p0=N - 50, k=2)})
        self.assertEqual(ow({"stages": back})[0], "wait")                                             # looped back before it: may run again
        self.assertEqual(self._lt(dict(PR, stages=dict(base, **{"라이브 검증": d(N - 100)})), st[:2] + [{"title": "재검증"}, st[3]])["재검증"]["st"], "wait")   # regular stage: never inferred

    def test_run_summary(self):
        lv = _js("plPrLv('s', %s, %s, %d)" % (json.dumps(PR), json.dumps(ST4), N * 1000), *MODEL)
        self.assertEqual(lv["run"], {"run": True, "phase": "구현", "fail": 0, "total": 4, "start": N - 600, "end": 0})
        done = dict(PR, end=N - 5, stages={"설계": PR["stages"]["설계"]})
        self.assertEqual(_js("plPrLv('s', %s, %s, 0).run" % (json.dumps(done), json.dumps(ST4)), *MODEL)["end"], N - 5)

    def test_node_pick_with_several_agents(self):
        fns = ("plStageAgents", "subWorkId") + MODEL
        js = "(() => { const lt = plPrLt(%s, %s, %d); return [plStageAgents(lt, '구현', %d), plStageAgents(lt, '설계', %d), plStageAgents(lt, '검증', 0), plStageAgents(lt, '리뷰', 0)]; })()" % (
            json.dumps(dict(PR, stages=dict(PR["stages"], 구현=dict(PR["stages"]["구현"], ag=PR["stages"]["구현"]["ag"] + [_pag("a4444444", True, N - 50, N)])))),
            json.dumps(ST4), N * 1000, N * 1000, N * 1000)
        run, done, main, none = _js(js, *fns)
        self.assertEqual([(a["id"], a["tid"], a["run"]) for a in run], [("a4444444", "a4444444", True), ("a3333333", "a3333333", True)])   # running only, newest first
        self.assertEqual([(a["id"], a["run"], a["sec"]) for a in done], [("a1111111", False, 100)])   # nothing running: every agent
        self.assertEqual((main[0]["tid"], none), ("", []))                 # main mark: the session's work popup

    def test_pass_window_filter(self):
        # 구현 pass 3 now; ps = passes 1 and 2 (oldest first). Agents match a pass by t0 inside [a-5, b+5].
        ag = [_pag("a1", False, N - 500, N - 400), _pag("a2", False, N - 297, N - 250), _pag("a3", True, N - 100, N)]
        st = dict(PR["stages"]["구현"], k=3, p0=N - 100, ag=ag, ps=[{"a": N - 500, "b": N - 400, "s": "back"}, {"a": N - 300, "b": N - 200, "s": "fail"},
                                                                    {"a": "x", "b": 1, "s": "done"}, {"a": 1, "b": 2, "s": "<x>"}])
        L = _js("(() => { const L = plPrLt(%s, %s, %d)['구현']; return [L.ps.length, plPass(L, 0), plPass(L, 1), plPass(L, 2)]; })()"
                % (json.dumps(dict(PR, stages={"구현": st})), json.dumps(ST4), N * 1000), *MODEL)
        self.assertEqual(L[0], 2)                                          # bad entries dropped
        self.assertEqual([(p["k"], p["st"], p["w0"], p["w1"], p["sec"], [a["aid"] for a in p["ag"]]) for p in L[1:3]],
                         [(1, "back", N - 500, N - 400, 100, ["a1"]), (2, "fail", N - 300, N - 200, 100, ["a2"])])
        self.assertIsNone(L[3])
        cap = _js("plPsOk(%s).length" % json.dumps([{"a": i, "b": i + 1, "s": "back"} for i in range(9)]), *MODEL)
        self.assertEqual(cap, 6)


class ProjectMatch(unittest.TestCase):
    FNS = ("plLiveRun", "plProjSess", "plMem", "plRunName", "plSessions", "plSubsOf") + MODEL

    def _live(self, sess, proj="/x/api", ret="r && [r.sid, r.lt['구현'].st, r.lt['리뷰'].st]"):
        stub = ("Date.now = () => %d; Object.assign(globalThis, {SESS: %s, PLS: {data: {'/x/api': {pipelines: [{name: 'p', stages: %s}]}}}, lsJson: () => ({})});"
                % (N * 1000, json.dumps(sess), json.dumps(ST4)))
        return _js("(() => { %s const r = plLiveRun(%s, 'p'); return %s; })()" % (stub, json.dumps(proj), ret), *self.FNS)

    def test_plrun_lights_by_proj(self):
        sess = [{"sid": "o", "cwd": "/x/other", "plrun": [dict(PR, proj="/x/other")]}, {"sid": "c", "cwd": "/x/origin", "plrun": [PR]}]
        self.assertEqual(self._live(sess), ["c", "run", "wait"])          # plrun proj wins over the session's cwd
        self.assertIsNone(self._live(sess, "/x/none"))

    def test_no_proj_needs_session_of_proj(self):
        pr = dict(PR, proj="")
        self.assertIsNone(self._live([{"sid": "o", "cwd": "/x/other", "plrun": [pr]}]))
        self.assertEqual(self._live([{"sid": "a", "cwd": "/x/api", "plrun": [pr]}])[0], "a")

    def test_running_then_newest(self):
        old = dict(PR, t1=N - 5000, stages={"설계": PR["stages"]["설계"]})
        new_done = dict(PR, t1=N - 1, stages={"구현": dict(PR["stages"]["구현"], o="done")})
        sess = [{"sid": "a", "cwd": "/x/api", "plrun": [old, new_done]}, {"sid": "b", "cwd": "/x/api", "plrun": [dict(PR, t1=N - 9000)]}]
        self.assertEqual(self._live(sess), ["b", "run", "wait"])          # a running run beats a newer finished one
        self.assertEqual(self._live(sess[:1])[1], "done")                  # else the newest t1

    def test_tagged_session_only(self):
        # t carries [pl:p/구현] with no run record; o's stale run of p must not be drawn under it
        stale = dict(PR, sid="o", t1=N - 7200, stages={"설계": PR["stages"]["설계"], "리뷰": dict(PR["stages"]["설계"], o="run")})
        sess = [{"sid": "o", "cwd": "/x/api", "plrun": [stale]},
                {"sid": "t", "cwd": "/x/triage", "repos": ["/x/api"], "sub": [{"lab": "impl: [pl:p/구현] fix"}]}]
        self.assertEqual(self._live(sess, ret="[r.sid, r.lt['설계'].st, r.lt['구현'].st, r.lt['리뷰'].st]"), ["t", "wait", "run", "wait"])
        own = dict(sess[1], plrun=[dict(PR, sid="t")])
        self.assertEqual(self._live([sess[0], own]), ["t", "run", "wait"])   # its own record wins
        self.assertEqual(self._live(sess[:1])[0], "o")                      # nothing tagged: latest record as before

    def test_wf_runner_wins(self):
        run = {"name": "pipeline", "run": True, "end": 1, "agents": [{"phase": "불러오기", "lab": "load p"}]}
        out = self._live([{"sid": "w", "cwd": "/x/api", "wf": [run], "plrun": [PR]}], ret="[r.sid, !!r.lt, r.run.name]")
        self.assertEqual(out, ["w", False, "pipeline"])                    # Workflow rows light through plLight (48-pipeline)

    def test_cwd_match_preferred(self):
        sess = [{"sid": "r", "cwd": "/x/o", "repos": ["/x/api"]}, {"sid": "c", "cwd": "/x/api"}]
        out = _js("(() => { Object.assign(globalThis, {SESS: %s, PLS: {data: {}}, lsJson: () => ({})}); return plProjSess('/x/api').map(s => s.sid); })()"
                  % json.dumps(sess), "plProjSess", "plMem", "plRunName", "plDescStage")
        self.assertEqual(out, ["c", "r"])

    def test_away_session_joins_sole_owner(self):
        # launched in /x/triage (no pipelines) with [pl:bugfix/..]: only /x/agent owns bugfix.json
        sess = [{"sid": "t", "cwd": "/x/triage", "sub": [{"lab": "x: [pl:bugfix/수정] fix"}]}]
        pls = {"projs": {"ok": True, "projects": [{"path": "/x/agent", "n": 1}, {"path": "/x/b", "n": 1}]},
               "data": {"/x/agent": {"ok": True, "pipelines": [{"name": "bugfix"}]}, "/x/b": {"ok": True, "pipelines": [{"name": "f"}]}}}
        js = "(() => { Object.assign(globalThis, {SESS: %s, PLS: %s, lsJson: () => ({})}); return [plProjSess('/x/agent'), plProjSess('/x/b')].map(l => l.map(s => s.sid)); })()"
        self.assertEqual(_js(js % (json.dumps(sess), json.dumps(pls)), "plProjSess", "plMem", "plRunName", "plDescStage"), [["t"], []])


ESC = re.search(r"^const esc = .*?\n.*?$", js_all(), re.M).group(0).replace("const esc =", "globalThis.esc =", 1)   # real 00-core esc


class DmText(unittest.TestCase):
    P = {"name": "sidereus-change", "defaults": {"model": "inherit"},
         "stages": [{"title": "설계", "agent": "sidereus-designer", "model": ""},
                    {"title": "검증", "agent": "sidereus-verifier", "model": "sonnet"}]}

    def test_text(self):
        t = _js("plDmText(%s, '버튼 고치기', {검증: 'haiku', 설계: ''})" % json.dumps(self.P), "plDmText")
        self.assertEqual(t.split("\n")[0], "파이프라인 sidereus-change 실행 — 요청: «버튼 고치기»")
        args = json.loads(t.split("\n")[1].split(" · args ", 1)[1])
        self.assertEqual(args, {"pipeline": "sidereus-change", "request": "버튼 고치기", "models": {"검증": "haiku"}})
        self.assertIn("scriptPath .claude/workflows/pipeline.js", t)
        self.assertEqual(t.split("\n")[2], "단계: 설계(sidereus-designer·inherit)→검증(sidereus-verifier·haiku)")

    def test_direct_text(self):
        P = dict(self.P, stages=[dict(self.P["stages"][0]), dict(self.P["stages"][1], onFail={"goto": "설계", "max": 2})])
        t = _js("plDmDirect(%s, '버튼 고치기', {설계: 'opus'}, {설계: 'DEF-SPEC'})" % json.dumps(P), "plDmDirect")
        self.assertTrue(t.startswith("파이프라인 sidereus-change 실행 (세션 직접) — 요청: «버튼 고치기»"))
        q = _js("plDmDirect(%s, \"isn't 'x'\", {}, {})" % json.dumps(P), "plDmDirect")
        self.assertTrue(q.startswith("파이프라인 sidereus-change 실행 (세션 직접) — 요청: «isn't 'x'»\n"))   # ' inside stays unambiguous
        self.assertIn("1. 설계 — agent sidereus-designer · model opus", t)
        self.assertIn("onFail → 설계 (max 2)", t)
        self.assertIn('[pl:sidereus-change/<stage title>]', t)
        self.assertIn("SendMessage", t)
        self.assertIn("not the Workflow tool", t)
        self.assertTrue(t.endswith("설계: DEF-SPEC"))

    def test_go_disabled_reason(self):
        r = _js("(globalThis.T = s => s, 0) || [plGoWhy(null, 'x', false), plGoWhy({login: false}, 'x', false), plGoWhy({login: true}, '  ', false),"
                " plGoWhy({login: true}, 'x', true), plGoWhy({login: true}, 'x', false)]", "plGoWhy")
        self.assertEqual(r, ["보낼 세션이 없습니다", "이 세션이 메일박스에 접속하지 않아 보낼 수 없습니다", "요청을 한 줄 입력하세요", "보내는 중입니다", ""])

    def test_no_models_key_without_overrides(self):
        t = _js("plDmText(%s, 'x', {})" % json.dumps(self.P), "plDmText")
        self.assertNotIn("models", t.split("\n")[1])

    def test_ag_missing(self):
        ags = [{"name": "sidereus-designer", "scope": "project"}]
        r = _js("['general-purpose', 'Explore', 'Plan', 'sidereus-designer', 'ghost', ''].map(a => plAgMissing(a, %s))" % json.dumps(ags), "plAgMissing")
        self.assertEqual(r, [False, False, False, False, True, False])

    def test_dm_missing_line(self):
        ags = [{"name": "sidereus-designer"}]
        t = _js("plDmMissing(%s, %s)" % (json.dumps(self.P), json.dumps(ags)), "plAgMissing", "plDmMissing")
        self.assertEqual(t, "\nMissing agents → run as general-purpose with the same task: sidereus-verifier")
        self.assertEqual(_js("plDmMissing(%s, [{name: 'sidereus-designer'}, {name: 'sidereus-verifier'}])" % json.dumps(self.P), "plAgMissing", "plDmMissing"), "")
        self.assertEqual(_js("plDmMissing(%s, undefined)" % json.dumps(self.P), "plAgMissing", "plDmMissing"), "")


class Overview(unittest.TestCase):
    P = {"name": "bugfix", "stages": [{"title": t} for t in ("재현", "수정", "검증")]}
    STUB = "globalThis.KE = (k, e) => k; globalThis.esc = s => String(s); globalThis.strShort = p => p.slice(1);"

    def test_marks_and_count(self):
        lv = {"sid": "s", "lt": {"재현": {"st": "done"}, "수정": {"st": "run"}, "검증": {"st": "wait"}}, "run": {"total": 3}}
        js = "(() => { %s const r = plOvRow('/a', 'bugfix', %s, %s, null, 0); return [r, plOvHtml([r], '/a', 'bugfix')]; })()" % (self.STUB, json.dumps(self.P), json.dumps(lv))
        r, h = _js(js, "plOvRow", "plOvHtml", "plLight", "plOvRunHtml")
        self.assertEqual([s["st"] for s in r["stages"]], ["done", "run", "wait"])
        self.assertEqual((r["n"], r["cur"]), (3, ["수정"]))
        self.assertIn("실행 중 1", h)
        self.assertIn('class="plovst plov-done">✓ 재현', h)
        self.assertIn('class="plovst plov-run plov-pulse"><i class=plovdot aria-hidden=true>●</i> 수정', h)   # running stage pulses
        self.assertEqual(h.count('plov-pulse'), 1)                        # done/wait stay static
        self.assertIn('class="plovst plov-wait">· 검증', h)
        self.assertIn('class="plovr on"', h)
        self.assertIn("에이전트 3", h)
        self.assertIn('data-plovwp="/a" data-plovwn="bugfix"', h)          # row click = open that pipeline
        self.assertNotIn('plovsel', h)                                    # no separate open button

    def test_skip_mark(self):
        lv = {"sid": "s", "lt": {"재현": {"st": "skip"}, "수정": {"st": "run"}}, "run": {"total": 1}}
        js = "(() => { %s const r = plOvRow('/a', 'bugfix', %s, %s, null, 0); return [r, plOvHtml([r], '/a', 'bugfix')]; })()" % (self.STUB, json.dumps(self.P), json.dumps(lv))
        r, h = _js(js, "plOvRow", "plOvHtml", "plLight", "plOvRunHtml")
        self.assertEqual([s["st"] for s in r["stages"]], ["skip", "run", "wait"])
        self.assertIn('class="plovst plov-skip">↷ 재현', h)               # same mark as the canvas node / run table

    def test_english_shows_display_names(self):
        # The strip shows stage titles through plgShow like the canvas and run table; raw file titles leaked in English mode.
        P = {"name": "change-flow", "stages": [{"title": t} for t in ("설계", "구현")]}
        lv = {"sid": "s", "lt": {"설계": {"st": "done"}, "구현": {"st": "run"}}, "run": {"total": 2}}
        js = "(() => { %s LANG = 'en'; const r = plOvRow('/a', 'change-flow', %s, %s, null, 0); return plOvHtml([r], '/a', ''); })()" % (self.STUB, json.dumps(P), json.dumps(lv))
        h = _js(js, "plOvRow", "plOvHtml", "plLight", "plOvRunHtml")
        self.assertIn('class="plovst plov-done">✓ Design', h)
        self.assertIn('</i> Implement', h)
        self.assertNotIn('설계', h)

    def test_empty_no_block(self):
        self.assertEqual(_js("(() => { %s return plOvHtml([], '', ''); })()" % self.STUB, "plOvHtml"), "")

    def test_unloaded_project(self):
        tags = [{"aid": "a1", "title": "수정"}, {"aid": "a2", "title": "수정"}]
        js = "(() => { %s const r = plOvRow('/b', 'bugfix', null, null, %s, 0); return [r, plOvHtml([r], '/a', '')]; })()" % (self.STUB, json.dumps(tags))
        r, h = _js(js, "plOvRow", "plOvHtml", "plOvRunHtml")
        self.assertEqual((r["stages"], r["cur"], r["n"]), (None, ["수정"], 2))
        self.assertIn('class="plovst plov-run plov-pulse"><i class=plovdot aria-hidden=true>●</i> 수정', h)
        self.assertNotIn("plov-wait", h)
        self.assertNotIn('plovr on', h)

    def test_arch_map_row_from_archrun(self):
        # Sidereus's arch-map on a target project: the row comes from plAgRun/plAgOvRow (48h), not the empty tag-only row.
        stub = (self.STUB + " globalThis.T = s => s; globalThis.LOADS = []; Object.assign(globalThis, {SESS: [], PLS: {data: {}, proj: '/t'}, ARCH_PL: 'arch-map',"
                " plLiveProjs: () => ({'/t': ['arch-map']}), plMem: () => ({}), plKnown: () => ({}), plCur: () => null, plOrphHtml: () => '',"
                " plLoad: p => LOADS.push(p), plAgRun: p => p === '/t' ? {stage: 'b', n: 2, of: 3} : null,"
                " plAgOvRow: (proj, r) => ({proj, name: 'arch-map', sid: 's', stages: [{t: 'a', st: 'done'}, {t: r.stage, st: 'run'}], cur: [r.stage], n: 0, sumh: 'N2OF3'})});")
        h, loads = _js("(() => { %s return [plOverview(), LOADS]; })()" % stub, "plOverview", "plOvHtml", "plOvRunHtml")
        self.assertIn("N2OF3", h)
        self.assertNotIn("에이전트 0", h)
        self.assertIn('class="plovst plov-done">✓ a', h)
        self.assertEqual(loads, [])                    # no pipeline-list load of the target for a pipeline it does not own

    def test_overview_placed_above_run_table_not_chips(self):
        # Top placement shifted the chips and canvas on every run start/end: the overview goes after the canvas, before .plrt.
        stub = ("globalThis.PLS = {data: {}, proj: '/a'}; globalThis.plChips = () => '<CHIPS/>'; globalThis.plApplySeg = () => '<APPLY/>';"
                " globalThis.plOverview = () => '<div class=plov>OV</div>';")
        js = "(() => { %s globalThis.plBody = ov => '<CV/>' + (ov || '') + '<div class=plrt></div>'; const a = plMainBody();" \
             " globalThis.plBody = () => '<EMPTY/>'; return [a, plMainBody()]; })()" % stub
        a, b = _js(js, "plMainBody")
        self.assertTrue(a.startswith("<div class=pltop><CHIPS/></div><APPLY/>"), a)
        self.assertEqual(a.count("class=plov>"), 1)
        self.assertLess(a.index("<CV/>"), a.index("class=plov>"))
        self.assertLess(a.index("class=plov>"), a.index("class=plrt"))
        self.assertEqual(b, "<div class=pltop><CHIPS/></div><APPLY/><EMPTY/><div class=plov>OV</div>")   # no canvas: overview at the body end, still under the chips
        self.assertIn("cv.html + (ov || '') + plRunTable(lv, p)", js_fn("plBody"))
        self.assertIn("cv.html + '</div>' + (ov || '') + plRunTable(lv, p)", js_fn("plBorrowBody"))



class StageOverview(unittest.TestCase):
    """Under the canvas: one row per stage (48b plStageRows / plRunTable)."""
    FNS = ("plStageRows", "plRunTable", "plPassTip", "plLabParts", "plgShow", "plgBase") + MODEL
    STUB = "globalThis.T = s => s; globalThis.KE = (k, e) => k; globalThis.ago = s => s + 's';"

    def _tbl(self, pr):
        oc = (re.search(r"^const PL_OUTCOME = [^\n]*$", js_all(), re.M).group(0).replace("const ", "", 1)
              + " globalThis.plOc = " + js_fn("plOc") + ";")
        js = "(() => { %s\n%s %s const lv = plPrLv('s<', %s, %s, %d); return [plStageRows(lv.lt, %s), plRunTable(lv, {stages: %s})]; })()" % (
            oc, ESC, self.STUB, json.dumps(pr), json.dumps(ST4), N * 1000, json.dumps(ST4), json.dumps(ST4))
        return _js(js, *self.FNS)

    def test_rows(self):
        rows, h = self._tbl(PR)
        self.assertEqual([(r["t"], r["st"], r["rb"], r["n"], r["sec"], r["ag"], r["type"]) for r in rows],
                         [("설계", "done", 0, 1, 100, 1, "dz"), ("구현", "run", 1, 2, 500, 2, "impl"), ("검증", "back", 0, 1, 100, 1, "main"),
                          ("리뷰", "wait", 0, 0, 0, 0, "")])
        self.assertEqual(h.count("<tr data-plst="), 3)                       # wait row: not clickable
        self.assertIn('<tr data-plst="구현" class=on>', h)
        self.assertIn("<tr class=plso-w>", h)
        self.assertIn("<td class=plrt-back><span class=plrtpl>↺ 되돌림</span>", h)
        self.assertIn("<td>↺ 1</td><td>2</td><td>500s</td>", h)
        self.assertEqual((h.count("<th>"), h.count("<col")), (6, 7))          # 6 columns (+ colgroup tag)
        self.assertIn('data-plsid="s&lt;"', h)

    def test_elapsed_per_pass(self):
        st = dict(PR["stages"], 구현=dict(PR["stages"]["구현"], p0=N - 100, k=3))
        rows, h = self._tbl(dict(PR, stages=st))
        self.assertEqual((rows[1]["sec"], rows[1]["tot"], rows[1]["k"], rows[0]["sec"]), (100, 500, 3, 100))   # no p0: t0
        self.assertIn('<td title="처음부터 500s · 3회째">100s</td>', h)

    def test_elapsed_lists_each_pass(self):
        st = dict(PR["stages"], 구현=dict(PR["stages"]["구현"], p0=N - 100, k=2, ps=[{"a": N - 500, "b": N - 300, "s": "back"}]))
        _rows, h = self._tbl(dict(PR, stages=st))
        self.assertIn('<td title="처음부터 500s · 2회째\n1회째 · 되돌림 · 200s\n2회째 · 진행 중 · 100s">100s</td>', h)

    def test_bash_only_stage_shows_main(self):
        st = dict(PR["stages"], 리뷰={"o": "done", "n": 0, "t0": N - 100, "t1": N - 50, "from": {}, "ag": [], "main": True})
        self.assertEqual(self._tbl(dict(PR, stages=st))[0][3]["type"], "main")   # server flag: no dispatch at all
        st["리뷰"] = {"o": "done", "n": 2, "t0": N - 100, "t1": N - 50, "from": {}}   # older run: no ag list, dispatches counted
        self.assertEqual(self._tbl(dict(PR, stages=st))[0][3]["type"], "")

    def test_hold_reason_tooltip(self):
        pr = dict(PR, stages=dict(PR["stages"], 구현=dict(PR["stages"]["구현"], o="hold", why="ask", ag=[])))
        rows, h = self._tbl(pr)
        self.assertEqual(rows[1]["st"], "hold")
        self.assertIn('<td class=plrt-hold title="질문 대기"><span class=plrtpl>⏸ 멈춤</span>', h)

    def test_lab_escaped(self):
        bad = '<img src=x onerror=alert(1)>": [pl:p/설계] x'
        pr = dict(PR, stages={"설계": dict(PR["stages"]["설계"], ag=[_pag("a1111111", False, N - 600, N - 500, bad)])})
        _rows, h = self._tbl(pr)
        self.assertNotIn("<img", h)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;&quot;", h)
        canvas = LoopBack()._cv("globalThis.esc = %s; return plNodeHtml(E, E.G.nodes[0], false, plPrLt(%s, [{title: '구현'}], 0));"
                                % (ESC.split("=", 1)[1].strip().rstrip(";"), json.dumps({"stages": {"구현": dict(PR["stages"]["구현"], ag=[_pag("a5", True, 0, 0, bad)])}})),
                                extra=MODEL + ("plLabTip", "plLabParts", "plLabDesc"))
        self.assertNotIn("<img", canvas)                                    # node hover title


class LoopBack(unittest.TestCase):
    """plrun `from` → loop-back edge pulse while the target re-runs, per-source badge (48d canvas)."""
    STUB = ("globalThis.T = s => s; globalThis.KE = (k, e) => LANG === 'en' ? e : k; globalThis.esc = s => String(s).replace(/</g, '&lt;');"
            " globalThis.ago = s => s + 's'; globalThis.plLabTip = s => s; globalThis.plgFam = () => 'cust'; globalThis.plgHue = () => ''; globalThis.plgPfc = () => '';"
            " globalThis.PL_JUDGED = []; globalThis.PL_LOW = [];")
    CANVAS = ("plEdgesSvg", "plPulseOn", "plVG", "plgNode", "plgW", "plgH", "plgFlowPath", "plgLoopLanes", "plgLoopPath", "plFlagChips", "plNodeHtml", "plEvRows", "plEvLine", "plPassSel", "plPass", "plAgLabs", "plAgLab")

    def _cv(self, body, extra=()):
        geo = re.search(r"^const PLG_W = [^\n]*$", js_all(), re.M).group(0).replace("const ", "", 1)   # sloppy-mode globals: the extracted functions live outside this IIFE
        oc = (re.search(r"^const PL_OUTCOME = [^\n]*$", js_all(), re.M).group(0).replace("const ", "", 1)
              + " globalThis.plOc = " + js_fn("plOc") + ";")
        G = {"defaults": {"model": "inherit"}, "flow": [["a", "b"], ["b", "c"]],
             "nodes": [{"id": "a", "title": "구현", "ui": {"x": 44, "y": 24}}, {"id": "b", "title": "검증", "ui": {"x": 300, "y": 24}},
                       {"id": "c", "title": "재검증", "ui": {"x": 560, "y": 24}}],
             "loops": [{"from": "b", "to": "a", "max": 2}, {"from": "c", "to": "a", "max": 2}]}
        return _js("(() => { %s\n%s\n%s const E = {G: %s, pxF: {}, pyF: {}}; %s })()" % (geo, oc, self.STUB, json.dumps(G), body), *(self.CANVAS + tuple(extra)))

    def test_badge_two_sources(self):
        r = self._cv("const L = {구현: {st: 'run', retry: 3, from: {'검증': 1, '재검증': 1}}}, n = E.G.nodes[0];"
                     " const ko = plNodeHtml(E, n, false, L); LANG = 'en'; const en = plNodeHtml(E, n, false, L); LANG = 'ko';"
                     " return [ko, en, plNodeHtml(E, n, false, {구현: {st: 'run', retry: 3}})];")
        self.assertIn('<span class=plrb title="↺ 검증에서 1 · 재검증에서 1">↺ 검증에서 1 · 재검증에서 1</span>', r[0])
        self.assertIn(">↺ 1 from Verify · 1 from Re-verify</span>", r[1])
        self.assertIn(">재시도 3</span>", r[2])                         # no from: the old retry badge

    def test_pass_picker_only_with_recorded_passes(self):
        L = "{st: 'done', k: %d, n: 1, sec: 9, w0: 0, ag: [], ps: %s}"
        ps = "[{a: 10, b: 20, s: 'back'}]"
        r = self._cv("return [plNodeHtml(E, E.G.nodes[0], false, {구현: %s}), plNodeHtml(E, E.G.nodes[0], false, {구현: %s}), plNodeHtml(E, E.G.nodes[0], false, {구현: %s})];"
                     % (L % (2, ps), L % (2, "[]"), L % (1, ps)))
        self.assertIn('<button type=button class="plpass" data-plpass="a" aria-haspopup=menu title="이전 회차 보기">↺2 ▾</button>', r[0])
        self.assertNotIn("plpass", r[1])                                   # legacy row: k>=2 but no ps
        self.assertNotIn("plpass", r[2])

    def test_picked_pass_drives_the_card(self):
        L = "{구현: {st: 'done', k: 2, n: 1, sec: 9, w0: 0, ag: [{aid: 'x', lab: 'impl: x', t0: 12, t1: 18}], ps: [{a: 10, b: 20, s: 'fail'}]}}"
        r = self._cv("const lt = %s; E.pass = {a: {k: 2, i: 0}}; const old = plNodeHtml(E, E.G.nodes[0], false, lt);"
                     " lt.구현.k = 3; const reset = plNodeHtml(E, E.G.nodes[0], false, lt); return [old, reset, E.pass];" % L)
        self.assertIn("pl-fail", r[0])
        self.assertIn("plx", r[0])
        self.assertIn('class="plpass on"', r[0])
        self.assertIn(">↺1 ▾</button>", r[0])
        self.assertIn("pl-done", r[1])                                     # k changed: back to the latest pass
        self.assertEqual(r[2], {})

    def test_flag_chips_readable(self):
        r = self._cv("const n = E.G.nodes[0]; Object.assign(n, {fanout: 'slices', onError: 'continue', produces: 'slices', onlyOnJump: true, parallel: 3});"
                     " const ko = plNodeHtml(E, n, false, null); LANG = 'en'; const en = plNodeHtml(E, n, false, null); LANG = 'ko'; return [ko, en];")
        ko, en = (re.search(r'<div class=plnc title="([^"]*)">(?:<span class=plunv[^>]*>[^<]*</span>)?([^<]*)</div>', h) for h in r)
        self.assertEqual(en.group(2), "Parallel 3 · Produces slices · Parallel slices · Only on jump · Continue on error")
        self.assertEqual(ko.group(2), "동시 3개 · 조각 나눔 · 병렬 분할 · 되돌아올 때만 · 실패해도 계속")
        self.assertEqual(len(en.group(1).split("\n")), 5)                 # one tooltip line per chip
        self.assertIn("Continue on error — A failed slice", en.group(1))

    def test_pulse_only_while_target_runs(self):
        h = self._cv("E.lt = {구현: {st: 'run', from: {'검증': 2}, via: '검증'}}; return plEdgesSvg(E);")
        segs = h.split('data-pledge="l:')
        self.assertIn('class="plel pulse"', segs[1])                       # 검증 → 구현 fired and 구현 re-runs
        self.assertNotIn("pulse", segs[2].split("<g ")[0])                 # 재검증 → 구현 never fired: plain dashed
        self.assertEqual(h.count(" pulse"), 1)
        self.assertIn("· ↺ 2", h)
        self.assertNotIn("<circle", h)                                     # the one-shot dot is gone

    def test_pulse_only_the_edge_of_the_current_pass(self):
        # Both edges fired earlier; only `via` (the loop-back that opened this pass) pulses. A forward pass (no via) pulses none.
        h = self._cv("E.lt = {구현: {st: 'run', from: {'검증': 2, '재검증': 1}, via: '재검증'}}; return plEdgesSvg(E);")
        segs = h.split('data-pledge="l:')
        self.assertNotIn("pulse", segs[1].split("<g ")[0])
        self.assertIn('class="plel pulse"', segs[2])
        self.assertEqual(h.count(" pulse"), 1)
        h = self._cv("E.lt = {구현: {st: 'run', from: {'검증': 2, '재검증': 1}}}; return plEdgesSvg(E);")
        self.assertNotIn("pulse", h)

    def test_gutter_pill_inside_viewbox(self):
        # 구현 at x=44 under a row-2 source: the gutter lane centres near x≈80, so a wide pill ran past x=0 (clipped)
        h = self._cv("E.G.nodes[2].ui = {x: 44, y: 300}; E.G.nodes.push({id: 'd', title: '설계', ui: {x: 44, y: 170}});"
                     " E.G.loops[1].then = '재검증 아주 긴 이름'; return plEdgesSvg(E);")
        xs = [float(x) for x in re.findall(r'<rect x="(-?[\d.]+)"', h)]
        self.assertTrue(xs and min(xs) >= 4, xs)

    def test_no_pulse_once_done(self):
        for st in ("done", "back", "fail", "wait"):
            h = self._cv("E.lt = {구현: {st: %s, from: {'검증': 2}}}; return plEdgesSvg(E);" % json.dumps(st))
            self.assertNotIn("pulse", h, st)
            self.assertIn("· ↺ 2", h)                                      # the count stays on the pill


class CssRules(unittest.TestCase):
    """43-pipeline.css: pulse + reduced motion, readable wait nodes, full-row canvas below 1000px."""
    CSS = open(__file__.rsplit("/tests/", 1)[0] + "/web/css/43-pipeline.css", encoding="utf-8").read()

    def test_pulse_and_reduced_motion(self):
        self.assertIn("html[data-ui] .plw .plel.pulse{", self.CSS)          # outranks html[data-ui=next] .plw .plel
        rm = re.search(r"@media \(prefers-reduced-motion:reduce\)\{html\[data-ui\] \.plw \.plel\.pulse\{([^}]*)\}", self.CSS)
        self.assertTrue(rm and "animation:none" in rm.group(1) and "stroke-dasharray:none" in rm.group(1))
        self.assertNotIn(".fired", self.CSS)
        self.assertNotIn("pldot", self.CSS)

    def test_overview_pulse_reduced_motion(self):
        self.assertRegex(self.CSS, r"\.plov-pulse \.plovdot::after\{[^}]*position:absolute[^}]*animation:plovpulse")   # absolute = no layout shift
        rm = re.search(r"@media \(prefers-reduced-motion:reduce\)\{\.plov-pulse \.plovdot::after\{([^}]*)\}", self.CSS)
        self.assertTrue(rm and "animation:none" in rm.group(1) and "opacity" in rm.group(1))   # static ring stays

    def test_wait_nodes_readable(self):
        self.assertNotRegex(self.CSS, r"\.pl-wait\{[^}]*opacity")   # parent opacity kept the «대기» pill at 3.5:1; dim by colour instead
        self.assertNotRegex(self.CSS, r"\.(wfnd\.pl-wait|pl-skip)\{[^}]*opacity")      # composited opacity put text under 4.5:1
        self.assertNotRegex(self.CSS, r"\.wfnd\.pl-wait\{[^}]*dashed")   # dashed = skip everywhere; Workflow wait is plain border + muted title
        self.assertIn("html[data-ui] .wfnd.pl-wait .plt{color:var(--nx-t2", self.CSS)
        self.assertIn("html[data-ui=next] .plw .plnd.pl-skip{border-style:dashed;border-color:var(--nx-t2)}", self.CSS)

    def test_back_amber_token(self):
        # one «back» token with a light value >=3:1; no hard-coded #d9a441 left in the canvas or the overview
        self.assertIn(":root{--pl-back:#d9a441}", self.CSS)
        light = open(__file__.rsplit("/tests/", 1)[0] + "/web/css/91-light.css", encoding="utf-8").read()
        self.assertIn("html[data-ui=next][data-theme=light]{--pl-back:#b45309}", light)
        self.assertIn(".plovst.plov-back{color:var(--pl-back)}", self.CSS)
        self.assertNotIn("d9a441", js_all())

    def test_counts_labelled(self):
        js = js_all()
        self.assertIn("TV({msg: 'Agents {n}/{m}'", js)          # Workflow summary counts agents
        self.assertIn("TV({msg: '{n}/{m} done', vars: {n: k, m: n}})", js)   # title bar counts finished stages
        self.assertNotIn("' · ' + k + ' / ' + n + ' · '", js)

    def test_canvas_full_row_when_narrow(self):
        # stacked at every width: side panes beside the canvas left 1440 narrower than 1100 (832 vs 1014px)
        self.assertNotIn("@container (max-width:1220px)", self.CSS)
        self.assertIn("6px var(--plpanh,minmax(420px,2fr))", self.CSS)   # one row handle; dragged pane height persists (sidereus.plpanh)
        self.assertIn(".plgw>.plgh{grid-area:2/1/3/3}", self.CSS)
        self.assertIn(".plgw{display:grid;grid-template-columns:minmax(220px,360px) minmax(0,1fr);", self.CSS)
        self.assertIn(".plgw>.plpan{grid-area:3/2/4/3}.plgw>.plpal{grid-area:3/1/4/2}", self.CSS)   # palette left, editor right
        # grid row 1 = canvas across both columns; rows fill the plGwFit height (a fixed 420px pane row left a blank under the run panels)
        self.assertIn(".plgw>.plcvw{grid-area:1/1/2/3}", self.CSS)
        self.assertIn("minmax(420px,2fr)", self.CSS)
        self.assertIn("floor = Math.round(row) + 426;", js_all())   # floor = plCvNeed canvas row + handle + default pane row
        self.assertIn("PLRO.observe(pw)", js_all())                      # in-place size changes re-fit too
        self.assertNotIn("@media (max-width:1000px){.plgw", self.CSS)
        self.assertIn("const PL_ZMIN = 0.8, PL_ZFIT = 0.4;", js_all())       # never raise the zoom floor instead


class CanvasFit(unittest.TestCase):
    """Auto-fit stays auto (48d): a best-wrap never marks the view touched, so a later canvas-height change re-wraps it."""

    def _run(self, body, ids="abcdef", extra=(), loops=()):
        geo = re.search(r"^const PLG_W = [^\n]*$", js_all(), re.M).group(0).replace("const ", "", 1)
        zm = re.search(r"^const PL_ZMIN = [^\n]*$", js_all(), re.M).group(0).replace("const ", "", 1)
        G = {"flow": [[c, d] for c, d in zip(ids, ids[1:])], "loops": [{"from": f, "to": t, "max": 1} for f, t in loops],
             "nodes": [{"id": c, "title": c, "ui": {"x": 44 + 248 * i, "y": 24}} for i, c in enumerate(ids)]}
        return _js("(() => { %s\n%s\n const E = {G: %s}; %s })()" % (geo, zm, json.dumps(G), body),
                   "plWrapBest", "plWrapCols", "plFitRaw", "plFit", "plFitKey", "plVG", "plgW", "plgH", "plgOrder", "plgLayout", "plgPush", "plgRows", "plgAlign", "plgNode", "plgRowH",
                   "plDrawBox", "plCentre", "plVisY", "plgLoopLanes", *extra)

    # Stub editor (globals: the extracted functions are top-level): feed 900 tall, editor top at 100, canvas column = toolbar 40 + canvas.
    DOM = ("mainView = 'pipe'; innerHeight = 1000; lsGet = () => 0; PL_SPLIT = {key: 'k', min: 200, cv: 200}; plCurEnt = () => E; plgKey = G => JSON.stringify(G.nodes);"
           " plApplyView = () => 0; plPaintEdgesNodes = () => 0; plZoomLabel = () => 0;"
           " fd = {clientTop: 0, scrollTop: 0, clientHeight: 900, scrollHeight: 900, getBoundingClientRect: () => ({top: 0})};"
           " g = {style: {height: ''}, getBoundingClientRect: () => ({top: 100})};"
           " cv = {clientWidth: 1000, get clientHeight(){ return parseFloat(g.style.height) - 40; }};"
           " g.querySelector = () => cv; document = {querySelector: () => g, getElementById: () => fd};"
           " getComputedStyle = () => ({paddingBottom: '0'});"
           " off = () => { const B = plDrawBox(plVG(E)), z = E.view.z; return [E.view.x + (B.l + B.r) / 2 * z - cv.clientWidth / 2, E.view.y + (B.t + B.b) / 2 * z - cv.clientHeight / 2]; };")

    def test_first_open_centres_then_camera_stays(self):
        # feed taller than the stacked floor (cf 620 + 426 = 1046), so the fill is what sets the height
        r = self._run(self.DOM + " fd.clientHeight = fd.scrollHeight = 1300; plGwFit(); const h = parseFloat(g.style.height); E.first = true; plWrapBest(E, cv, false); const a = off();"
                      " E.first = false; E.touched = true; E.view.x = 5; E.view.y = 7; fd.clientHeight = fd.scrollHeight = 1200; plGwFit();"   # resize after a pan
                      " return [h, a, E.view.x, E.view.y, parseFloat(g.style.height)];", ids="abcd", extra=("plGwFit", "plPanH"), loops=(("c", "b"), ("d", "b")))
        self.assertEqual(r[0], 1192)                                     # full height kept (fill to the feed bottom)
        self.assertLessEqual(max(abs(r[1][0]), abs(r[1][1])), 1)         # first open: drawn graph centred on both axes
        self.assertEqual(r[2:4], [5, 7])                                 # touched: re-sizing never moves the camera
        self.assertEqual(r[4], 1092)

    def test_fit_button_centres_and_later_fits_stay_centred(self):
        r = self._run(self.DOM + " plGwFit(); plWrapBest(E, cv, false); const x0 = E.view.x;"
                      " plWrapBest(E, cv, false, true); const a = off(); plWrapBest(E, cv, false); return [x0, a, off()];", ids="abcd", extra=("plGwFit", "plPanH"))
        self.assertEqual(r[0], 0)                                        # never centred: today's anchor
        self.assertLessEqual(max(abs(r[1][0]), abs(r[1][1])), 1)         # Fit to view (ctr) centres
        self.assertLessEqual(max(abs(r[2][0]), abs(r[2][1])), 1)         # a later untouched re-fit keeps it centred

    def test_stage_click_then_add_stays_centred(self):
        # first open -> stage click (E.first off) -> stage added (fit key changes) -> plGwFit re-fit
        r = self._run(self.DOM + " plGwFit(); E.first = true; E.ctrd = true; plWrapBest(E, cv, false); E.first = false;"
                      " E.G.nodes.push({id: 'e', title: 'e', ui: {x: 44 + 248 * 4, y: 24}}); E.G.flow.push(['d', 'e']);"
                      " const stale = E.fitK !== plFitKey(E, cv); plGwFit(); return [stale, off()];", ids="abcd", extra=("plGwFit", "plPanH"))
        self.assertTrue(r[0])
        self.assertLessEqual(max(abs(r[1][0]), abs(r[1][1])), 1)

    def test_pan_then_refit_keeps_camera(self):
        r = self._run(self.DOM + " plGwFit(); E.first = true; E.ctrd = true; plWrapBest(E, cv, false);"
                      " E.first = false; E.ctrd = false; E.touched = true; E.view.x = 5; E.view.y = 7;"   # what a pan sets
                      " E.G.nodes.push({id: 'e', title: 'e', ui: {x: 44 + 248 * 4, y: 24}}); plGwFit(); return [E.view.x, E.view.y];", ids="abcd", extra=("plGwFit", "plPanH"))
        self.assertEqual(r, [5, 7])

    def test_centre_in_visible_band(self):
        # canvas 515 tall starting at y=500 of a 900 window (feed 50..900): only rows 0..400 are on screen
        r = self._run("innerHeight = 900; document = {getElementById: () => ({scrollTop: 0, getBoundingClientRect: () => ({top: 50, bottom: 900})})};"
                      " const cv = {clientWidth: 1000, clientHeight: 515, clientTop: 0, getBoundingClientRect: () => ({top: 500})};"
                      " E.first = true; plWrapBest(E, cv, false); const B = plDrawBox(plVG(E)), z = E.view.z, v = E.visY;"
                      " const mid = E.view.y + (B.t + B.b) / 2 * z, top = E.view.y + B.t * z;"
                      " E.visY = [0, 130, E.visY[2]]; plCentre(E, cv); return [v.slice(0, 2), mid, top, E.view.y + B.t * z];", ids="abcd")
        self.assertEqual(r[0], [0, 400])
        self.assertLessEqual(abs(r[1] - 200), 1)                         # centred in the visible rows, not in all 515
        self.assertGreaterEqual(r[2], 0)
        self.assertGreaterEqual(r[3], 0)                                 # band shorter than the graph: never above the canvas top

    def test_scroll_never_recentres(self):
        r = self._run("innerHeight = 900; let st = 0; document = {getElementById: () => ({get scrollTop(){ return st; }, getBoundingClientRect: () => ({top: 50, bottom: 900})})};"
                      " const cv = {clientWidth: 1000, clientHeight: 515, clientTop: 0, getBoundingClientRect: () => ({top: 500 - st})};"
                      " E.first = true; plWrapBest(E, cv, false); const y0 = E.view.y; st = 300; plCentre(E, cv); return [y0, E.view.y];", ids="abcd")
        self.assertEqual(r[0], r[1])                                     # same place in the feed: the band from the fit is kept

    def test_empty_first_open_keeps_finite_view(self):
        r = self._run("const cv = {clientWidth: 900, clientHeight: 500}; E.first = true; plFit(E, cv, false); plCentre(E, cv);"
                      " return [E.view.x, E.view.y, E.view.z].every(Number.isFinite);", ids="")
        self.assertTrue(r)

    def test_wider_than_canvas_keeps_left_anchor(self):
        r = self._run("const cv = {clientWidth: 300, clientHeight: 200}; E.first = true; plFit(E, cv, false); return [E.view.x, E.view.z];")
        self.assertEqual(r, [0, 0.4])                                    # does not fit at the zoom floor: start of the chain stays in view

    def test_wrap_leaves_untouched(self):
        r = self._run("const cv = {clientWidth: 888, clientHeight: 282}; plWrapBest(E, cv, false); const z1 = E.view.z, k1 = E.fitK;"
                      " cv.clientHeight = 520; const stale = E.fitK !== plFitKey(E, cv); plWrapBest(E, cv, false);"
                      " return [!!E.touched, E.laid, k1, stale, z1, E.view.z];")
        self.assertEqual(r[:4], [False, True, "888x282/6", True])
        self.assertLess(r[4], 0.8)                                          # the short canvas forced a small fit
        self.assertGreaterEqual(r[5], 0.9)                                  # the settled height re-wraps to a readable zoom

    def test_fail_glyph_matches_strip(self):
        src = js_fn("plNodeHtml")
        self.assertIn("<b class=plx>\u2715</b>", src)
        self.assertNotIn("\u2717", src)


class RunPicker(unittest.TestCase):
    """Earlier runs of the live session (plrun `past`): plViewRun pick, head picker, menu labels escaped (48b)."""
    FNS = ("plViewRun", "plRunNav", "plRunLab", "plRunPick", "plLiveHead", "plRvOpen", "plRvClose", "plLiveRun", "plProjSess", "plMem", "plRunName", "plSubsOf") + MODEL
    PAST = {"rid": N - 5000, "t0": N - 5000, "t1": N - 4000, "end": N - 4000, "cur": "", "lab": "old <img src=x>",
            "stages": {"설계": {"o": "done", "n": 1, "t0": N - 5000, "t1": N - 4000, "from": {}}}}

    def _run(self, body, past=True, sel="null"):
        pr = dict(PR, rid=N - 600, lab="now", **({"past": [self.PAST]} if past else {}))
        stub = ("%s Date.now = () => %d; Object.assign(globalThis, {SESS: %s, PLS: {runSel: %s, proj: '/x/api', data: {'/x/api': {pipelines: [{name: 'p', stages: %s}]}}},"
                " lsJson: () => ({}), hhmm: t => 'H' + t, sid8: s => s, ago: s => s + 's', plCur: () => ({name: 'p'}), window: {innerWidth: 1440},"
                " document: {getElementById: () => null, createElement: () => ({style: {}, setAttribute(){}}), body: {appendChild(el){ globalThis.EL = el; }}}});"
                % (ESC, N * 1000, json.dumps([{"sid": "a", "cwd": "/x/api", "plrun": [pr]}]), sel, json.dumps(ST4)))
        return _js("(() => { %s %s })()" % (stub, body), *self.FNS)

    def test_default_is_live(self):
        self.assertEqual(self._run("const v = plViewRun('/x/api', 'p'); return [v.pr.rid, v.lt['구현'].st, plRunNav(v).k, plRunNav(v).N];"), [N - 600, "run", 2, 2])

    def test_pick_shows_that_run(self):
        sel = json.dumps({"sid": "a", "name": "p", "rid": N - 5000, "cur": N - 600})
        r = self._run("const v = plViewRun('/x/api', 'p'); return [v.lt['설계'].st, v.lt['구현'].st, v.nav.k, !!PLS.runSel, plLiveHead(v, v.lt)];", sel=sel)
        self.assertEqual(r[:4], ["done", "wait", 1, True])                   # only the picked run's stages
        self.assertIn("data-plrvb", r[4])                                   # «Back to current»
        self.assertIn("plrunst old", r[4])

    def test_pick_dropped_when_rid_changes(self):
        sel = json.dumps({"sid": "a", "name": "p", "rid": N - 5000, "cur": N - 9})
        self.assertEqual(self._run("const v = plViewRun('/x/api', 'p'); return [v.pr.rid, PLS.runSel];", sel=sel), [N - 600, None])

    def test_picker_only_with_past(self):
        h = self._run("const v = plViewRun('/x/api', 'p'); return [plLiveHead(v, v.lt), plLiveHead(Object.assign({}, v, {pr: Object.assign({}, v.pr, {past: []})}), v.lt)];")
        self.assertIn("data-plrv ", h[0])
        self.assertNotIn("data-plrv", h[1])
        self.assertNotIn("data-plrv", self._run("const v = plViewRun('/x/api', 'p'); return plLiveHead(v, v.lt);", past=False))

    def test_menu_label_escaped(self):
        h = self._run("plRvOpen({left: 10, bottom: 20}); return EL.innerHTML;")
        self.assertNotIn("<img", h)
        self.assertIn("old &lt;img src=x&gt;", h)
        self.assertEqual(h.count("data-plrvi="), 2)                          # current + one earlier run


if __name__ == "__main__":
    unittest.main()

