"""«Replay the tour» from shortcut help: Esc at the tour returns focus to the button that opened help, not BODY (98-a11y kbHelpOpen -> 98b-tour tourOpen/tourEnd)."""
import json
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

STUB = r"""
const OPEN = {};
let ISPOP = false, ISWP = false, ISBP = false, mainView = 'pipe', FEATS = {}, SESS = [], UIPOPS = [];
let tourI = -1, tourList = [], tourFrom = '', tourBack = null, tourTimer = 0, tourSpot = null;
const T = s => s, esc = s => String(s), softErr = () => {}, cfgClose = () => {};
const popIsOpen = id => !!OPEN[id];
const popHide = id => { OPEN[id] = false; const p = EL[id]; if(p){ p.hidden = true; if(document.activeElement === p || p.contains(document.activeElement)) document.activeElement = document.body; } };
const tourIsOpen = () => !!EL.tour && !EL.tour.hidden;
const tourPlan = () => [{}], tourHas = () => true, tourPlEdit = () => false, tourPlace = () => {};
const tourClick = () => {}, tourGo = i => { tourI = i; }, setMainView = v => { mainView = v; };
const UIS = {setItem(){}};
const setInterval = () => 1, clearInterval = () => {};
const EL = {};
function mk(tag){
  const kids = [];
  const n = {tagName: tag.toUpperCase(), hidden: false, isConnected: true, attrs: {}, _btn: {},
    setAttribute(k, v){ this.attrs[k] = v; }, addEventListener(){},
    focus(){ document.activeElement = this; }, contains: x => x === n || kids.includes(x),
    set innerHTML(h){ for(const c of ['kbhx', 'kbhtour']){ const b = mk('button'); b.className = c; kids.push(b); n._btn[c] = b; } },
    querySelector(s){ return n._btn[s.slice(1)] || null; }};
  return n;
}
const document = {activeElement: null,
  createElement: mk, getElementById: id => EL[id] || null,
  body: {tagName: 'BODY', appendChild(n){ EL[n.id] = n; }, focus(){ document.activeElement = this; }}};
document.activeElement = document.body;
const KB_KEYS = [];
const kbKeyLab = k => k;
"""


class KbHelpTourFocus(unittest.TestCase):
    def run_js(self, body):
        js = (STUB + "\n".join(js_fn(n) for n in ("kbHelpClose", "kbHelpOpen", "tourOpen", "tourEnd"))
              + "\nlet kbHelpFrom = null;\nconst opener = mk('button'); opener.id = 'opener';\n"
              + "function openHelp(){ opener.focus(); kbHelpOpen(); OPEN.kbhelp = true; }\n"
              + body)
        r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_replay_tour_then_esc_returns_to_opener(self):
        R = self.run_js("openHelp(); EL.kbhelp._btn.kbhtour.onclick();"
                        "tourEnd(); process.stdout.write(JSON.stringify({back: document.activeElement === opener, tour: tourIsOpen()}));")
        self.assertEqual(R, {"back": True, "tour": False})

    def test_help_close_returns_to_opener(self):
        R = self.run_js("openHelp(); const inHelp = document.activeElement === EL.kbhelp; kbHelpClose(true);"
                        "process.stdout.write(JSON.stringify({inHelp, back: document.activeElement === opener}));")
        self.assertEqual(R, {"inHelp": True, "back": True})


if __name__ == "__main__":
    unittest.main()
