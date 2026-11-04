"""Enter/Space on a 98-a11y marked element activates it, SVG <g> included (web/js/98-a11y.js delegated keydown).

⚠SVGElement has no click(): t.click() threw a TypeError on arch map edges (.mmdfe) and nodes ([data-p]), so keys did nothing.
Run under node with stubs."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all
from tests._node import node_e


def _listener():
    m = re.search(r"^// One delegated activator[^\n]*\n(document\.addEventListener\('keydown', [\s\S]*?^\}\);)", js_all(), re.M)
    if m is None:
        raise LookupError("98-a11y.js: delegated activator not found")
    return m.group(1)


def run(body):
    code = (r"""
let L = null; const document = { addEventListener(t, f){ if(t === 'keydown') L = f; } };
class MouseEvent { constructor(type, o){ this.type = type; this.bubbles = o.bubbles; this.cancelable = o.cancelable; } }
const R = [];
function ev(t, key){ return { key, target: t, defaultPrevented: false, isComposing: false, repeat: false, preventDefault(){ this.defaultPrevented = true; } }; }
function el(withClick){ const o = { hasAttribute: a => a === 'data-kb', dispatchEvent(e){ R.push(['dispatch', e.type, e.bubbles, e.cancelable]); return true; } };
  if(withClick) o.click = () => R.push(['click']); return o; }
""" + _listener() + "\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    return json.loads(subprocess.run(node_e(code), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SvgActivate(unittest.TestCase):
    def test_svg_g_gets_bubbling_click(self):
        self.assertEqual(run("const e = ev(el(false), 'Enter'); L(e); R.push(e.defaultPrevented);"),
                         [["dispatch", "click", True, True], True])

    def test_html_element_uses_click(self):
        self.assertEqual(run("L(ev(el(true), ' '));"), [["click"]])


if __name__ == "__main__":
    unittest.main()
