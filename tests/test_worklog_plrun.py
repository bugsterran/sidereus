"""Work-popup pipeline strip (web/js/35e-worklog-plrun.js): run lookup by tid/aid/tag, stage marks, ↺ counts,
this agent's highlight, escaping, and the 10 s pljump freshness. One node run; fixed clock passed in, no live data."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import jconst
from tests._node import node_e

NOW = 1_700_000_000_000
EVIL = '<img src=x onerror=alert(1)>"'
SESS = [
    {"cwd": "/w/a", "plrun": [
        {"name": "ch", "proj": "/w/a", "sid": "s1", "t0": 100, "stages": {
            "설계": {"o": "done", "n": 1, "from": {}, "ag": [{"aid": "a0123456789", "tid": "toolu_d", "lab": "sidereus-designer: x", "t0": 100}]},
            "구현": {"o": "back", "n": 2, "from": {"검증": 2, "리뷰": 1},
                   "ag": [{"aid": "abcdef0", "tid": "toolu_i1", "lab": EVIL + ": a", "t0": 110},
                          {"aid": "abcdef1", "tid": "toolu_i2", "lab": "impl: b", "t0": 120}]},
            "검증": {"o": "fail", "n": 1, "from": {}, "ag": []},
            EVIL: {"o": "run", "n": 1, "from": {}, "ag": [{"aid": "main", "tid": "", "lab": EVIL, "t0": 130}]}}},
        {"name": "ch", "proj": "/w/a", "sid": "s0", "t0": 50, "end": 60, "stages": {}}]},
    {"cwd": "/w/b", "plrun": [{"name": "ch", "proj": "/w/b", "sid": "s2", "t0": 300, "stages": {"설계": {"o": "skip", "n": 0, "from": {}}}}]},
]


def run(body):
    src = ("var LANG = 'ko'; var SESS = %s; const PLS = {data: {'/w/a': {pipelines: [{name: 'ch', stages: "
           "[{title: '설계'}, {title: '구현'}, {title: '검증'}, {title: '리뷰'}]}]}}};\n"
           "function KE(k, e){ return LANG === 'en' ? e : k; }\nconst T = s => s, plgShow = t => t, ago = s => Math.floor(s / 60) + '분', AGO = t => t + ' 전';\nfunction CLK(d){ return 'T' + d.getTime(); }\n"
           "var WPCH = null;\nconst WPPL = {}, WPHITS = {};\nfunction wpFetchOrder(){}\n"
           "const wtabs = [{key: 'A', cwd: '/w/a', tid: 'toolu_i2|s1'}, {key: 'B', cwd: '/w/a', tid: 'a0123456789'},"
           " {key: 'S', cwd: '/w/a', tid: 'sess:/w/a'}];\nconst wtPanes = ['A', 'B'], wtData = {};\n" % json.dumps(SESS)
           + "\n".join([jconst("esc"), jconst("TLPL_ICON"), jconst("WP_TAG")]
                       + [js_fn(f) for f in ("plStepper", "plPrLive", "wpLive", "wpRunOf", "wpOrder", "wpLabel", "plWhy", "wpAgId", "wpAgs", "wpStripHtml", "wpJumpRecv",
                                                      "tidSid", "wpSessRuns", "wpHitOf", "wpView", "wpPlrunHook", "wpRefresh", "wpJumpKnown", "tlPlEnd", "tlPlSt")])
           + "\nDate.now = () => %d;\nconst R = {};\n" % NOW + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class WorklogPlrun(unittest.TestCase):
    def test_ended_run_label(self):
        # NOW = 1_700_000_000 s; ended 600 s earlier
        R = run(r"""
