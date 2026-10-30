"""#27 stage card «gate FAIL» line links to its Harness incident (48f plEvLine link · 48 plGoHarness / data-plv scroll keep)."""
import json
import os
import re
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import ROOT, js_fn
from tests._node import node_e

ESC = "const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\"/g, '&quot;');\n"
PASS = {"ts": 1000, "mode": "fast", "rc": 0, "steps": [{"name": "tests", "rc": 0, "n": 5, "failed": 0}]}
FAIL = {"ts": 900.0, "mode": "fast", "rc": 1, "steps": [{"name": "tests", "rc": 1, "n": 9, "failed": 2}]}


def _run(src):
    return json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


def _ev(calls):
    src = i18n_prelude("'en'", ("T", "TV", "U")) + ESC + js_fn("plEvLine") + "\nconsole.log(JSON.stringify([%s]))" % ",".join(calls)
    return _run(src)


def _call(rows, L, link=None):
    a = "%s, %s, []" % (json.dumps(rows), json.dumps(L))
    return "plEvLine(%s%s)" % (a, "" if link is None else ", " + json.dumps(link))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


class EvLineLink(unittest.TestCase):
    def test_r3_pass_noev_nogate_identical(self):
        cases = [([PASS], {"w0": 950, "w1": 990}), ([], {"w0": 950, "w1": 990}), ([PASS], {"w0": 0, "w1": 0})]
        out = _ev([_call(r, L, link) for r, L in cases for link in (None, True)])
        for i in range(0, len(out), 2):
            self.assertEqual(out[i], out[i + 1])
            self.assertNotIn("data-plevf", out[i + 1])

    def test_r3_fail_same_text_and_class(self):
        plain, linked = _ev([_call([FAIL], {"w0": 850, "w1": 920}), _call([FAIL], {"w0": 850, "w1": 920}, True)])
        body = lambda h: re.search(r">(.*)</div>$", h).group(1)
        cls = lambda h: re.search(r'class="([^"]*)"', h).group(1)
        self.assertEqual(body(plain), body(linked))
        self.assertEqual(cls(plain), cls(linked))
        self.assertEqual(cls(linked), "plev plevng")
        self.assertIn(' data-plevf="fast|900" tabindex=0 role=link aria-label="Open this failure in Harness report"', linked)

    def test_r3_timeline_unlinked(self):
        # 74c timeline and 48k mode panel never pass a link: three-argument calls only
        for rel in ("web/js/74c-timeline-plrun.js", "web/js/48k-pipeline-mode.js"):
            calls = re.findall(r"plEvLine\(plEvRows\([^)]*\), [^,]+, plEvCommits\([^)]*\)(,?)", _read(rel))
            self.assertTrue(calls, rel)
            self.assertEqual(set(calls), {""}, rel)
        self.assertIn("FEATS.harness !== false)", _read("web/js/48d-pipeline-canvas.js"))
        self.assertNotIn("data-plevf", _ev([_call([FAIL], {"w0": 850, "w1": 920}, False)])[0])

    def test_r1_key_format_escaped(self):
        bad = dict(FAIL, mode='"><b>x')
        h = _ev([_call([bad], {"w0": 850, "w1": 920}, True)])[0]
        self.assertIn('data-plevf="&quot;&gt;&lt;b&gt;x|900"', h)
        self.assertNotIn("<b>", h)

    def test_r4_scroll_restored(self):
        handler = re.search(r"document\.addEventListener\('click', e => \{\n  const b = e\.target\.closest && e\.target\.closest\('\.wkrgb\[data-plv\]'\);.*?\n\}\);",
                            _read("web/js/48-pipeline.js"), re.S).group(0)
        src = r"""
let PLVIEW = 'pipe', GO = [], PAINTS = 0, RAF = [];
const FEATS = {}, PLS = { proj: '/p', sel: 'a' }, LS = {};
const fd = { scrollTop: 640 };
const H = {};
const document = { getElementById: id => id === 'feed' ? fd : null, addEventListener: (t, f) => { H[t] = f; }, activeElement: null };
const lsSet = (k, v) => { LS[k] = v; };
const requestAnimationFrame = f => RAF.push(f);
const kbHold = () => {};
let CLR = 0;
function hnGo(k){ GO.push(k); }
function hnGoClear(){ CLR++; }
function plPaint(){ PAINTS++; fd.scrollTop = 0; }   // innerHTML rebuild resets the feed scroll
""" + js_fn("plPipeTopSave") + "\n" + js_fn("plPipeTopRestore") + "\n" + js_fn("plGoHarness") + "\n" + handler + r"""
plGoHarness('fast|900');
const mid = [PLVIEW, LS['sidereus.plview'], GO.slice(), PLS.pipeTop, fd.scrollTop, CLR];
const btn = { dataset: { plv: 'pipe' } };
H.click({ target: { closest: s => s === '.wkrgb[data-plv]' ? btn : null } });
const before = fd.scrollTop;
RAF.forEach(f => f());
console.log(JSON.stringify([mid, PLVIEW, before, fd.scrollTop, PLS.sel, PAINTS, CLR]));
"""
        mid, view, before, after, sel, paints, clr = _run(src)
        self.assertEqual(mid, ["harness", "harness", ["fast|900"], 640, 0, 0])
        self.assertEqual([view, before, after, sel, paints], ["pipe", 0, 640, "a", 2])
        self.assertEqual(clr, 1)   # leaving Harness clears the hnGo target

    def test_r4_project_change_resets_scroll(self):
        src = ("let PLNEW = 1, PLDRAFT = 1, PLSTD = true;\nconst PLS = { proj: '/a', pipeTop: 640 };\nconst lsSet = () => {};\n"
               + js_fn("plProjGo") + "\nconst same = plProjGo('/a'), t0 = PLS.pipeTop; plProjGo('/b');\nconsole.log(JSON.stringify([same, t0, PLS.pipeTop]));")
        self.assertEqual(_run(src), [False, 640, 0])

    def test_r1_capture_listeners_stop_and_go(self):
        f = _read("web/js/48f-pipeline-evline.js")
        lis = f[f.index("function plEvfKey"):]
        src = r"""
const H = {}, GO = [];
const document = { addEventListener: (t, fn, cap) => { H[t] = [fn, cap]; } };
function plGoHarness(k){ GO.push(k); }
const el = { dataset: { plevf: 'fast|900' } };
const tgt = { closest: s => s === '.plnd [data-plevf]' ? el : null }, other = { closest: () => null };
const ev = (target, key) => ({ target, key, stop: 0, prev: 0, stopPropagation(){ this.stop++; }, preventDefault(){ this.prev++; } });
""" + lis + r"""
const out = [];
for(const [t, key] of [['pointerdown'], ['click'], ['keydown', 'Enter'], ['keydown', ' '], ['keydown', 'a']]){ const e = ev(tgt, key); H[t][0](e); out.push([t, key || '', e.stop, H[t][1]]); }
const o = ev(other, 'Enter'); H.click[0](o); H.keydown[0](o); H.pointerdown[0](o);
console.log(JSON.stringify([out, GO, o.stop]));
"""
        out, go, ostop = _run(src)
        self.assertEqual(out, [["pointerdown", "", 1, True], ["click", "", 1, True], ["keydown", "Enter", 1, True],
                               ["keydown", " ", 1, True], ["keydown", "a", 0, True]])
        self.assertEqual(go, ["fast|900"] * 3)   # click · Enter · Space; pointerdown only stops the drag
        self.assertEqual(ostop, 0)


if __name__ == "__main__":
    unittest.main()
