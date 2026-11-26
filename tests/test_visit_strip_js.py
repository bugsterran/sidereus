"""web/js/48n-pipeline-visit.js «Since your last visit» strip: counts for (since, at], metadata-only items,
the 10-minute gap rule, Dismiss, caps. One node run per test; storage, clock and DOM are stubs."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn, sidereus
from tests._node import node_e

STUBS = r"""
let NOW = 100000, LSM = {}, LSBAD = false, PAINT = 0, FIT = 0, PICK = [], CPGO = [], ATTGO = [], RESP = [], BODY = [];
Date.now = () => NOW * 1000;
const localStorage = {
  getItem(k){ if(LSBAD) throw new Error('blocked'); return k in LSM ? LSM[k] : null; },
  setItem(k, v){ if(LSBAD) throw new Error('blocked'); LSM[k] = String(v); }};
const ISPOP = false, ISWP = false, ISBP = false, LANG = 'en';
let mainView = 'pipe', SESS = [], PLS = { runSel: null, data: {'/w/shop': {ok: true, pipelines: [{name: 'change', stages: [{title: 'implement'}, {title: 'review'}]}]}} };
function T(s){ return s; }
function esc(s){ return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function hhmm(t){ const d = new Date(t * 1000), z = n => String(n).padStart(2, '0'); return z(d.getUTCHours()) + ':' + z(d.getUTCMinutes()); }
function softErr(){}
function attnRows(){ return { resp: RESP }; }
function plPaint(){ PAINT++; } function plFitSoon(){ FIT++; }
function setMainView(v){ mainView = v; }
function plOvPick(p, n, s){ PICK.push([p, n, s]); PLS.runSel = null; }
function plNowLive(ss){ return (ss || []).filter(x => x && !['done', 'abort', 'gone'].includes(x.state)); }   // 48j stand-in: visitGo marks «Working now» only for a live pinned sid
function actAttnGo(x){ ATTGO.push(x.sid); return true; }
function cpGo(x){ CPGO.push(x.sid); }
const window = { innerWidth: 1920 };
const document = { hidden: false, getElementById(){ return null; },
  createElement(){ return { style: {}, setAttribute(){}, remove(){} }; }, body: { appendChild(el){ BODY.push(el); } } };
"""
FNS = ("visitLoad", "visitSave", "visitVerdict", "visitDefs", "visitDefsLoad", "visitCollect", "visitVdLab", "visitHtml", "visitStripHtml", "visitItemHtml",
       "visitList", "visitPopClose", "visitOpen", "visitGo", "visitSet", "visitTick", "visitDismiss", "visitAway")


def _consts():
    src = js_all()
    out = [m.group(0) for m in re.finditer(r"^const VISIT_[A-Z_]+ = .*$", src, re.M)]
    out.append(re.search(r"^let VISIT = .*$", src, re.M).group(0))
    return "\n".join(out)


def run(body):
    js = STUBS + _consts() + "\n" + "\n".join(js_fn(n) for n in FNS) + "\n" + body
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def out(expr):
    return "\nprocess.stdout.write(JSON.stringify(" + expr + "));"


def st(o, t1, **kw):
    d = {"o": o, "n": 1, "t0": t1 - 10, "t1": t1}
    d.update(kw)
    return d


# One session: the current run passed, earlier runs failed / unknown; a planted lab must never render.
SESS = [{"sid": "abcdef1234567890", "cwd": "/w/shop", "state": "run", "ageSec": 5, "plrun": [{
    "name": "change", "proj": "/w/shop", "sid": "abcdef1234567890", "rid": 1500, "lab": "SECRET-LAB", "cur": "review",
    "end": 1900, "t0": 1500, "t1": 1900, "stop": 0,
    "stages": {"implement": st("done", 1600, ag=[{"lab": "SECRET-AGENT"}]), "review": st("done", 1890)},
    "past": [
        {"rid": 1200, "t0": 1200, "t1": 1300, "end": 1300, "cur": "verify", "lab": "SECRET-LAB",
         "stages": {"implement": st("done", 1250, cm=[1260]), "verify": st("fail", 1300)}},
        {"rid": 1000, "t0": 1000, "t1": 1100, "end": 1100, "cur": "implement", "lab": "",
         "stages": {"implement": st("run", 1100)}},
    ]}]}]


class VisitCollect(unittest.TestCase):
    def setUp(self):
        if not shutil.which("node"):
            self.skipTest("node not installed")

    def test_r1_verdicts_pass_fail_unknown_and_dedup(self):
        twice = SESS + SESS   # the same session reaching the client twice counts once
        d = run("const d = visitCollect(" + json.dumps(twice) + ", null, 900, 2000, visitDefs);" + out("d"))
        self.assertEqual((len(d["runs"]), d["pass"], d["fail"], d["unk"]), (3, 1, 1, 1))
        self.assertEqual([r["vd"] for r in d["runs"]], ["pass", "fail", "unknown"])
        self.assertTrue(d["changed"])

    def test_r1_stopped_or_open_run_is_unknown_never_pass(self):
        d = run("const L = ['x', 'y'], a = visitVerdict({y: {o: 'done'}}, 50, 40, L, 'y'), b = visitVerdict({x: {o: 'done'}, y: {o: 'run'}}, 50, 0, L, 'y'),"
                " c = visitVerdict({y: {o: 'skip'}}, 50, 0, L, 'y'), e = visitVerdict({y: {o: 'done'}}, 0, 0, L, 'y');" + out("[a, b, c, e]"))
        self.assertEqual(d, ["unknown", "unknown", "pass", "unknown"])

    def test_r1_stopped_past_run_unknown_last_stage_pass_no_defs_unknown(self):
        # a past run stopped at stage 1 of 2: no `stop` key and its cur stage closed as done
        d = run("const L = ['implement', 'review'], S = {implement: {o: 'done', t1: 10}},"
                " a = visitVerdict(S, 50, 0, L, 'implement'), b = visitVerdict({implement: {o: 'done'}, review: {o: 'done'}}, 50, 0, L, 'review'),"
                " c = visitVerdict({implement: {o: 'done'}, review: {o: 'done'}}, 50, 0, null, 'review');"
                " const s = [{sid: 's1', cwd: '/w/shop', plrun: [{name: 'change', proj: '/w/shop', rid: 1500, t0: 1500, t1: 1600, end: 0, cur: 'implement',"
                " stages: {implement: {o: 'run', t1: 1600}}, past: [{rid: 1000, t0: 1000, t1: 1100, end: 1100, cur: 'implement',"
                " stages: {implement: {o: 'done', t1: 1050, cm: [1060]}}}]}]}];"
                " const d = visitCollect(s, null, 900, 2000, visitDefs);" + out("[a, b, c, d.runs.map(r => r.vd), d.cms.length]"))
        self.assertEqual(d, ["unknown", "pass", "unknown", ["unknown"], 0])

    def test_r1_past_run_pass_only_when_stop_is_known(self):
        L = "['implement', 'review']"
        d = run("const L = " + L + ", S = {implement: {o: 'done'}, review: {o: 'done'}},"
                " a = visitVerdict(S, 50, null, L, 'review', true), b = visitVerdict({implement: {o: 'done'}, review: {o: 'fail'}}, 50, null, L, 'review', true),"
                " c = visitVerdict(S, 50, 0, L, 'review', false), e = visitVerdict(S, 50, 0, L, 'review', true), f = visitVerdict(S, 50, 40, L, 'review', true);" + out("[a, b, c, e, f]"))
        self.assertEqual(d, ["unknown", "fail", "pass", "pass", "unknown"])

    def test_r1_past_run_with_stop_key_counts_pass_and_its_commits(self):
        # stop 0 = the hook kept it; end 0 + t1 = idle-replaced, dated by t1 but never proven finished
        d = run("const s = [{sid: 's1', cwd: '/w/shop', plrun: [{name: 'change', proj: '/w/shop', rid: 1500, t0: 1500, t1: 1600, end: 0, cur: 'implement',"
                " stages: {implement: {o: 'run', t1: 1600}}, past: ["
                " {rid: 1000, t0: 1000, t1: 1100, end: 1100, stop: 0, cur: 'review', stages: {implement: {o: 'done', t1: 1050, cm: [1060]}, review: {o: 'done', t1: 1100}}},"
                " {rid: 1200, t0: 1200, t1: 1300, end: 0, stop: 0, cur: 'review', stages: {review: {o: 'done', t1: 1300}}}]}]}];"
                " PLS.data['/w/shop'] = {ok: true, pipelines: [{name: 'change', stages: [{title: 'implement'}, {title: 'review'}]}]};"
                " const d = visitCollect(s, null, 900, 2000, visitDefs);" + out("[d.runs.map(r => [r.rid, r.vd]), d.cms.length]"))
        self.assertEqual(d, [[[1200, "unknown"], [1000, "pass"]], 1])

    def test_r1_borrowed_definition_counts(self):
        d = run("PLS.data['/w/shop'] = {ok: true, pipelines: [], borrowed: [{name: 'change', from: '/w/o', stages: [{title: 'implement'}, {title: 'review'}]}]};"
                + out("visitDefs('/w/shop', 'change')"))
        self.assertEqual(d, ["implement", "review"])

    def test_r1_cap_measured_from_now_not_window_end(self):
        d = run("const a = visitCollect([], null, 900, 1000, visitDefs, 900 + VISIT_KEEP_S + 1).cap,"
                " b = visitCollect([], null, 900, 1000, visitDefs, 1000).cap;" + out("[a, b]"))
        self.assertEqual(d, [True, False])

    def test_r1_commit_in_failed_run_or_before_done_not_counted(self):
        s = json.loads(json.dumps(SESS))
        r = s[0]["plrun"][0]
        r["stages"]["implement"]["cm"] = [1590, 1610]   # 1590 is before any stage was done
        r["stages"]["review"]["cm"] = [1610]            # same stamp in two stages = one commit
        d = run("const d = visitCollect(" + json.dumps(s) + ", null, 900, 2000, visitDefs);" + out("d.cms.map(c => c.t)"))
        self.assertEqual(d, [1610])   # past failed run's 1260 is not «after a pass»

    def test_r1_ended_from_attention_at_minus_age_and_missing_age_skipped(self):
        s = [{"sid": "s1", "cwd": "/w/a", "state": "done", "ageSec": 100}, {"sid": "s2", "cwd": "/w/b", "state": "gone"},
             {"sid": "s3", "cwd": "/w/c", "state": "done", "ageSec": "7"}, {"sid": "s4", "cwd": "/w/d", "state": "done", "ageSec": 900},
             {"sid": "s5", "cwd": "/w/e", "state": "run", "ageSec": 1}]
        d = run("const d = visitCollect(" + json.dumps(s) + ", {at: 2000, resp: []}, 1500, 2100);" + out("d"))
        self.assertEqual([e["sid"] for e in d["ended"]], ["s1"])
        self.assertTrue(d["changed"])

    def test_r1_unknown_attention_is_null_not_zero(self):
        d = run("const d = visitCollect(" + json.dumps(SESS) + ", null, 900, 2000, visitDefs); const h = visitHtml(d);" + out("[d.wait, d.ended, h]"))
        self.assertIsNone(d[0])
        self.assertIsNone(d[1])
        self.assertIn("<b>?</b>", d[2])

    def test_r1_waiting_changes_only_when_started_after_since(self):
        old = [{"r": {"sid": "w1", "cwd": "/w/x"}, "since": 800}]
        new = [{"r": {"sid": "w1", "cwd": "/w/x"}, "since": 950}]
        d = run("const a = visitCollect([], {at: 2000, resp: " + json.dumps(old) + "}, 900, 2000, visitDefs),"
                " b = visitCollect([], {at: 2000, resp: " + json.dumps(new) + "}, 900, 2000, visitDefs);" + out("[a.changed, a.wait.length, b.changed]"))
        self.assertEqual(d, [False, 1, True])


class VisitHtml(unittest.TestCase):
    def setUp(self):
        if not shutil.which("node"):
            self.skipTest("node not installed")

    def test_r2_items_are_metadata_only(self):
        d = run("VISIT.data = visitCollect(" + json.dumps(SESS) + ", {at: 2000, resp: []}, 900, 2000, visitDefs);"
                " const strip = visitHtml(VISIT.data); visitOpen('runs', {left: 10, bottom: 20});"
                + out("{strip, pop: BODY.length ? BODY[0].innerHTML : ''}"))
        pop = d["pop"]
        for want in ("shop", "abcdef12", "change", "review", "gate passed", "gate failed", "verdict unknown"):
            self.assertIn(want, pop)
        self.assertNotIn("abcdef1234567890", pop)
        for bad in ("SECRET-LAB", "SECRET-AGENT"):
            self.assertNotIn(bad, pop)
            self.assertNotIn(bad, d["strip"])

    def test_r2_run_click_opens_watch_and_pins_the_run(self):
        d = run("VISIT.data = visitCollect(" + json.dumps(SESS) + ", null, 900, 2000, visitDefs); mainView = 'time';"
                " const L = visitList('runs'); visitGo(L[1]); const past = PLS.runSel; visitGo(L[0]);"
                + out("{pick: PICK, past, cur: PLS.runSel, mv: mainView}"))
        self.assertEqual(d["mv"], "pipe")
        self.assertEqual(d["pick"][0], ["/w/shop", "change", "abcdef1234567890"])
        self.assertEqual(d["past"], {"sid": "abcdef1234567890", "name": "change", "rid": 1200, "cur": 1500, "pin": True})
        self.assertEqual(d["cur"], {"sid": "abcdef1234567890", "name": "change", "rid": 1500, "cur": 1500, "pin": True})   # head run pinned too (48b plPinRun)

    def test_r2_single_waiting_item_jumps_to_attention_row(self):
        resp = [{"r": {"sid": "w1", "cwd": "/w/x"}, "since": 950}]
        d = run("VISIT.data = visitCollect([], {at: 2000, resp: " + json.dumps(resp) + "}, 900, 2000, visitDefs);"
                " visitOpen('wait', {left: 0, bottom: 0});" + out("{att: ATTGO, pop: BODY.length}"))
        self.assertEqual(d, {"att": ["w1"], "pop": 0})

    def test_caps_show_n_plus(self):
        s = json.loads(json.dumps(SESS))
        s[0]["plrun"][0]["past"] = [{"rid": 1000 + i * 10, "t0": 1000 + i * 10, "t1": 1005 + i * 10, "end": 1005 + i * 10,
                                     "stages": {"a": st("done", 1005 + i * 10)}} for i in range(5)]
        d = run("const a = visitHtml(visitCollect(" + json.dumps(s) + ", null, 900, 2000, visitDefs)),"
                " b = visitHtml(visitCollect(" + json.dumps(SESS) + ", null, 900, 2000, visitDefs)),"
                " c = visitCollect(" + json.dumps(SESS) + ", null, 1000 - VISIT_KEEP_S - 1, 1000).cap;" + out("[a, b, c]"))
        self.assertIn("<b>6+</b>", d[0])
        self.assertNotIn("+</b>", d[1])
        self.assertTrue(d[2])

    def test_keep_constants_match_server(self):
        pr = sidereus("pl_runs")
        d = run(out("[VISIT_KEEP_S, VISIT_PAST_MAX, VISIT_RUNS_MAX]"))
        self.assertEqual(d, [pr.PLR_KEEP_S, pr.PLR_PAST_MAX, pr.PLR_MODEL_MAX])


def tick_js(seen, sess, extra=""):
    return ("LSM['sidereus.visit'] = JSON.stringify({seen: " + str(seen) + ", open: null}); SESS = " + json.dumps(sess) + ";"
            + extra + " visitTick({attention: {at: NOW, rows: []}});")


class VisitTick(unittest.TestCase):
    def setUp(self):
        if not shutil.which("node"):
            self.skipTest("node not installed")

    def test_r1_gap_with_change_shows_and_stores_window(self):
        d = run("NOW = 2000;" + tick_js(1000, SESS) + out("{h: VISIT.html, rec: JSON.parse(LSM['sidereus.visit']), fit: FIT}"))
        self.assertIn("Since your last visit", d["h"])
        self.assertEqual(d["rec"], {"seen": 2000, "open": {"since": 1000, "at": 2000}})
        self.assertEqual(d["fit"], 1)

    def test_r3_short_gap_or_no_change_or_blocked_storage_shows_nothing(self):
        d = run("NOW = 2000;" + tick_js(1500, SESS) + " const a = VISIT.html;"
                " VISIT = {ready: false, away: false, w: 0, html: '', data: null, pop: null};" + tick_js(100, [])
                + " const b = VISIT.html, rb = JSON.parse(LSM['sidereus.visit']);"
                " VISIT = {ready: false, away: false, w: 0, html: '', data: null, pop: null}; LSBAD = true; visitTick({attention: null});"
                " visitAway(); visitDismiss();" + out("[a, b, rb, VISIT.html]"))
        self.assertEqual(d[0], "")
        self.assertEqual(d[1], "")
        self.assertEqual(d[2], {"seen": 2000, "open": None})
        self.assertEqual(d[3], "")

    def test_r3_first_visit_only_seeds(self):
        d = run("NOW = 2000; SESS = " + json.dumps(SESS) + "; visitTick({attention: null});"
                + out("{h: VISIT.html, rec: JSON.parse(LSM['sidereus.visit'])}"))
        self.assertEqual(d, {"h": "", "rec": {"seen": 2000, "open": None}})

    def test_r3_hidden_tab_neither_checks_nor_writes(self):
        d = run("NOW = 2000; document.hidden = true;" + tick_js(1000, SESS) + out("[VISIT.html, JSON.parse(LSM['sidereus.visit']).seen]"))
        self.assertEqual(d, ["", 1000])

    def test_r4_reload_before_dismiss_shows_again_dismiss_then_reload_does_not(self):
        fresh = " VISIT = {ready: false, away: false, w: 0, html: '', data: null, pop: null};"
        d = run("NOW = 2000;" + tick_js(1000, SESS) + fresh + " NOW = 2010; visitTick({attention: {at: NOW, rows: []}});"
                " const again = VISIT.html; visitDismiss(); const gone = VISIT.html, rec = JSON.parse(LSM['sidereus.visit']);"
                + fresh + " NOW = 2020; visitTick({attention: {at: NOW, rows: []}});"
                + out("{again, gone, rec, after: VISIT.html}"))
        self.assertIn("Since your last visit", d["again"])
        self.assertEqual(d["gone"], "")
        self.assertEqual(d["rec"], {"seen": 2010, "open": None})
        self.assertEqual(d["after"], "")

    def test_r5_demo_stamp_opens_with_empty_storage_and_dismiss_sticks(self):
        fresh = " VISIT = {ready: false, away: false, w: 0, html: '', data: null, pop: null};"
        st_ = "{visitDemo: 900, attention: {at: 2000, rows: []}}"   # demo clock (attention.at), not Date.now()
        d = run("NOW = 5000; SESS = " + json.dumps(SESS) + "; visitTick(" + st_ + ");"
                " const shown = VISIT.html, rec = JSON.parse(LSM['sidereus.visit']); visitDismiss();" + fresh
                + " NOW = 5010; visitTick(" + st_ + ");" + out("{shown, rec, after: VISIT.html, d: VISIT.data}"))
        self.assertIn("Since your last visit", d["shown"])
        self.assertIn("<b>3</b>", d["shown"])
        self.assertEqual(d["rec"]["open"], {"since": 900, "at": 2000})
        self.assertEqual(d["after"], "")
        self.assertIsNone(d["d"])

    def test_r1_other_project_run_passes_once_defs_fetched_once_per_proj(self):
        other = [{"sid": "o1", "cwd": "/w/other", "state": "run", "ageSec": 5, "plrun": [{
            "name": "rel", "proj": "/w/other", "rid": 1500, "t0": 1500, "t1": 1900, "end": 1900, "stop": 0, "cur": "b",
            "stages": {"a": st("done", 1600), "b": st("done", 1890)}, "past": []}]}]
        body = ("var GETS = []; var getJSON = async u => { GETS.push(u); return {ok: true, pipelines: [{name: 'rel', stages: [{title: 'a'}, {title: 'b'}]}]}; };"
                " (async () => { NOW = 2000;" + tick_js(1000, other) + " const first = VISIT.data.pass;"
                " await new Promise(r => setTimeout(r, 0)); NOW = 2003; visitTick({attention: {at: NOW, rows: []}});"
                " await new Promise(r => setTimeout(r, 0)); NOW = 2006; visitTick({attention: {at: NOW, rows: []}});"
                " process.stdout.write(JSON.stringify({first, pass: VISIT.data.pass, gets: GETS, sel: Object.keys(PLS.data)})); })();")
        d = run(body)
        self.assertEqual(d["first"], 0)
        self.assertEqual(d["pass"], 1)
        self.assertEqual(d["gets"], ["/api/pipelines?proj=%2Fw%2Fother"])
        self.assertEqual(d["sel"], ["/w/shop"])   # PLS.data untouched

    def test_r3_window_held_only_by_waiting_row_is_cleared_when_it_goes(self):
        RESP = "[{r: {sid: 'w1', cwd: '/w/x'}, since: 1900}]"
        d = run("NOW = 2000; RESP = " + RESP + ";" + tick_js(1000, []) + " const shown = VISIT.html;"
                " NOW = 2005; RESP = []; visitTick({attention: {at: NOW, rows: []}});"
                + out("{shown, h: VISIT.html, rec: JSON.parse(LSM['sidereus.visit'])}"))
        self.assertIn("Since your last visit", d["shown"])
        self.assertEqual(d["h"], "")
        self.assertIsNone(d["rec"]["open"])

    def test_r3_missing_attention_keeps_open_window(self):
        RESP = "[{r: {sid: 'w1', cwd: '/w/x'}, since: 1900}]"
        d = run("NOW = 2000; RESP = " + RESP + ";" + tick_js(1000, []) + " NOW = 2005; visitTick({});"
                + out("JSON.parse(LSM['sidereus.visit']).open"))
        self.assertEqual(d, {"since": 1000, "at": 2000})

    def test_r5_new_demo_stamp_reopens_after_dismiss(self):
        d = run("NOW = 5000; SESS = " + json.dumps(SESS) + "; visitTick({visitDemo: 900, attention: {at: 2000, rows: []}}); visitDismiss();"
                " const rec = JSON.parse(LSM['sidereus.visit']); NOW = 5010; visitTick({visitDemo: 950, attention: {at: 2000, rows: []}});"
                + out("{rec, h: VISIT.html, open: JSON.parse(LSM['sidereus.visit']).open}"))
        self.assertEqual(d["rec"]["vd"], 900)
        self.assertIn("Since your last visit", d["h"])
        self.assertEqual(d["open"], {"since": 950, "at": 2000})

    def test_away_before_first_tick_keeps_seen(self):
        d = run("LSM['sidereus.visit'] = JSON.stringify({seen: 1000, open: null}); NOW = 5000; visitAway();"
                + out("JSON.parse(LSM['sidereus.visit']).seen"))
        self.assertEqual(d, 1000)


if __name__ == "__main__":
    unittest.main()