const st = o => ({o: o, n: 1, from: {}, ag: []});
const done = {name: 'ch', proj: '/w/a', t0: 1, end: 1699999400, stages: {'설계': st('done'), '구현': st('done'), '검증': st('skip'), '리뷰': st('run')}};
const cut = {name: 'ch', proj: '/w/a', t0: 1, end: 1699999400, stages: {'설계': st('done'), '구현': st('run')}};
const live = {name: 'ch', proj: '/w/a', t0: 1, stages: {'설계': st('done'), '구현': st('run')}};
R.done = wpStripHtml(done, '', ''); R.cut = wpStripHtml(cut, '', ''); R.live = wpStripHtml(live, '', '');
""")
        self.assertIn('<i class="tlpc tlpe tlpe-ok"><strong><i aria-hidden=true>✓</i> Done</strong> · 리뷰 · 10분 전</i>', R["done"])
        self.assertIn('tlpe-stop"><strong><i aria-hidden=true>⏸</i> Aborted</strong> · 구현 · 10분 전', R["cut"])   # 검증/리뷰 never reached
        self.assertNotIn("tlpe", R["live"])

    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
const k = h => h ? {sid: h.run.sid, title: h.title, cwd: h.cwd} : null;
R.tid = k(wpRunOf('/w/a', 'toolu_i2|s1', ''));
R.aid = k(wpRunOf('/w/a', 'a0123456789', ''));
R.tag = k(wpRunOf('/w/a', 'toolu_zz', 'impl [pl:ch/검증] go'));
R.none = wpRunOf('/w/a', 'toolu_zz', 'no tag');
R.strip = wpStripHtml(SESS[0].plrun[0], '구현');
R.evilRun = wpStripHtml(SESS[0].plrun[0], Object.keys(SESS[0].plrun[0].stages)[3]);
R.chooser = wpStripHtml(SESS[0].plrun[0], '설계', '구현');
R.split = {A: wpPlrunHook({ok: true}, 'A'), B: wpPlrunHook({ok: true}, 'B'), S: wpPlrunHook({ok: true}, 'S'), def: wpPlrunHook({ok: true})};
const el = h => ({dataset: {wplk: /data-wplk="([^"]*)"/.exec(h)[1], sig: /data-sig="([^"]*)"/.exec(h)[1]
  .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&')}, innerHTML: 'OLD'});
// scroller stubs: pane A sits at its end, pane B mid-log; the redraw grows both by 50px
const scs = [{scrollTop: 400, clientHeight: 300, scrollHeight: 700}, {scrollTop: 100, clientHeight: 300, scrollHeight: 700}];
var document = {getElementById: () => null};
const els = [el(R.split.A), el(R.split.B)], root = {querySelectorAll: () => els};
els.forEach((x, i) => { let h = x.innerHTML; x.closest = () => scs[i];
  Object.defineProperty(x, 'innerHTML', {get: () => h, set: v => { h = v; scs[i].scrollHeight += 50; }}); });
R.same = wpRefresh(root);
SESS[0].plrun[0].stages['검증'].o = 'done';
R.changed = wpRefresh(root); R.html = els.map(x => x.innerHTML); R.tops = scs.map(x => x.scrollTop);
R.again = wpRefresh(root);
R.fresh = wpJumpRecv(JSON.stringify({proj: '/w/a', name: 'ch', at: Date.now() - 9000}), Date.now());
R.stale = wpJumpRecv(JSON.stringify({proj: '/w/a', name: 'ch', at: Date.now() - 10001}), Date.now());
R.future = wpJumpRecv(JSON.stringify({proj: '/w/a', name: 'ch', at: Date.now() + 5000}), Date.now());
R.junk = wpJumpRecv('{', Date.now());
R.known = [wpJumpKnown('/w/a'), wpJumpKnown('/etc'), wpJumpKnown('')];
""")

    def test_run_by_tid_aid_and_tag(self):
        self.assertEqual(self.R["tid"], {"sid": "s1", "title": "구현", "cwd": "/w/a"})
        self.assertEqual(self.R["aid"], {"sid": "s1", "title": "설계", "cwd": "/w/a"})
        self.assertEqual(self.R["tag"], {"sid": "s2", "title": "검증", "cwd": "/w/b"})   # newest run named ch
        self.assertIsNone(self.R["none"])

    def test_marks_order_back_count_and_highlight(self):
        s = self.R["strip"]
        steps = re.findall(r'class="tlpls pl-(\w+)[^"]*"[^>]*><i class=tlpd aria-hidden=true></i><i class=tlpn>([^<]+)', s)
        steps = [(st, nm) for st, nm in steps if nm in ("설계", "구현", "검증", "리뷰")]
        self.assertEqual(steps, [("done", "설계"), ("back", "구현"), ("fail", "검증"), ("wait", "리뷰")])   # file order, absent = wait
        self.assertIn("<em>↺3</em>", s)
        self.assertIn("검증 ×2, 리뷰 ×1", s)
        self.assertIn('class="tlpls pl-back p me"', s)             # shared stepper (74c); progress up to the running stage
        self.assertIn('class="tlpls pl-run cur me na"', self.R["evilRun"])
        self.assertEqual(s.count(" me\""), 1)
        self.assertIn('class="tlpst lg"', s)
        self.assertNotIn("wplc", s)

    def test_chooser_lists_agents_newest_first(self):
        c = self.R["chooser"]
        self.assertLess(c.index('data-wplc="abcdef1"'), c.index('data-wplc="abcdef0"'))
        self.assertIn("impl · T120000", c)

    def test_split_panes_each_own_run(self):
        sp = self.R["split"]
        self.assertIn('data-wplk="A"', sp["A"])
        self.assertIn('class="tlpls pl-back p me"', sp["A"])                # A = 구현 agent
        self.assertIn('class="tlpls pl-done p me"', sp["B"])                # B = 설계 agent
        self.assertIn('data-wplk="S"', sp["S"])                         # session tab: its own open run
        self.assertIn('pl-run cur me na"', sp["S"])
        self.assertEqual(sp["def"], sp["A"])                             # single pane = wtPanes[0]

    def test_refresh_only_on_signature_change(self):
        self.assertEqual(self.R["same"], 0)
        self.assertEqual(self.R["changed"], 2)
        self.assertTrue(all(re.search(r'pl-done[^"]*"[^>]*><i class=tlpd aria-hidden=true></i><i class=tlpn>검증', h) for h in self.R["html"]))
        self.assertEqual(self.R["again"], 0)

    def test_refresh_keeps_end_pinned_only_at_end(self):
        self.assertEqual(self.R["tops"], [750, 100])                    # at end -> follows; mid-log -> untouched

    def test_hostile_title_and_label_escaped(self):
        s = self.R["strip"]
        self.assertNotIn("<img", s)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;&quot;", s)
        self.assertNotIn('data-wplc="main"', self.R["chooser"])
        self.assertNotIn("<img", self.R["chooser"])
        self.assertIn("&lt;img", self.R["chooser"])

    def test_stale_pljump_ignored(self):
        self.assertEqual(self.R["fresh"], {"proj": "/w/a", "name": "ch"})
        self.assertIsNone(self.R["stale"])
        self.assertIsNone(self.R["future"])
        self.assertIsNone(self.R["junk"])

    def test_pljump_unknown_project_ignored(self):
        self.assertEqual(self.R["known"], [True, False, False])


