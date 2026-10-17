"""GET /api/pipelines/eval body (sidereus/pl_eval_view.py) and its header/panel render (web/js/48i). No live files."""
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import types
import unittest

from tests._load import ROOT, sidereus, js_fn
from tests._node import node_e

PIPE = {"name": "flow", "title": "Flow", "defaults": {"model": "inherit", "retry": 0}, "rules": "",
        "stages": [{"title": "build", "agent": "a", "gate": "make test"}, {"title": "check", "agent": "a", "gate": "make check"},
                   {"title": "review", "agent": "a"}]}


class EvalApi(unittest.TestCase):
    def setUp(self):
        self.v = sidereus("pl_eval_view")
        self.proj = tempfile.mkdtemp(prefix="pl-eval-")
        d = os.path.join(self.proj, ".claude", "pipelines")
        os.makedirs(d)
        with open(os.path.join(d, "flow.json"), "w", encoding="utf-8") as f:
            json.dump(PIPE, f)
        pp, sc = sidereus("pipeline_projects"), sidereus("pl_scorecard")
        self._saved = [(pp, "_proj_ok", pp._proj_ok), (self.v, "_pe", self.v._pe), (self.v, "_head", self.v._head),
                       (sc, "scorecard", sc.scorecard)]
        sc.scorecard = lambda p, head: {"n": 1, "m": 2, "path": p, "checks": [
            {"id": "license", "v": "pass", "file": "LICENSE"}, {"id": "sast-gate", "v": "fail"}, {"id": "zz", "v": "pass"},
            {"id": "pinned-deps", "v": "na"}]}
        pp._proj_ok = lambda p: p == self.proj
        self.v._head = lambda p: "a" * 40
        self.calls = []

        def graded(P, root, now):
            self.calls.append((P["name"], root))
            red = {"build": "pass", "check": "pass"}
            flaky = {"check"}
            gated = [s["title"] for s in P["stages"] if s.get("gate")]
            return {"n": len([t for t in gated if red.get(t) == "pass" and t not in flaky]), "m": len(P["stages"]),
                    "unred": [t for t in gated if red.get(t) != "pass"], "unstable": sorted(flaky)}
        fake = types.SimpleNamespace(
            load_eval=lambda key, commit: {"stages": [{"title": "build", "n": 8, "caught": 7, "missed": ["case-17"]}],
                                           "holdout": {"n": 12, "caught": 10, "ids": ["secret-case"]}},
            redcheck_status=lambda name, stages: {"build": {"verdict": "pass", "why": "x", "at": 1}, "check": {"verdict": "weird"}},
            graded_summary=graded, gate_agreement=lambda P, root, now, head: {"check": {"k": 2, "n": 3}, "zz": {"k": 1, "n": 1}})
        self.v._pe = lambda: fake

    def tearDown(self):
        for mod, k, val in self._saved:
            setattr(mod, k, val)
        shutil.rmtree(self.proj, ignore_errors=True)

    def test_body_shape(self):
        code, b = self.v.pl_eval(self.proj, "flow")
        self.assertEqual(code, 200)
        self.assertEqual(set(b), {"ok", "name", "graded", "stages", "holdout", "commit", "sugg", "security"})
        self.assertEqual(b["graded"], {"n": 1, "m": 3, "unred": 0, "unstable": ["check"]})   # check is red-checked but flaky
        self.assertEqual(b["stages"], [
            {"title": "build", "catch": {"caught": 7, "n": 8}, "red": "pass", "unstable": False, "ci": {"lo": 53, "hi": 98},
             "agree": None},
            {"title": "check", "catch": None, "red": "none", "unstable": True, "ci": None, "agree": {"k": 2, "n": 3}},   # unknown verdict -> none
            {"title": "review", "catch": None, "red": "none", "unstable": False, "ci": None, "agree": None}])
        self.assertEqual(self.calls, [("flow", self.proj)])

    def test_counts_only(self):
        _c, b = self.v.pl_eval(self.proj, "flow")
        self.assertEqual(b["holdout"], {"n": 12, "caught": 10, "ci": {"lo": 55, "hi": 95}})
        s = json.dumps(b)
        self.assertNotIn("secret-case", s)
        self.assertNotIn("case-17", s)
        self.assertNotIn("why", s)

    def test_security_block(self):   # R4: id/v/n/m only, unknown ids and extra keys dropped
        _c, b = self.v.pl_eval(self.proj, "flow")
        self.assertEqual(b["security"], {"n": 1, "m": 2, "checks": [{"id": "license", "v": "pass"}, {"id": "sast-gate", "v": "fail"},
                                                                     {"id": "pinned-deps", "v": "na"}]})
        self.v._pe = lambda: None   # shown without the eval core too
        self.assertEqual(self.v.pl_eval(self.proj, "flow")[1]["security"]["n"], 1)
        self.assertIsNone(self.v.body("f", [], None, None, None, "")["security"])

    def test_wilson(self):
        w = self.v.wilson
        self.assertEqual((w(7, 7), w(0, 1), w(0, 0), w(5, 6)), ({"lo": 65, "hi": 100}, {"lo": 0, "hi": 79}, None, {"lo": 44, "hi": 97}))
        self.assertIsNone(w(3, 2))

    def test_guards(self):
        self.assertEqual(self.v.pl_eval("/nope", "flow")[0], 400)
        self.assertEqual(self.v.pl_eval(self.proj, "../x")[0], 400)
        self.assertEqual(self.v.pl_eval(self.proj, "other")[0], 400)

    def test_core_missing(self):
        self.v._pe = lambda: None
        code, b = self.v.pl_eval(self.proj, "flow")
        self.assertEqual(code, 200)
        self.assertIsNone(b["graded"])
        self.assertIsNone(b["holdout"])
        self.assertEqual([s["red"] for s in b["stages"]], ["none"] * 3)

    def test_real_core(self):
        pe = sidereus("pl_eval")
        saved = [(pe, k, getattr(pe, k)) for k in ("_red_gates", "flaky_modes", "load_eval")]
        try:
            pe._red_gates = lambda: {pe.gate_key("make test"): {"verdict": "pass"}}
            pe.flaky_modes = lambda root, now: set()
            pe.load_eval = lambda key, commit: None
            self.v._pe = lambda: pe
            _c, b = self.v.pl_eval(self.proj, "flow")
            self.assertEqual(b["graded"], {"n": 1, "m": 3, "unred": 1, "unstable": []})   # check has a gate but no red pass
            self.assertEqual([s["red"] for s in b["stages"]], ["pass", "none", "none"])
            self.assertIsNone(b["holdout"])
        finally:
            for mod, k, val in saved:
                setattr(mod, k, val)

    def test_demo(self):
        # demo_tools keeps a fixed copy (core may not import the pipeline feature); it must still be body()'s output
        from sidereus import demo_tools as d
        ev = {"stages": [{"title": "구현", "n": 8, "caught": 7}, {"title": "검증", "n": 6, "caught": 5}],
              "holdout": {"n": 12, "caught": 10}}
        red = {"구현": {"verdict": "pass"}, "검증": {"verdict": "none"}, "리뷰": {"verdict": "skip"}}
        sg = [d.DEMO_EVAL["sugg"][0], {"code": "redcheck", "stage": "검증",
                                       "cmd": self.v.redcheck_cmd("/demo", "change-flow", "검증", code_dir="/sidereus", nt=False)}]
        ag = {"구현": {"k": 3, "n": 3}, "검증": {"k": 2, "n": 3}}
        want = self.v.body("change-flow", ["설계", "구현", "검증", "리뷰"], ev, red, d.DEMO_EVAL["graded"], "3f9c2ab0d1e2", sg, ag,
                           sec=d.DEMO_EVAL["security"])
        code, b = d._demo_eval("/demo", "/demo", "change-flow")
        self.assertEqual((code, b), (200, want))
        self.assertEqual(d._demo_eval("/x", "/demo", "change-flow")[0], 400)

