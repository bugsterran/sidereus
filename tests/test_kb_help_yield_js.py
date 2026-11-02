"""With the keyboard help sheet open, ⌘K / `s` / `/` / ⌘B close it before acting, so two overlays never stack (98-a11y kbHelpYield)."""
import json
import os
import re
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def src(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def handler(rel, start):
    """The `document.addEventListener('keydown', ...)` block that contains `start`."""
    s = src(rel)
    i = s.rindex("document.addEventListener('keydown'", 0, s.index(start))
    return s[i:s.index("\n});", s.index(start)) + 4] if rel != "web/js/92d-rail.js" else s[i:s.index("\n  });", i) + 6]


STUB = r"""
const OPEN = {kbhelp: true}, LOG = [], LS = [];
let ISPOP = false, ISWP = false, ISBP = false, wkOn = false, cpOn = false, railOpen = false;
const tourIsOpen = () => false, kbTyping = () => false, softErr = () => {};
const popIsOpen = id => !!OPEN[id];
const kbHelpClose = () => { OPEN.kbhelp = false; LOG.push('help-close'); };
const kbHelpOpen = () => { OPEN.kbhelp = true; };
const kbSearchBox = () => ({focus(){ LOG.push('search:' + (OPEN.kbhelp ? 'help' : 'clear')); }, select(){}});
const cpOpen = () => { cpOn = true; LOG.push('palette:' + (OPEN.kbhelp ? 'help' : 'clear')); }, cpClose = () => { cpOn = false; };
const railSet = v => { railOpen = v; LOG.push('rail:' + (OPEN.kbhelp ? 'help' : 'clear')); };
const railKeyB = e => !!(e.metaKey && e.key === 'b'), railCovered = () => true, railCloseOver = () => false;
const SESB = {offsetParent: {}, click(){ LOG.push('sessions:' + (OPEN.kbhelp ? 'help' : 'clear')); }};
const H = [];
const document = {addEventListener: (t, f) => H.push(f), getElementById: id => id === 'sesb' ? SESB : null, querySelectorAll: () => []};
function fire(o){ const e = Object.assign({key: '', code: '', target: {tagName: 'BODY'}, defaultPrevented: false, preventDefault(){ this.defaultPrevented = true; }}, o); H.forEach(f => f(e)); }
"""


class KbHelpYield(unittest.TestCase):
    def test_no_overlay_over_help(self):
        js = (STUB + js_fn("kbKey") + "\n" + js_fn("kbHelpYield") + "\n"
              + handler("web/js/98-a11y.js", "kbHelpYield(); b.click()") + "\n"
              + handler("web/js/40-sessions.js", "Cmd+K (mac)") + "\n"
              + handler("web/js/92d-rail.js", "if(railKeyB(e))") + "\n"
              + "const R = {};"
              + "for(const [n, o] of [['k', {key: 'k', metaKey: true}], ['s', {key: 's'}], ['slash', {key: '/'}], ['b', {key: 'b', metaKey: true}], ['digit', {key: '2'}]]){"
              + " OPEN.kbhelp = true; LOG.length = 0; cpOn = false; fire(o); R[n] = LOG.slice(); }"
              + "process.stdout.write(JSON.stringify(R));")
        r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        R = json.loads(r.stdout)
        self.assertEqual(R["k"], ["help-close", "palette:clear"])
        self.assertEqual(R["s"], ["help-close", "sessions:clear"])
        self.assertEqual(R["slash"], ["help-close", "search:clear"])
        self.assertEqual(R["b"], ["help-close", "rail:clear"])
        self.assertEqual(R["digit"], [])   # digits stay blocked under help

    def test_handlers_call_it(self):
        for rel in ("web/js/40-sessions.js", "web/js/92d-rail.js"):
            self.assertTrue(re.search(r"kbHelpYield\(\)", src(rel)), rel)


if __name__ == "__main__":
    unittest.main()
