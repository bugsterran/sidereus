"""Structure «Architecture» deviation filter (84j): the «{n} outside {s} flow» header badge is a toggle button whose tooltip says
it is a review hint (R1); pressed, the edge list shows only the deviating edges with their reason (R2) under a «Not an error» line (R3)."""
import json
import re
import shutil
import unittest

from tests.test_struct_arch_js import EDGES, MODS, _SRC, run

STYLE = {"style": "hexagonal", "framework": "", "ok": True, "evidence": []}
DEV = [{"i": 2, "a": "adapter", "b": "web"}, {"i": 0, "a": "x<y", "b": "data"}]
D = {"ok": True, "commit": "c1", "modules": MODS, "edges": EDGES, "style": STYLE, "dev": DEV}
CLICK = re.search(r"^document\.addEventListener\('click', ev => \{\n  const t = ev\.target.*?^\}\);$", _SRC, re.S | re.M).group(0)
# Paint helper: archEdTreeHtml stands in for 84j6 so the test sees whether the tree was bypassed.
PAINT = ("globalThis.archMmd = s => '<M/>'; globalThis.archEdTreeHtml = () => '<TREE/>';"
         "const box = {innerHTML: '', querySelector(){ return null; }}; const pt = () => { box._arsig = ''; archPaint(box, head); return box.innerHTML; };")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchDevFilter(unittest.TestCase):
    def test_R1_badge_is_toggle_with_hint(self):
        r = run("const d = " + json.dumps(D) + ";"
                "console.log(JSON.stringify([archHeadNote(d), archHeadNote(d, true), archHeadNote(Object.assign({}, d, {dev: []})), archStyleParts(d).dev]));", "en")
        off, on, none, dev = r
        self.assertIn('<button type=button class="strbg strbg-cy strbg-dvf" data-ardv aria-pressed=false title="', off)
        self.assertIn("aria-pressed=true", on)
        self.assertIn(">2 outside Hexagonal flow</button>", off)
        tip = re.search(r'data-ardv aria-pressed=false title="([^"]*)"', off).group(1)
        for w in ("Review hint, not an error", "Hexagonal flow", "Keep an edge if it is intended", "reverse the dependency"):
            self.assertIn(w, tip)
        self.assertNotIn("data-ardv", none)                    # no deviations: no button
        self.assertNotIn("Edges whose module roles", dev)
        ko = run("console.log(JSON.stringify(archHeadNote(" + json.dumps(D) + ")));")
        self.assertIn("오류가 아니라 검토 힌트", ko)

    def test_R2_R3_filtered_list(self):
        r = run(PAINT + "ARCH.cache['/r'] = " + json.dumps(D) + "; const full = pt(); ARCH.dvf = '/r'; const on = pt();"
                "ARCH.dvf = ''; const back = pt(); console.log(JSON.stringify([full, on, back]));", "en")
        full, on, back = r
        self.assertIn("<TREE/>", full)
        self.assertNotIn("archdvn", full)
        side = on.split("<aside class=archside>", 1)[1]
        self.assertNotIn("<TREE/>", side)
        self.assertIn('<div class=archdvn role=status>Not an error · 2 edges to review</div><ul class="archel-list archdvl">', side)
        self.assertEqual(re.findall(r'data-ae="(\d+)"', side), ["0", "2"])   # deviating indices only, ascending
        self.assertIn("x&lt;y → Data is outside the Hexagonal flow", side)
        self.assertIn("Adapter → Web is outside the Hexagonal flow", side)
        self.assertIn("aria-pressed=true", on.split("<aside", 1)[0])
        self.assertEqual(back, full)                           # off restores the full list

    def test_R3_ko_line(self):
        r = run("console.log(JSON.stringify(archDevListHtml(" + json.dumps(EDGES) + ", {}, '/r', {1: {a: 'web', b: 'data'}}, '육각형', '')));")
        self.assertIn("오류 아님 · 검토할 연결 1건", r)

    def test_out_of_range_index_no_row(self):
        r = run("console.log(JSON.stringify(archDevListHtml(" + json.dumps(EDGES) + ", {}, '/r', {1: {a: 'a', b: 'b'}, 9: {a: 'a', b: 'b'}}, 'S', '/r\\t1')));", "en")
        self.assertEqual(re.findall(r'data-ae="(\d+)"', r), ["1"])
        self.assertIn("1 edges to review", r)
        self.assertIn('class="arche on"', r)                   # open row follows op

    def test_auto_off_without_deviations(self):
        r = run(PAINT + "ARCH.cache['/r'] = Object.assign(" + json.dumps(D) + ", {dev: []}); ARCH.dvf = '/r'; const h = pt();"
                "console.log(JSON.stringify([ARCH.dvf, h]));", "en")
        self.assertEqual(r[0], "")
        self.assertIn("<TREE/>", r[1])
        self.assertNotIn("archdvn", r[1])

    def test_module_pick_turns_filter_off(self):
        r = run(PAINT + "ARCH.cache['/r'] = " + json.dumps(D) + "; ARCH.dvf = '/r'; const on = pt(); ARCH.sel = {p: '/r', id: 'b'}; const h = pt();"
                "console.log(JSON.stringify([on.indexOf('aria-pressed=true') >= 0, ARCH.dvf, h.split('<aside', 1)[0]]));", "en")
        self.assertTrue(r[0])
        self.assertEqual(r[1], "")
        self.assertIn("data-ardv aria-pressed=false", r[2])
        self.assertNotIn("aria-pressed=true", r[2])

    def test_R2_click_toggles_and_clears_focus(self):
        r = run("const HS = [], HOLD = []; document.addEventListener = (k, f) => { if(k === 'click') HS.push(f); }; function kbHold(s){ HOLD.push(s); }"
                "eval(" + json.dumps(CLICK) + ");"
                "const btn = {}, tab = {}, ev = {target: {closest(s){ return s === '.archtab' ? tab : s === '[data-ardv]' ? btn : null; }}};"
                "ARCH.sel = {p: '/r', id: 'a'}; ARCH.flow = {p: '/r', id: 'f'}; ARCH.op = '/r\\t0'; document.activeElement = btn;"
                "HS[0](ev); const a = [ARCH.dvf, ARCH.sel, ARCH.flow, ARCH.op, PAINTS];"
                "ARCH.sel = {p: '/r', id: 'b'}; document.activeElement = null; HS[0](ev); const b = [ARCH.dvf, ARCH.sel, PAINTS];"
                "console.log(JSON.stringify([a, b, HOLD]));")
        self.assertEqual(r[0], ["/r", None, None, "", 1])
        self.assertEqual(r[1], ["", {"p": "/r", "id": "b"}, 2])   # second press restores, leaves selection alone
        self.assertEqual(r[2], [".archtab [data-ardv]"])


if __name__ == "__main__":
    unittest.main()
