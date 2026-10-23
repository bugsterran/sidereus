"""«파이프라인» canvas a11y/i18n: palette presets are buttons, node titles use display names, focus survives repaint,
«실행» keeps >=4.5:1 in light and dark. Pure functions under node; CSS tokens read from web/css (no live files)."""
import json
import os
import re
import subprocess
import unittest

from tests._load import ROOT, js_all, js_fn
from tests._node import node_e

STUBS = """
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s, KE = (k, e) => LANG === 'en' ? e : k, ago = s => s + 's';
const PL_JUDGED = [], PL_LOW = [];
function plLabTip(x){ return x; }
let PLPGRP = {}, PLPQ = '';
"""


def _js(body, lang="ko"):
    src = js_all()
    consts = "\n".join(re.search(r"^const %s[^\n]*$" % c, src, re.M).group(0) for c in ("PLG_GFAM", "PLG_W"))
    consts += "\n" + re.search(r"^const PLG_FAM = [\s\S]*?\};$", src, re.M).group(0)
    consts += "\n" + re.search(r"^const PLG_NAMES = [\s\S]*?^PLG_NAMES\.ko = \{\};", src, re.M).group(0)
    fns = "\n".join(js_fn(f) for f in ("plgShow", "plgBase", "plPalHit", "plgFam", "plgColor", "plgHue", "plgPfc", "plgTpl", "plPalette", "plFlagChips", "plAgDesc", "plNodeHtml",
                                        "plgGraded", "plgGuards", "plRow", "plGuardsPane"))
    code = "let LANG = %s;\n" % json.dumps(lang) + STUBS + consts + "\n" + fns + "\n" + body
    return subprocess.run(node_e(code), capture_output=True, text=True, check=True, encoding="utf-8").stdout


def _hex(s):
    return [int(s[i:i + 2], 16) for i in (1, 3, 5)]


def _lum(c):
    a = [(v / 255) / 12.92 if v / 255 <= .03928 else ((v / 255 + .055) / 1.055) ** 2.4 for v in c]
    return .2126 * a[0] + .7152 * a[1] + .0722 * a[2]


def _cr(a, b):
    x, y = _lum(a), _lum(b)
    return (max(x, y) + .05) / (min(x, y) + .05)


def _mix(a, b, p):
    return [x * p + y * (1 - p) for x, y in zip(a, b)]


def _css(name):
    with open(os.path.join(ROOT, "web", "css", name), encoding="utf-8") as fh:
        return fh.read()


CAT = {"groups": [{"id": "quality", "en": "Quality"}, {"id": "review", "en": "Review"}], "items": [
    {"id": "lint", "group": "quality", "title": {"ko": "린트·정적 분석", "en": "Lint"}, "gate": "python3 x.py --verify", "asserts": "1+ files",
     "tools": [{"id": "ruff", "bin": "ruff", "install": "pipx install ruff", "net": False, "avail": False},
               {"id": "mypy", "bin": "mypy", "install": "pipx install mypy", "net": False, "avail": True}]},
    {"id": "review", "group": "review", "title": {"ko": "리뷰", "en": "Review"}, "gate": "", "gateHint": "a diff tool", "tools": []}]}