STUBS = """
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const I18N = { ko: {} };
"""
EV = {"ok": True, "graded": {"n": 1, "m": 4, "unred": 2, "unstable": ["<b>"]},
      "stages": [{"title": "<b>", "catch": {"caught": 7, "n": 8}, "red": "pass", "unstable": True, "ci": {"lo": 53, "hi": 98},
                  "agree": {"k": 2, "n": 3}},
                 {"title": "y", "catch": None, "red": "none", "unstable": False}],
      "holdout": {"n": 12, "caught": 10}, "commit": "a" * 12}


def _node(body, lang="en"):
    with open(os.path.join(ROOT, "web", "js", "06-i18n-zx-eval.js"), encoding="utf-8") as fh:
        ko = fh.read()
    fns = "\n".join(js_fn(f) for f in ("T", "TV", "plEvalCov", "plEvalHead", "plEvalCi", "plEvalAgree", "plEvalPanel", "plEvalSgList", "plEvalSgMsg",
                                         "plEvalSgEn", "plEvalSgHtml", "plEvalFixBody", "archChkReqKey", "archChkGoLabel", "archChkSentHtml"))
    with open(os.path.join(ROOT, "web", "js", "48i-pipeline-eval.js"), encoding="utf-8") as fh:
        src = fh.read()
    sg = src[src.index("const PLE_SG = "):src.index("function plEvalSgList")]
    red = "const PLE_RED = { pass: 'pass', fail: 'fail', skip: 'skip' };\n" + sg + \
        "\nconst archChkCandLabel = c => c.sid; const plEvalCands = () => [{sid: 's<1>', login: true, id: 'm'}];"
    code = "let LANG = %s;\n" % json.dumps(lang) + STUBS + ko + "\nI18N.ko['Stage'] = '단계';\n" + red + "\n" + fns + "\n" + body
    r = subprocess.run(node_e(code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class EvalUi(unittest.TestCase):
    def test_cov_override(self):
        r = _node("const ev = %s; console.log(JSON.stringify([plEvalCov({n: 3, m: 4}, ev, false), plEvalCov({n: 3, m: 4}, ev, true),"
                  " plEvalCov({n: 3, m: 4}, null, false)]));" % json.dumps(EV))
        self.assertEqual(r, [{"n": 1, "m": 4}, {"n": 3, "m": 4}, {"n": 3, "m": 4}])

    def test_head(self):
        r = _node("console.log(JSON.stringify([plEvalHead(%s, false), plEvalHead(null, false)]));" % json.dumps(EV))
        self.assertIn("gate not red-checked 2", r[0])
        self.assertIn("data-pleval", r[0])
        self.assertEqual(r[1], "")
        ko = _node("console.log(JSON.stringify(plEvalHead(%s, true)));" % json.dumps(EV), lang="ko")
        self.assertIn("게이트 red 미확인 2", ko)
        self.assertIn("평가", ko)

    def test_panel_escapes(self):
        r = _node("console.log(JSON.stringify(plEvalPanel(%s)));" % json.dumps(EV))
        self.assertNotIn("<b>", r)
        self.assertIn("&lt;b>", r)
        self.assertIn("7/8", r)
        self.assertIn("unstable", r)
        self.assertIn("Holdout", r)
        self.assertIn("10/12", r)
        self.assertNotIn("No evaluation yet", r)
        self.assertIn("95% 53–98%", r)
        self.assertIn("the range narrows", r)
        self.assertIn("2/3 agree", r)
        ko = _node("console.log(JSON.stringify(plEvalPanel(%s)));" % json.dumps(EV), lang="ko")
        self.assertIn("불안정", ko)
        self.assertIn("통과", ko)
        self.assertIn("2/3 일치", ko)

    def test_panel_empty(self):
        e = {"stages": [{"title": "x", "catch": None, "red": "none", "unstable": False}], "holdout": None}
        self.assertIn("No evaluation yet", _node("console.log(JSON.stringify(plEvalPanel(%s)));" % json.dumps(e)))


TPLS = [{"id": "dep-audit", "group": "security", "title": {"ko": "의존"}, "gate": "python3 x/arch_checks.py --verify --last --category security",
         "tools": [{"id": "npm-audit"}]},
        {"id": "sast", "group": "security", "title": {"ko": "정적"}, "gate": "python3 x/arch_checks.py --verify --last --category security",
         "tools": [{"id": "semgrep"}, {"id": "bandit"}]},
        {"id": "secrets", "group": "security", "title": {"ko": "비밀"}, "gate": "python3 x/arch_checks.py --verify --last --category security",
         "tools": [{"id": "gitleaks"}, {"id": "semgrep"}]},
        {"id": "secret-scan", "group": "security", "title": {"ko": "비밀값"}, "gate": "python3 x/arch_checks.py --verify --last --category security",
         "tools": [{"id": "gitleaks"}]},
        {"id": "unit-tests", "group": "test", "title": {"ko": "단위 테스트"}, "tools": []},
        {"id": "review", "group": "review", "title": {"ko": "리뷰"}, "tools": []}]


class Suggest(unittest.TestCase):
    def setUp(self):
        self.v = sidereus("pl_eval_view")

    def sg(self, stages, ev=None, red=None, unstable=(), kinds=None):
        return self.v.suggest(stages, ev, red, set(unstable), kinds or {}, TPLS, lambda t: "cmd " + t)

    def test_rule_table(self):
        ev = {"stages": [{"title": "impl", "n": 3, "caught": 1}], "holdout": {"n": 4, "caught": 2}}
        st = [{"title": "impl", "agent": "dev"}, {"title": "chk", "agent": "dev", "gate": "scripts/check.sh --fast"},
              {"title": "sec", "agent": "dev", "gate": "python3 a/arch_checks.py --verify --category security"}]
        out = self.sg(st, ev, {"chk": "fail"}, unstable=["sec"], kinds={"impl": ["dep", "logic", "secret"]})
        self.assertEqual(out, [
            {"code": "add-gate", "stage": "impl", "kind": "secret", "tpl": "secret-scan"},   # fewest tools wins
            {"code": "add-gate", "stage": "impl", "kind": "dep", "tpl": "dep-audit"},     # logic has no tool gate
            {"code": "tighten-gate", "stage": "chk", "mode": "fast", "flags": "--fast", "tpl": ""},
            {"code": "unstable", "stage": "sec", "mode": "checks-security"},
            {"code": "redcheck", "stage": "sec", "cmd": "cmd sec"},
            {"code": "add-review", "tpl": "review"}])

    def test_sast_add_gate(self):
        ev = {"stages": [{"title": "impl", "n": 1, "caught": 0}]}
        self.assertEqual(self.sg([{"title": "impl", "agent": "dev"}], ev, kinds={"impl": ["sast"]}),
                         [{"code": "add-gate", "stage": "impl", "kind": "sast", "tpl": "sast"}])

    def test_quiet_cases(self):
        st = [{"title": "chk", "agent": "a-reviewer", "gate": "scripts/check.sh --fast"}]
        self.assertEqual(self.sg(st, None, None), [])                        # core absent: no red rules
        self.assertEqual(self.sg(st, None, {"chk": "pass"}), [])
        ev = {"stages": [], "holdout": {"n": 2, "caught": 1}}
        self.assertEqual(self.sg(st, ev, {"chk": "skip"}), [])                # a review agent exists
        self.assertEqual(self.sg([{"title": "단위 테스트", "agent": "x"}], ev, {}), [])   # a test catalog stage exists

    def test_cmd_quoted(self):
        c = self.v.redcheck_cmd("/p q", "flow", "it's", code_dir="/ag", nt=False)   # POSIX quoting; joins still use os.sep
        self.assertIn("--pipeline '%s'" % os.path.join("/p q", ".claude", "pipelines", "flow.json"), c)
        self.assertIn("--stage 'it'\"'\"'s' --repo '/p q'", c)
        # ⚠shlex quotes a `\` path (os.sep on Windows), so compare against the quoted script path
        self.assertTrue(c.startswith("python3 ") and shlex.quote(os.path.join("/ag", "scripts", "pl_eval.py")) + " redcheck" in c)
        w = self.v.redcheck_cmd("C:\\p q", "flow", "a b", code_dir="C:\\ag", nt=True)
        self.assertTrue(w.startswith("py ") and '--stage "a b"' in w)

    def test_missed_kinds_no_holdout(self):
        pe = types.SimpleNamespace(load_seeds=lambda p: {"seeds": [{"id": "a", "kind": "dep"}, {"id": "h", "kind": "secret", "holdout": True}]})
        k = self.v._missed_kinds(pe, "/x", {"stages": [{"title": "s", "missed": ["a", "h"]}]})
        self.assertEqual(k, {"s": ["dep"]})


SG_EV = dict(EV, sugg=[{"code": "redcheck", "stage": "y", "cmd": "python3 x '<i>'"},
                       {"code": "add-gate", "stage": "<x>", "kind": "dep", "tpl": "<t>"},
                       {"code": "nope", "stage": "z"}])


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SuggestUi(unittest.TestCase):
    def test_badge_and_list_escape(self):
        r = _node("console.log(JSON.stringify([plEvalPanel(%s), plEvalHead(%s, false)]));" % (json.dumps(SG_EV), json.dumps(SG_EV)))
        self.assertNotIn("<x>", r[0])
        self.assertNotIn("<i>", r[0] + r[1])
        self.assertNotIn("<t>", r[0])
        self.assertIn('data-plecp="python3 x \'&lt;i>\'"', r[0])   # badge copies the exact command
        self.assertIn("red check needed", r[0])
        self.assertIn("red check needed:\npython3 x", r[1])
        self.assertEqual(r[0].count("data-plsg="), 2)   # unknown code dropped
        self.assertIn("data-plsask", r[0])
        ko = _node("console.log(JSON.stringify(plEvalPanel(%s)));" % json.dumps(SG_EV), lang="ko")
        self.assertIn("red 확인 필요", ko)
        self.assertIn("직접 고치기", ko)

    def test_preview_and_body(self):
        r = _node("const S = {sel: {0: 1}, req: {sid: 's<1>', body: plEvalFixBody('/p', 'flow', [%s])}, sent: '', msg: ''};"
                  "console.log(JSON.stringify(plEvalSgHtml(%s, S, plEvalCands(), null)));"
                  % (json.dumps(SG_EV["sugg"][1]), json.dumps(SG_EV)))
        self.assertIn("data-plsgo", r)
        self.assertIn("Please improve pipeline flow in /p", r)
        self.assertIn("add a gate like «&lt;t>»", r)
        self.assertNotIn("<t>", r)

    def test_preview_shows_resolved_recipient(self):
        r = _node("const c = [{sid: 's<1>', login: true, ran: true}, {sid: 's2', login: true}];"
                  "const S = {sel: {0: 1}, req: {sid: 's<1>', pick: false, body: 'b'}, sent: '', msg: ''};"
                  "const a = plEvalSgHtml(%s, S, c, null); S.req.pick = true;"
                  "console.log(JSON.stringify([a, plEvalSgHtml(%s, S, c, null), plEvalSgHtml(%s, S, c.slice(0, 1), null)]));"
                  % ((json.dumps(SG_EV),) * 3))
        self.assertIn("s&lt;1> · ran this pipeline", r[0])
        self.assertIn("data-plsch", r[0])          # «Change» link only when there are other candidates
        self.assertNotIn("data-plss", r[0])
        self.assertIn("data-plss", r[1])
        self.assertIn("data-plsgo", r[0])


RECIP = """
const archBase = p => String(p || '').split('/').pop();
function archChkFixCands(sess, p){ return (sess || []).filter(x => x.state !== 'done' && String(x.cwd || '').startsWith(p))
  .map(x => ({ sid: x.sid, login: !!x.mbox, dir: archBase(x.cwd), age: +x.ageSec || 0 })); }
"""


def _recip(body):
    code = RECIP + "\n".join(js_fn(f) for f in ("plEvalRecips", "plEvalPick", "plEvalPre")) + "\n" + body
    r = subprocess.run(node_e(code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class AskAiRecipient(unittest.TestCase):
    RUN = {"name": "flow", "proj": "/p", "t1": 5}

    def _sess(self, **kw):
        base = {"sid": "x", "cwd": "/p", "state": "wait", "mbox": "m", "mboxSrc": "identity", "plrun": []}
        base.update(kw)
        return base

    def test_order_run_then_repo_then_none(self):
        ss = [self._sess(sid="repo", ageSec=1), self._sess(sid="old", cwd="/elsewhere", plrun=[dict(self.RUN, t1=1)]),
              self._sess(sid="new", cwd="/elsewhere", plrun=[self.RUN]), self._sess(sid="other", plrun=[dict(self.RUN, name="x")])]
        r = _recip("const ss = %s; console.log(JSON.stringify([plEvalRecips(ss, '/p', 'flow', '').map(c => c.sid),"
                   " plEvalRecips(ss, '/p', 'flow', 'old').map(c => c.sid), plEvalPick(plEvalRecips(ss, '/p', 'flow', '')).sid]));" % json.dumps(ss))
        self.assertEqual(r[0], ["new", "old", "repo", "other"])   # run sessions newest first, then the repo rule
        self.assertEqual(r[1][0], "old")                           # the lighting model's run session leads
        self.assertEqual(r[2], "new")

    def test_gone_run_session_falls_back_and_none(self):
        ss = [self._sess(sid="ran", cwd="/elsewhere", state="gone", plrun=[self.RUN]), self._sess(sid="repo")]
        r = _recip("const ss = %s; console.log(JSON.stringify([plEvalRecips(ss, '/p', 'flow', 'ran').map(c => [c.sid, !!c.ran]),"
                   " plEvalRecips([], '/p', 'flow', ''), plEvalPick([])]));" % json.dumps(ss))
        self.assertEqual(r[0], [["repo", False]])
        self.assertEqual(r[1], [])
        self.assertIsNone(r[2])

    def test_prechecked_once(self):
        r = _recip("const S = {sel: {}, init: false}; plEvalPre(S, [1, 2]); delete S.sel[0]; plEvalPre(S, [1, 2]);"
                   " console.log(JSON.stringify(S.sel));")
        self.assertEqual(r, {"1": 1})

    def test_send_only_from_confirm(self):
        with open(os.path.join(ROOT, "web", "js", "48i-pipeline-eval.js"), encoding="utf-8") as fh:
            src = fh.read()
        ask = src[src.index("if(t.closest('[data-plsask]'))"):src.index("if(t.closest('[data-plsgo]'))")]
        self.assertNotIn("plEvalFixSend", ask)   # «Ask AI» and «Change» only open/adjust the preview
        self.assertNotIn("postJSON", ask)
        fn = src[src.index("async function plEvalFixSend"):src.index("document.addEventListener('change'")]
        code = ("let sent = 0; const postJSON = async () => { sent++; return {ok: true}; }; const plPaint = () => {}; const T = s => s;"
                "const PLS = {proj: '/p'}; const plCur = () => ({name: 'flow'}); const plEvalOf = () => ({}); const plEvalSgList = () => [{code: 'redcheck'}];"
                "const archChkCandLabel = c => c.sid; const plEvalCands = () => [{sid: 's', id: 'm', login: true}];"
                "const archChkReqKey = (a, b) => a + '\\n' + b; const hhmm = () => '14:05'; const note = () => {};"
                "let PLEVAL_S = {sel: {0: 1}, req: null};\n" + fn +
                "\n(async () => { const a = await plEvalFixSend(); PLEVAL_S.req = {sid: 's', body: 'b', busy: false};"
                " const b = await plEvalFixSend(); console.log(JSON.stringify([a, sent, b])); })();")
        r = subprocess.run(node_e(code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        self.assertEqual(json.loads(r.stdout), [False, 1, True])   # no preview -> nothing sent

    def test_sent_line_inflight_and_repeat(self):
        with open(os.path.join(ROOT, "web", "js", "48i-pipeline-eval.js"), encoding="utf-8") as fh:
            src = fh.read()
        fn = src[src.index("async function plEvalFixSend"):src.index("document.addEventListener('change'")]
        body = ("const plPaint = () => { HTML.push(plEvalSgHtml(%s, PLEVAL_S, plEvalCands(), null)); }; let HTML = [], POSTS = 0, PEND = null, NOTES = 0;"
                "const postJSON = () => { POSTS++; return new Promise(r => { PEND = r; }); }; const note = () => { NOTES++; };"
                "const PLS = {proj: '/p'}; const plCur = () => ({name: 'flow'}); const plEvalOf = () => ({});"
                "let PLEVAL_S = {sel: {0: 1}, req: null, sent: '', msg: ''};\n" + fn + "\n(async () => {"
                " const q = () => ({sid: 's<1>', body: 'b', busy: false, pick: false});"
                " PLEVAL_S.req = q(); const p1 = plEvalFixSend(); const busy = HTML[HTML.length - 1]; const dup = await plEvalFixSend(), n0 = POSTS;"
                " PEND({ok: true}); await p1; const ok = HTML[HTML.length - 1];"
                " PLEVAL_S.req = q(); plPaint(); const again = HTML[HTML.length - 1]; const r1 = await plEvalFixSend(), n1 = POSTS;"
                " const p2 = plEvalFixSend(); PEND({ok: false, error: 'boom'}); await p2;"
                " console.log(JSON.stringify([busy, dup, n0, ok, again, r1, n1, HTML[HTML.length - 1], NOTES])); })();") % json.dumps(SG_EV)
        r = _node("const hhmm = () => '14:05';" + body.replace("const plEvalOf = () => ({});", "const plEvalOf = () => (%s);" % json.dumps(SG_EV)))
        self.assertIn("data-plsgo disabled", r[0])   # confirm disabled while the POST is in flight
        self.assertEqual([r[1], r[2]], [False, 1])
        self.assertIn('class="archckst archsent"', r[3])
        self.assertIn("Requested → s&lt;1> · 14:05", r[3])
        self.assertIn("Sent · send again", r[4])     # same suggestions + same session
        self.assertEqual([r[5], r[6]], [False, 1])   # first click only arms
        self.assertIn('class="archmsg archerr" role=alert', r[7])
        self.assertIn("boom", r[7])
        self.assertEqual(r[8], 1)


if __name__ == "__main__":
    unittest.main()
