"""Harness side of the stage card FAIL link (#27, web/js/47b-harness.js hnGo/hnGoFind/hnGoScroll): target card, note, scroll once."""
import json
import subprocess
import unittest

from tests._i18n_js import i18n_switch
from tests._node import node_e
from tests.test_harness_js import _F, _STUB

# rAF queues (run by RUNRAF); querySelector returns one fake element that records scroll/focus calls.
_DOC = """
const RAF = [], SCR = [], FOC = [];
function requestAnimationFrame(f){ RAF.push(f); }
function RUNRAF(){ RAF.splice(0).forEach(f => f()); }
let HAS = '.hngo';
const EL = {classList: {contains: c => c === 'hngo' && HAS === '.hngo'}, scrollIntoView(o){ SCR.push(o); }, focus(o){ FOC.push(o); }};
const LST = {}, BLUR = [];
const document = {addEventListener(t, f){ (LST[t] = LST[t] || []).push(f); }, querySelector(s){ return s.endsWith(HAS) ? EL : null; },
  activeElement: null};
"""


def _js(body):
    with open(_F, encoding="utf-8") as f:
        src = _STUB + i18n_switch() + _DOC + f.read() + "\n" + body
    return json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


def _inc(mode, fts, pts):
    return {"mode": mode, "cp": "fast" if mode == "fast" else "other", "state": "held", "commits": 1,
            "fail": {"ts": fts, "head": "a" * 7, "rc": 1}, "pass": {"ts": pts, "head": "b" * 7}}


def _data(incs, caught=None):
    return {"ok": True, "report": {"counts": {"caught": len(incs) if caught is None else caught}, "incidents": incs,
                                   "checkpoints": {"fast": {"runs": 4, "caught": len(incs), "listed": len(incs)}}}}


def _render(data, key, extra=""):
    return _js("hnGo(%s); const h = hnReport(%s); %s console.log(JSON.stringify({h: h, n: (h.match(/hngo\"/g) || []).length,"
               " note: /hngonote/.test(h), go: HN.go, cp: HN.cp, scr: SCR.length, foc: FOC}))" % (json.dumps(key), json.dumps(data), extra))