def _run_row(sid, t0, end, cur, o):
    return {"name": "ch", "proj": "", "sid": sid, "t0": t0, "end": end, "cur": cur,
            "stages": {"설계": {"o": "done", "n": 1, "from": {}}, "구현": {"o": o, "n": 1, "from": {}}}}


@unittest.skipUnless(shutil.which("node"), "node not installed")
class WorklogPlrunSession(unittest.TestCase):
    """Session (orchestrator) popup: open run first, newest ended fallback, ≤3 stacked, none without plrun."""
    @classmethod
    def setUpClass(cls):
        rows = [
            {"cwd": "/w/a", "sid": "o1", "plrun": [_run_row("o1", 200, 0, "구현", "run"), _run_row("o1", 300, 310, "", "done")]},
            {"cwd": "/w/a", "sid": "o2", "plrun": [_run_row("o2", 100, 110, "", "done"), _run_row("o2", 150, 160, "", "fail")]},
            {"cwd": "/w/a", "sid": "o3", "plrun": [_run_row("o3", 100, 0, "", "run"), _run_row("o3", 120, 0, "설계", "wait"),
                                                   _run_row("o3", 90, 0, "", "run"), _run_row("o3", 80, 0, "", "run")]},
            {"cwd": "/w/a", "sid": "o4"},
            {"cwd": "/w/a", "sid": "o5", "plrun": [dict(_run_row("o5", 100, 0, "", "x"), name=EVIL,
                                                        stages={EVIL: {"o": "run", "n": 1, "from": {}}})]},
        ]
        cls.R = run("const ROWS = %s; SESS = ROWS;\nconst _r = sid => (%s);\n"
                    % (json.dumps(rows), json.dumps(_run_row("X", 1, 0, "구현", "run")).replace('"X"', 'sid')) + r"""
const k = h => h ? {cwd: h.cwd, runs: h.runs.map(x => [x.run.sid, x.run.t0, x.title])} : null;
R.open = k(wpSessRuns('/w/a', 'sess:/w/a|o1'));
R.ended = k(wpSessRuns('/w/a', 'sess:/w/a|o2'));
R.stack = k(wpSessRuns('/w/a', 'sess:/w/a|o3'));
R.none = wpSessRuns('/w/a', 'sess:/w/a|o4');
R.live = k(wpSessRuns('/w/a', 'sess:/w/a'));
SESS = [{cwd: '/w/c', sid: 'old', ageSec: 900, plrun: [_r('old')]}, {cwd: '/w/c', sid: 'new', ageSec: 5, plrun: [_r('new')]},
        {cwd: '/w/c', sid: 'ext', plat: 'codex', ageSec: 0, plrun: [_r('ext')]}];
R.newest = k(wpSessRuns('/w/c', 'sess:/w/c'));
R.bySid = k(wpSessRuns('/w/c', 'sess:/w/c|old'));
SESS = ROWS;
wtabs.push({key: 'N', cwd: '/w/a', tid: 'sess:/w/a|o4'}, {key: 'T', cwd: '/w/a', tid: 'sess:/w/a|o3'},
           {key: 'E', cwd: '/w/a', tid: 'sess:/w/a|o5'});
R.noneHtml = wpPlrunHook({ok: true}, 'N');
R.stackHtml = wpPlrunHook({ok: true}, 'T');
R.evil = wpPlrunHook({ok: true}, 'E');
""")

    def test_open_run_wins_over_newer_ended(self):
        self.assertEqual(self.R["open"], {"cwd": "/w/a", "runs": [["o1", 200, "구현"]]})
        self.assertEqual(self.R["live"]["runs"][0][0], "o1")             # all ageSec missing: first row of that cwd

    def test_plain_cwd_tab_uses_newest_session(self):
        self.assertEqual(self.R["newest"]["runs"][0][0], "new")         # smallest ageSec, ext rows ignored
        self.assertEqual(self.R["bySid"]["runs"][0][0], "old")

    def test_all_ended_falls_back_to_newest(self):
        self.assertEqual(self.R["ended"]["runs"], [["o2", 150, ""]])    # no cur, no o=run stage: no highlight

    def test_open_runs_stack_at_most_three(self):
        self.assertEqual(self.R["stack"]["runs"], [["o3", 120, "설계"], ["o3", 100, "구현"], ["o3", 90, "구현"]])
        h = self.R["stackHtml"]
        self.assertEqual(h.count('<div class=wpl '), 3)
        self.assertEqual(h.count(' me na"'), 3)                              # each strip highlights its current stage
        self.assertEqual(h.count('class="tlpst lg fin"'), 1)                 # 120: open but no «run» stage = not live, no pulse

    def test_no_plrun_renders_nothing(self):
        self.assertIsNone(self.R["none"])
        self.assertNotIn("tlpls", self.R["noneHtml"])

    def test_session_strip_escaped(self):
        self.assertNotIn("<img", self.R["evil"])
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;&quot;", self.R["evil"])
        self.assertIn('class="tlpls pl-run cur me na"', self.R["evil"])