class Palette(unittest.TestCase):
    def _pal(self, nodes="[]", lang="en"):
        return _js("console.log(plPalette({ G: { nodes: %s } }, %s));" % (nodes, json.dumps(CAT)), lang)

    def test_catalog_items(self):
        out = self._pal()
        self.assertIn("Stage catalog", out)
        self.assertIn("Click + or drag onto the canvas", out)
        self.assertIn('data-plgrp="quality"', out)
        self.assertIn('<button type=button class=plpi draggable=true data-pldrag="c:lint"', out)
        self.assertEqual(out.count("data-plcadd="), 2)                     # visible «+ Add» per item
        self.assertEqual(out.count("class=plcg"), 1)                       # «graded» only with a gate
        self.assertIn('class="plcdot part"', out)                          # one of two tools missing
        self.assertIn("ruff — pipx install ruff", out)                     # tooltip = install hint
        self.assertNotIn("mypy — ", out)
        self.assertIn("Gate idea: a diff tool", out)                       # gateless item shows its hint
        self.assertIn("class=\"plci pf-qual\"", out)                     # group family colour
        used = self._pal("[{title: '리뷰'}]")
        self.assertIn('data-plcadd="review"', used)                        # in use: adding again makes «리뷰 2»
        self.assertIn('data-pldrag="c:review"', used)
        self.assertIn('data-plgrp="review"', used)                         # still listed, dimmed with «in use»
        self.assertIn('class="plci pf-review used"', used)
        self.assertIn('>in use</span>', used)
        self.assertIn('data-pldrag="c:review"', self._pal())

    def test_filter_by_name(self):
        def pal(q, nodes="[]"):
            return self._pal(nodes) if not q else _js("PLPQ = %s; console.log(plPalette({ G: { nodes: %s } }, %s));" % (json.dumps(q), nodes, json.dumps(CAT)), "en")
        out = pal("  LINT ")                                                  # trimmed, case-insensitive, en title
        self.assertRegex(out, r'data-plq="[^"]*lint[^"]*">')                # match: row visible
        self.assertRegex(out, r'data-plq="[^"]*review[^"]*" hidden>')       # no match: row hidden
        self.assertIn('data-plgrp="review" hidden>', out)                   # empty group hidden
        self.assertIn('data-plgrp="quality" open>', out)                    # matching group opened
        self.assertIn("class=plpnm hidden>", out)
        self.assertIn('value="  LINT "', out)                               # query survives a repaint
        self.assertIn('data-plgrp="review" hidden>', pal("quality"))                   # group label matches too
        self.assertIn('data-plgrp="quality" open>', pal("quality"))
        self.assertIn('data-plgrp="quality" open>', pal("린트"))                         # ko title
        used = pal("리뷰", "[{title: '리뷰'}]")
        self.assertIn('class="plci pf-review used"', used)                  # «in use» row stays visible when it matches
        self.assertNotRegex(used, r'used" data-plq="[^"]*" hidden>')
        none = pal("zzz")
        self.assertIn('No match — + Custom stage creates &quot;zzz&quot;</div>', none)
        self.assertNotIn("plpnm hidden", none)
        self.assertIn('class="wkrgb plhot"', none)
        self.assertEqual(none.count("<details"), none.count(" hidden><summary"))      # every group hidden
        self.assertNotIn('class="wkrgb plhot"', self._pal())                # empty box: full list, plain button

    def test_no_recommended_stages_left(self):
        for d in ("js", "css"):
            for f in os.listdir(os.path.join(ROOT, "web", d)):
                with open(os.path.join(ROOT, "web", d, f), encoding="utf-8") as fh:
                    txt = fh.read()
                for gone in ("Recommended stages", "PLG_PRESETS", "PLG_GROUPS", "plgAddPreset"):
                    self.assertNotIn(gone, txt, f)

    def test_guards_pane(self):
        G = ("{ nodes: [{ id: 'a', title: '구현', gate: 'bash t.sh' }, { id: 'b', title: '리뷰' }, { id: 'c', title: '검증', gate: 'x' }],"
             " guards: { requireGates: ['검증'], maxLoopBacks: 4 } }")
        out = _js("console.log(plGuardsPane(%s));" % G)
        self.assertIn('data-plgq="구현">', out)
        self.assertIn('data-plgq="검증" checked>', out)
        self.assertNotIn('data-plgq="리뷰"', out)                          # gateless stages cannot be required
        self.assertIn('data-plgm min=1 max=10 value="4"', out)
        m = _js("console.log(plGuardsPane(%s, ['check\\\\.sh\\\\s+--fast']));" % G.replace("'bash t.sh'", "'scripts/check.sh --fast'"))
        self.assertIn('data-plgq="구현">', m)
        self.assertNotIn('data-plgq="검증"', m)                            # gate that records no evidence: cannot be required
        self.assertIn("No stage has a graded gate yet", _js("console.log(plGuardsPane({ nodes: [{ id: 'b', title: '리뷰' }] }));"))

    def test_node_title_display_name(self):
        G = "{ nodes: [], loops: [], flow: [], defaults: { model: 'inherit' } }"
        body = "const E = { G: %s }; console.log(plNodeHtml(E, { id: 'n1', title: '설계', agent: 'a', ui: { x: 0, y: 0 } }, false, null)"
        body += " + '\\n' + plNodeHtml(E, { id: 'n2', title: '내 단계', agent: 'a', ui: { x: 0, y: 0 } }, false, null));"
        en = _js(body % G, "en")
        self.assertIn("<div class=plt>Design", en)
        self.assertIn("<div class=plt>내 단계", en)          # custom titles stay as written
        self.assertIn("<div class=plt>설계", _js(body % G, "ko"))

    def test_focus_restored_after_repaint(self):
        src = js_all()
        self.assertRegex(src, r"\[data-plstd\]'\)\)\{ PLSTD = !PLSTD; plPaint\(\); plRefocus\(")
        self.assertRegex(src, r"PLS\.std = so\.dataset\.plstdopen;[^\n]*plPaint\(\); plRefocus\(")
        self.assertRegex(src, r"\[data-plnew\]'\)\)\{[^\n]*plPaint\(\); plRefocus\('\[data-plnf=name\]'\)")
        for fn in ("plSave", "plDelete", "plNewSend"):          # async repaints end on a control, not BODY
            self.assertRegex(src, r"\nasync function %s\([^\n]*\n(?:  [^\n]*\n)*  plPaint\(\); plRefocus\(" % fn, fn)

    def test_template_options_display_names(self):
        src = js_fn("plTplList")
        self.assertIn("plgTplShow(x.title)", src)
        self.assertNotIn("+ x.title +", src)

    def test_run_button_contrast(self):
        # Run / Save / draft save = primary (.plsv): white on --nx-info-bg; Edit / Back = --nx-info text on bg/panel (+ its 10% tint)
        css = _css("43-pipeline.css")
        self.assertIn('class="wkrgb plsv plrn', open(os.path.join(ROOT, "web", "js", "48-pipeline.js"), encoding="utf-8").read())
        self.assertRegex(css, r":is\(\.plact,\.plnames,\.pltop\) \.wkrgb\.plsv\{background:var\(--nx-info-bg\);border-color:var\(--nx-info-bg\);color:#fff")
        self.assertRegex(css, r":is\(\.plact,\.pltop\) \.wkrgb\.plmode\{border-color:var\(--nx-info\);color:var\(--nx-info\);background:color-mix\(in srgb,var\(--nx-info\) 5%")
        for f, sel in (("91-light.css", r"html\[data-ui=next\]\[data-theme=light\]\{"), ("90-main-ui.css", r"html\[data-ui=next\]\{")):
            blk = _css(f)[re.search(sel, _css(f)).end():]
            tok = lambda k: _hex(re.search(r"--nx-%s:(#[0-9a-f]{6})" % k, blk).group(1))
            self.assertGreaterEqual(_cr(_hex("#ffffff"), tok("info-bg")), 4.5, f)
            for bg in (tok("bg"), tok("panel")):
                for t in (0, .05, .10):
                    self.assertGreaterEqual(_cr(tok("info"), _mix(tok("info"), bg, t)), 4.5, (f, t))


if __name__ == "__main__":
    unittest.main()
