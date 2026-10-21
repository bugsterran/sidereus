"""First-visit tour (98b-tour.js): plan resolver, auto-open rule, plugin lines, done flag on finish/skip, English coverage."""
import glob
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_switch
from tests._load import sidereus, js_fn
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(ROOT, "web", "js", "98b-tour.js"), encoding="utf-8").read()
STEPS = re.search(r"^const TOUR_STEPS = \[.*?^\];", SRC, re.S | re.M).group(0)
KEY = re.search(r"^const TOUR_KEY = .*$", SRC, re.M).group(0)

STUB = "let LANG = 'ko';\n" + i18n_switch(("T", "KE")) + r"""
const esc = s => String(s).replace(/[&<>"']/g, c => '&#' + c.charCodeAt(0) + ';');
const softErr = () => {};
const R = {};
"""


def run(body):
    fns = "".join(js_fn(n) + "\n" for n in ("tourPlan", "tourShouldAuto", "tourPluginLines", "tourStepper", "tourBody", "tourEnd", "tourClick", "tourPlEdit", "plNowShown"))
    code = STUB + STEPS + "\n" + KEY + "\n" + fns + body + "\nprocess.stdout.write(JSON.stringify(R));"
    r = subprocess.run(node_e(code), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Tour(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
const all = () => true, none = () => false, noStrip = s => s !== '#feed .plnl';
R.full = tourPlan({}, all, 3);
R.off = tourPlan({pipeline: false}, all, 3).map(p => p.id);
R.edit = tourPlan({}, all, 3, true).map(p => p.id);
R.editDemo = tourPlan({}, noStrip, 0, true).filter(p => p.demo).map(p => p.id);
var PLS = {wf: ''}, PLAG = '', plCur = () => null, plWatchFor = () => false;
R.firstRun = tourPlan({}, noStrip, 0, tourPlEdit()).map(p => p.id);
plCur = () => ({ok: true}); R.editLive = tourPlEdit();
R.demoAt = tourPlan({}, all, 0).filter(p => p.demo).map(p => p.id);
R.demoOffAt = tourPlan({pipeline: false}, all, 0).filter(p => p.demo).map(p => p.id);
R.demo = tourPlan({}, all, 0).find(p => p.demo);
R.demoBody = tourBody(R.demo, '');
R.demoOffBody = tourBody(tourPlan({pipeline: false}, all, 0).find(p => p.demo), '');
R.nostrip = tourPlan({}, noStrip, 2).find(p => p.id === 'pl-live');
R.nostripBody = tourBody(R.nostrip, '').h;
R.liveSpot = tourBody({id: 'pl-live', mode: 'spot'}, '');
R.missing = tourPlan({}, none, 2).map(p => p.mode);
R.auto = {first: tourShouldAuto(false, false, ''), done: tourShouldAuto(true, false, ''), wd: tourShouldAuto(false, true, ''),
          q0: tourShouldAuto(false, false, '?tour=0'), q1: tourShouldAuto(true, true, '?tour=1')};
R.withDir = tourPluginLines('/opt/sidereus'); R.noDir = tourPluginLines('');
R.doneBody = tourBody({id: 'done', mode: 'centre'}, '/opt/sidereus').cmds;
R.doneH = tourBody({id: 'done', mode: 'centre'}, '').h;
R.guideH = R.full.filter(p => p.id !== 'done').map(p => tourBody(p, '').h).join('') + R.demoBody.h;
LANG = 'en'; R.noDirEn = tourPluginLines(''); LANG = 'ko';
// finish / skip: flag written, tab before the tour restored
const writes = [], tabs = [];
var UIS = {setItem: (k, v) => writes.push([k, v])};
var document = {getElementById: () => root};
let root, tourI, tourTimer = 0, tourFrom, tourBack = null, mainView, tourList = [{id: 'a'}, {id: 'b'}], tourCmds = [];
const setMainView = v => { tabs.push(v); mainView = v; };
const btn = a => ({target: {closest: s => s === '[data-tour]' ? {dataset: {tour: a}} : null}});
root = {hidden: false}; tourI = 0; tourFrom = 'time'; mainView = 'pipe'; tourClick(btn('skip'));
R.skip = {writes: writes.slice(), tabs: tabs.slice(), hidden: root.hidden};
root = {hidden: false}; tourI = 1; tourFrom = 'time'; mainView = 'struct'; tourClick(btn('next'));
R.finish = {writes: writes.slice(), tabs: tabs.slice(), hidden: root.hidden};
""")

    def test_full_plan_order_and_spot(self):
        # R4: Pipelines lead the tour, Timeline (evidence view) comes after Structure.
        self.assertEqual([p["id"] for p in self.R["full"]], ["pl-what", "pl-live", "pl-start", "arch", "time", "done"])
        self.assertEqual([p["mode"] for p in self.R["full"]], ["centre", "spot", "spot", "spot", "spot", "centre"])

    def test_feature_off_skips_pipeline_steps(self):
        self.assertEqual(self.R["off"], ["arch", "time", "done"])

    def test_edit_mode_drops_pl_live(self):
        # Edit has no «Working now» list: pl-live drops, pl-start stays, the demo hint moves to 'time'.
        self.assertEqual(self.R["edit"], ["pl-what", "pl-start", "arch", "time", "done"])
        self.assertEqual(self.R["editDemo"], ["time"])
        self.assertTrue(self.R["editLive"])

    def test_first_run_without_pipeline_keeps_pl_live(self):
        # No pipeline yet: the list is on screen, so pl-live stays (with the demo hint).
        self.assertIn("pl-live", self.R["firstRun"])

    def test_tour_never_switches_pipeline_mode(self):
        self.assertNotIn("plModeSet", SRC)

    def test_no_sessions_demo_variant(self):
        # R4: the demo hint sits on pl-live; on 'time' only when pl-live dropped out (pipelines off).
        self.assertEqual(self.R["demoAt"], ["pl-live"])
        self.assertEqual(self.R["demoOffAt"], ["time"])
        self.assertEqual(self.R["demo"]["mode"], "centre")
        for b in (self.R["demoBody"], self.R["demoOffBody"]):
            self.assertEqual(b["cmds"], ["python3 -m sidereus start --demo --open"])

    def test_no_strip_centres_pl_live_with_stepper(self):
        self.assertEqual(self.R["nostrip"]["mode"], "centre")
        self.assertIn("tourms", self.R["nostripBody"])

    def test_pl_live_describes_working_now_list(self):
        # pl-live spotlights the always-rendered «Working now» list (.plnl, even collapsed); no dead «no pipeline running» line.
        self.assertEqual(self.R["liveSpot"]["t"], "Working now")
        self.assertIn("지금 작업 중", self.R["liveSpot"]["h"])
        self.assertIn("파이프라인 실행이 열리고", self.R["liveSpot"]["h"])
        self.assertNotIn("tourms", self.R["liveSpot"]["h"])
        self.assertNotIn("tourdim", self.R["nostripBody"])

    def test_missing_targets_all_centred(self):
        self.assertEqual(set(self.R["missing"]), {"centre"})

    def test_should_auto(self):
        self.assertEqual(self.R["auto"], {"first": True, "done": False, "wd": False, "q0": False, "q1": True})

    def test_plugin_lines(self):
        self.assertEqual(self.R["withDir"], ["/plugin marketplace add /opt/sidereus", "/plugin install sidereus@sidereus"])
        self.assertEqual(self.R["noDir"][0], "/plugin marketplace add bugsterran/sidereus")
        self.assertEqual(self.R["noDirEn"][0], "/plugin marketplace add bugsterran/sidereus")
        self.assertEqual(self.R["doneBody"], self.R["withDir"])

    def test_guide_text_platform_neutral(self):
        # Only the plugin step may name Claude Code (its commands are Claude-Code-only).
        self.assertNotIn("Claude Code", self.R["guideH"])
        self.assertIn("AI 코딩 에이전트", self.R["guideH"])
        self.assertIn("Claude Code 를 쓴다면", self.R["doneH"])

    def test_skip_and_finish_write_flag_and_restore_tab(self):
        for k in ("skip", "finish"):
            self.assertTrue(self.R[k]["hidden"])
        self.assertEqual(self.R["skip"]["writes"], [["sidereus.tourDone", "1"]])
        self.assertEqual(self.R["skip"]["tabs"], ["time"])
        self.assertEqual(self.R["finish"]["writes"], [["sidereus.tourDone", "1"]] * 2)
        self.assertEqual(self.R["finish"]["tabs"], ["time", "time"])

    def test_done_key_passes_ui_prefs_filter(self):
        self.assertTrue(sidereus("ui_prefs").KEY_RE.match("sidereus.tourDone"))


class TourI18n(unittest.TestCase):
    def test_every_english_string_has_korean(self):
        # English is the source: every tour text (T/P literal, step title, term meaning) needs an I18N.ko key.
        dict_src = "".join(open(p, encoding="utf-8").read() for p in glob.glob(os.path.join(ROOT, "web", "js", "0[56]*i18n*.js")))
        keys = set(re.findall(r"\b(?:T|P)\('([^']*[A-Za-z][^']*)'\)", SRC))
        keys |= set(re.findall(r"\bt: '([^']*[A-Za-z][^']*)'", SRC))
        keys |= set(re.findall(r"T\(last \? '([^']*)' : '([^']*)'\)", SRC) and sum(re.findall(r"T\(last \? '([^']*)' : '([^']*)'\)", SRC), ()))
        keys |= set(re.findall(r"\[T\('[^']*'\), '([^']*)'\]", SRC))   # term meanings
        self.assertGreater(len(keys), 15)
        missing = sorted(k for k in keys if "'%s':" % k not in dict_src)   # I18N.ko key
        self.assertEqual(missing, [])

    def test_neutral_strings_have_english(self):
        dict_src = open(os.path.join(ROOT, "web", "js", "06-i18n-z.js"), encoding="utf-8").read()
        self.assertIn("'AI coding-agent sessions on this computer gather here automatically': '이 컴퓨터의 AI 코딩 에이전트 세션이 자동으로 모입니다'", dict_src)
        self.assertIn("'If you use Claude Code, these two lines install the Sidereus plugin", dict_src)
        self.assertNotIn("이 컴퓨터의 Claude Code 세션", dict_src)


def _ko_dict():
    # I18N.ko entries in file order (a later file wins); 06-i18n-w.js holds PLG name tables, parsed separately.
    d = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "web", "js", "06-i18n-*.js"))):
        if p.endswith("06-i18n-w.js"):
            continue
        with open(p, encoding="utf-8") as f:
            src = f.read()
        for k, v in re.findall(r"'((?:[^'\\]|\\.)*)'\s*:\s*'((?:[^'\\]|\\.)*)'", src):
            d[k] = v
    return d


def _plg_en():
    # PLG_NAMES / PLG_TPL_NAMES en tables: English display -> saved Korean title.
    with open(os.path.join(ROOT, "web", "js", "06-i18n-w.js"), encoding="utf-8") as f:
        src = f.read()
    return {v: k for k, v in re.findall(r"'([^']*[가-힣][^']*)'\s*:\s*'([^']*)'", src)}


def _labels(s, en):
    # «quoted» labels plus "A › B" breadcrumb parts, in reading order.
    crumb = r"([A-Z][\w-]*) › ([A-Z][\w-]*)" if en else r"(\S+) › (\S+)"
    out = []
    for m in re.finditer(r"«([^»]+)»|" + crumb, s):
        out.extend(x for x in m.groups() if x)
    return out


class TourDrift(unittest.TestCase):
    """A UI change that breaks the tour fails here: step targets must still be built by the page and
    every label the tour text names must still be a live UI string with the same Korean."""

    @classmethod
    def setUpClass(cls):
        # Assembled PAGE minus the tour's own source and the dictionaries: what is left is markup + feature code.
        cls.code = sidereus("page").PAGE.replace(SRC, "")
        for p in glob.glob(os.path.join(ROOT, "web", "js", "06-i18n-*.js")):
            with open(p, encoding="utf-8") as f:
                cls.code = cls.code.replace(f.read(), "")
        cls.ko = _ko_dict()
        cls.plg = _plg_en()

    def test_step_selectors_are_built_by_the_page(self):
        sels = re.findall(r"\b(?:sel|also): '([^']+)'", STEPS)
        self.assertGreaterEqual(len(sels), 4)
        for sel in sels:
            for kind, name in re.findall(r"([#.]|\[)([\w-]+)", sel):
                if kind == "#":
                    pat = r"\bid=[\"']?%s(?![\w-])" % re.escape(name)
                else:   # emitted as a class/attribute token, not a CSS or querySelector reference
                    pat = r"(?<![\w.\[-])%s(?![\w-])" % re.escape(name)
                self.assertRegex(self.code, pat, "tour step %r: %s%s is no longer built by the page" % (sel, kind, name))

    def test_quoted_labels_are_live_ui_strings(self):
        sents = set(re.findall(r"\bP\('([^']*[«›][^']*)'\)", SRC))
        self.assertGreaterEqual(len(sents), 2)
        for s in sents:
            en, ko = _labels(s, True), _labels(self.ko.get(s, ""), False)
            self.assertTrue(en)
            self.assertEqual(len(en), len(ko), "ko text of %r names a different number of labels" % s)
            for e, k in zip(en, ko):
                if e in self.plg:   # pipeline/template display name: Korean = saved title
                    self.assertEqual(k, self.plg[e], s)
                    continue
                self.assertRegex(self.code, r"'%s'" % re.escape(e), "tour label «%s» is not a UI string any more" % e)
                self.assertEqual(self.ko.get(e), k, "tour label «%s»: ko text says «%s»" % (e, k))

    def test_stepper_words_match_screen(self):
        # Mini stepper stage names = PLG_NAMES en values (Korean = saved title); other words = live T() strings.
        st = js_fn("tourStepper")
        stages = re.findall(r"nd\('[^']*', '[^']*', T\('([^']*)'\)\)", st)
        self.assertEqual(len(stages), 3)
        for e in stages:
            self.assertIn(e, self.plg, "stepper stage %r is not a pipeline stage name" % e)
            self.assertEqual(self.ko.get(e), self.plg[e])
        terms = re.findall(r"\[T\('([^']*)'\), '[^']*'\]", SRC) + re.findall(r"tourlpt>[^']*' \+ esc\(T\('([^']*)'\)", st)
        for e in terms:
            if e in ("Stage", "Gate"):
                continue   # generic concept words, not screen labels
            self.assertRegex(self.code, r"'%s'" % re.escape(e), "tour term %r is not a UI string any more" % e)


if __name__ == "__main__":
    unittest.main()