@unittest.skipUnless(shutil.which("node"), "node not installed")
class WorklogPlrunMulti(unittest.TestCase):
    """Agent present in two runs: both strips, live run first; non-live runs never get the live (pulsing) stepper."""
    @classmethod
    def setUpClass(cls):
        ag = [{"aid": "a0000000001", "tid": "toolu_m", "lab": "impl: m", "t0": 100}]
        rows = [{"cwd": "/w/a", "sid": "m1", "plrun": [
            {"name": "ch", "proj": "", "sid": "m1", "t0": 100, "t1": 500, "end": 500, "stages": {"구현": {"o": "done", "n": 1, "from": {}, "ag": ag}}},
            {"name": "ch", "proj": "", "sid": "m1", "t0": 200, "t1": 300, "stages": {"리뷰": {"o": "run", "n": 1, "from": {}, "ag": ag}}}]}]
        cls.R = run("SESS = %s;\nwtabs.push({key: 'M', cwd: '/w/a', tid: 'toolu_m|m1'});\n" % json.dumps(rows) + r"""
const h = wpRunOf('/w/a', 'toolu_m|m1', '');
R.runs = h.runs.map(x => [x.run.t0, x.title]);
R.html = wpPlrunHook({ok: true}, 'M');
""")

    def test_two_runs_two_strips_live_first(self):
        self.assertEqual(self.R["runs"], [[200, "리뷰"], [100, "구현"]])
        h = self.R["html"]
        self.assertEqual(h.count('<div class=wpl '), 2)
        self.assertEqual(h.count('class="tlpst lg"'), 1)
        self.assertEqual(h.count('class="tlpst lg fin"'), 1)


if __name__ == "__main__":
    unittest.main()