class HarnessGo(unittest.TestCase):
    def test_r1_exact_match_highlight(self):
        r = _render(_data([_inc("fast", 1700000100.0, 1700000200.0), _inc("fast", 1700000000.0, 1700000050.0)]), "fast|1700000000")
        self.assertEqual(r["n"], 1)
        self.assertIn('hngo" tabindex=-1', r["h"])
        self.assertFalse(r["note"])
        cards = r["h"].split('class="hnrun hninc')[1:]   # newest first: the matching card is the older, second one
        self.assertEqual([c.startswith(' hngo"') for c in cards], [False, True])

    def test_r1_covering_pair(self):
        # FAIL at 100 was superseded by FAIL at 150; the PASS at 200 pairs with 150
        r = _js("hnGo('fast|100'); const R = hnRep(%s); const g = hnGoFind(R);"
                " console.log(JSON.stringify(g.x ? g.x.pass.ts : g.note))"
                % json.dumps(_data([_inc("fast", 300.0, 400.0), _inc("fast", 150.0, 200.0), _inc("full", 90.0, 120.0)])))
        self.assertEqual(r, 200.0)

    def test_r1_clears_cp_filter(self):
        r = _js("HN.cp = 'full'; hnGo('fast|5'); console.log(JSON.stringify([HN.cp, HN.go.mode, HN.go.ts, HN.go.done]))")
        self.assertEqual(r, ["", "fast", 5, False])

    def test_r2_note_when_unpaired(self):
        r = _render(_data([_inc("fast", 100.0, 200.0)]), "fast|500", "HAS = '.hngonote'; RUNRAF();")
        self.assertEqual(r["n"], 0)
        self.assertTrue(r["note"])
        self.assertIn("다음 PASS", r["h"])
        self.assertLess(r["h"].index("hngonote"), r["h"].index("hninc"))   # first line of the card list
        self.assertEqual((r["scr"], r["foc"]), (1, []))   # note is scrolled to, never focused

    def test_r2_note_without_any_incident(self):
        r = _render({"ok": True, "report": {"counts": {}, "incidents": [], "checkpoints": {}}}, "full|42")
        self.assertTrue(r["note"])

    def test_r2_older_than_listed(self):
        r = _render(_data([_inc("fast", 100.0, 200.0)], caught=25), "fast|10")
        self.assertIn("오래된", r["h"])
        r2 = _render(_data([_inc("fast", 100.0, 200.0)]), "fast|10")   # caught == listed: covered by the listed pair
        self.assertEqual((r2["n"], r2["note"]), (1, False))

    def test_r1_highlight_survives_repaint(self):
        r = _js("hnGo('fast|100'); const D = %s; hnReport(D); RUNRAF(); const h2 = hnReport(D); RUNRAF();"
                " console.log(JSON.stringify({n: (h2.match(/hngo\"/g) || []).length, scr: SCR, foc: FOC, done: HN.go.done}))"
                % json.dumps(_data([_inc("fast", 100.0, 200.0)])))
        self.assertEqual(r["n"], 1)
        self.assertEqual(r["scr"], [{"block": "nearest"}])   # one scroll only, nearest edge
        self.assertEqual(r["foc"], [{"preventScroll": True}])
        self.assertTrue(r["done"])

    def test_go_cleared_by_project_and_platform(self):
        r = _js("hnGo('fast|100'); PLS.proj = '/w/b'; hnReport(%s); const a = HN.go; PLS.proj = '/w/a';"
                " hnGo('fast|100'); hnSetPlat('cx'); console.log(JSON.stringify([a, HN.go]))" % json.dumps(_data([])))
        self.assertEqual(r, [None, None])

    def test_f1_go_clear_repaint_plain(self):
        for key in ("fast|100", "fast|500"):   # card target, then note target
            r = _js("hnGo(%s); const D = %s; const a = hnReport(D); hnGoClear(); const b = hnReport(D);"
                    " console.log(JSON.stringify([/hngo/.test(a), /hngo/.test(b), HN.go]))"
                    % (json.dumps(key), json.dumps(_data([_inc("fast", 100.0, 200.0)]))))
            self.assertEqual(r, [True, False, None])

    def test_f2_click_inside_clears_and_blurs(self):
        r = _js("hnGo('fast|100'); hnReport(%s); RUNRAF();"
                " const card = {classList: {contains: c => c === 'hngo'}, blur(){ BLUR.push(1); }}; document.activeElement = card;"
                " const t = {closest: s => s === '.hnw' ? {} : null}; LST.click.forEach(f => f({target: t}));"
                " console.log(JSON.stringify([HN.go, BLUR.length]))" % json.dumps(_data([_inc("fast", 100.0, 200.0)])))
        self.assertEqual(r, [None, 1])
        r2 = _js("hnGo('fast|100'); const t = {closest: s => null}; LST.click.forEach(f => f({target: t}));"
                 " console.log(JSON.stringify(HN.go.mode))")   # a click outside the view keeps the target
        self.assertEqual(r2, "fast")

    def test_f3_older_cutoff_is_per_mode(self):
        # only a newer pair of another mode is listed: fast has no later pair = not fixed yet (all-mode cut-off said «older»)
        r = _render(_data([_inc("full", 900.0, 1000.0)], caught=25), "fast|300")
        self.assertIn("다음 PASS", r["h"])
        # an older pair of another mode must not lower the fast cut-off: fast|50 is below the oldest listed fast PASS
        r2 = _render(_data([_inc("fast", 100.0, 200.0), _inc("full", 10.0, 20.0)], caught=25), "fast|50")
        self.assertIn("오래된", r2["h"])
        self.assertEqual(r2["n"], 0)

    def test_f5_empty_mode_key(self):
        r = _render(_data([_inc("", 100.0, 200.0)]), "|100")
        self.assertEqual((r["go"]["mode"], r["n"]), ("", 1))

    def test_bad_key_ignored(self):
        bad = ["", "fast", "fast|", "fast|abc", "FAST|1", "a b|1", "x" * 21 + "|1", "fast|1|2", "fast|-1", "fast|0", "<b>|1", None]
        r = _js("HN.cp = 'full'; const out = %s.map(k => { hnGo(k); return HN.go; }); console.log(JSON.stringify([out, HN.cp]))"
                % json.dumps(bad))
        self.assertEqual(r, [[None] * len(bad), "full"])


if __name__ == "__main__":
    unittest.main()
