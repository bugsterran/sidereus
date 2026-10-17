"""Timeline polish (2026-09-27): bar label ink reaches 4.5:1 on every agent hue, hover card stays in its box and off #tlcurp."""
import json
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

LUM = """
const lin = v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
const hsl = (H, S, L) => { const a = S * Math.min(L, 1 - L);
  return [0, 8, 4].map(n => { const k = (n + H / 30) % 12; return L - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)); }); };
const Y = c => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
const CR = (a, b) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
const INK = Y([13 / 255, 16 / 255, 20 / 255]);
let LIGHT = false; const thc = (dk, lt) => LIGHT ? lt : dk;   // 00-core.js theme pick, stubbed
"""


def run(body):
    src = LUM + js_fn("agColor") + "\n" + js_fn("tlInk") + "\n" + js_fn("tlHovPos") + "\n" + body
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


class Ink(unittest.TestCase):
    def test_every_hue_passes(self):
        worst = run("let w = 99; for(let h = 0; h < 360; h++){ const bg = 'hsl('+h+' 38% 52%)';"
                    "const y = Y(hsl(h, .38, .52)); const k = tlInk(bg), c = k === 'tlbi' ? CR(y, 1) : CR(y, k ? 0 : INK); w = Math.min(w, c); }"
                    "const y2 = Y([91/255, 141/255, 239/255]); const k2 = tlInk('#5b8def'); w = Math.min(w, k2 === 'tlbi' ? CR(y2, 1) : CR(y2, k2 ? 0 : INK));"
                    "console.log(JSON.stringify(w));")
        self.assertGreaterEqual(worst, 4.5)

    def test_agcolor_format_parsed(self):
        # agColor's string must be the format tlInk parses (a silent mismatch would fall into the hex path)
        out = run("console.log(JSON.stringify([agColor('Explore'), tlInk('#ffffff'), tlInk('#000000')]))")
        self.assertRegex(out[0], r"^hsl\(\d+ 38% 52%\)$")
        self.assertEqual(out[1:], ["", "tlbi"])

    def test_light_agcolor_darker_and_inked(self):
        # light track: 42% keeps every hue >=3.17:1 on #fdfefe (52% greens were 2.5) and labels still reach 4.5
        out = run("LIGHT = true; const c = agColor('Explore'); let lo = 99, ink = 99; const P = Y([253/255, 254/255, 254/255]);"
                  "for(let h = 0; h < 360; h++){ const y = Y(hsl(h, .38, .42)); lo = Math.min(lo, CR(y, P));"
                  "const k = tlInk('hsl('+h+' 38% 42%)'); ink = Math.min(ink, k === 'tlbi' ? CR(y, 1) : CR(y, k ? 0 : INK)); }"
                  "console.log(JSON.stringify([c, lo, ink]))")
        self.assertRegex(out[0], r"^hsl\(\d+ 38% 42%\)$")
        self.assertGreaterEqual(out[1], 3.0)
        self.assertGreaterEqual(out[2], 4.5)


class CardPos(unittest.TestCase):
    BOX = {"l": 8, "t": 8, "r": 1040, "b": 892}

    def pos(self, x, y, av=None, w=300, h=180):
        return run("console.log(JSON.stringify(tlHovPos(%d, %d, %d, %d, %s, %s)))"
                   % (w, h, x, y, json.dumps(self.BOX), json.dumps(av)))

    def test_right_edge_flips_inside_box(self):
        l, t = self.pos(1030, 400)
        self.assertLessEqual(l + 300, self.BOX["r"])
        self.assertEqual(l, 1030 - 14 - 300)

    def test_default_right_of_pointer(self):
        self.assertEqual(self.pos(400, 300), [414, 316])

    def test_never_over_panel(self):
        av = {"left": 414, "right": 666, "top": 290, "bottom": 540}   # panel where the card would go
        for x, y in ((400, 300), (700, 360), (1000, 800), (420, 880)):
            l, t = self.pos(x, y, av)
            over = max(0, min(l + 300, av["right"]) - max(l, av["left"])) * max(0, min(t + 180, av["bottom"]) - max(t, av["top"]))
            self.assertEqual(over, 0, (x, y, l, t))
            self.assertTrue(self.BOX["l"] <= l and l + 300 <= self.BOX["r"] and self.BOX["t"] <= t and t + 180 <= self.BOX["b"])


if __name__ == "__main__":
    unittest.main()
