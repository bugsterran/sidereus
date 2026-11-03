"""morphKids keeps 98-a11y marks (tabindex/role/data-kb) only on a node of the same kind; a marked row reused for
another class is replaced, so e.g. the To-do header .stdhd never becomes an empty tab stop (web/js/08-ui-kit.js)."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

DOM = r"""
const MORPH_KEEP = {tabindex: 1, role: 1, 'data-kb': 1};
function El(tag, attrs, kids){
  const e = {nodeType: 1, nodeName: tag, tagName: tag, childNodes: kids || [], _a: Object.assign({}, attrs || {})};
  Object.defineProperty(e, 'attributes', {get(){ return Object.keys(e._a).map(k => ({name: k, value: e._a[k]})); }});
  e.getAttribute = k => k in e._a ? e._a[k] : null;
  e.setAttribute = (k, v) => { e._a[k] = String(v); };
  e.hasAttribute = k => k in e._a;
  e.removeAttribute = k => { delete e._a[k]; };
  e.appendChild = c => { e.childNodes.push(c); };
  e.replaceChild = (n, o) => { e.childNodes[e.childNodes.indexOf(o)] = n; };
  e.removeChild = c => { e.childNodes.splice(e.childNodes.indexOf(c), 1); };
  return e;
}
const MARK = {tabindex: '0', role: 'button', 'data-kb': ''};
"""


def _js(body):
    src = DOM + js_fn("morphKind") + "\n" + js_fn("morphKids") + "\n" + body
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class MorphKbKind(unittest.TestCase):
    def test_other_class_drops_marks(self):
        o = _js("const a = El('DIV', Object.assign({class: 'sxw s-tool'}, MARK)), p = El('DIV', {}, [a]);"
                "morphKids(p, El('DIV', {}, [El('DIV', {class: 'stdhd'})]));"
                "const c = p.childNodes[0]; console.log(JSON.stringify({same: c === a, a: c._a}));")
        self.assertFalse(o["same"])
        self.assertEqual(o["a"], {"class": "stdhd"})

    def test_same_kind_repaint_keeps_marks(self):
        o = _js("const a = El('DIV', Object.assign({class: 'sxw s-tool'}, MARK)), p = El('DIV', {}, [a]);"
                "morphKids(p, El('DIV', {}, [El('DIV', {class: 'sxw s-idle', title: 't'})]));"
                "const c = p.childNodes[0]; console.log(JSON.stringify({same: c === a, a: c._a}));")
        self.assertTrue(o["same"])
        self.assertEqual(o["a"], {"class": "sxw s-idle", "title": "t", "tabindex": "0", "role": "button", "data-kb": ""})

    def test_unmarked_node_still_morphs_in_place(self):
        o = _js("const a = El('DIV', {class: 'sxw'}), p = El('DIV', {}, [a]);"
                "morphKids(p, El('DIV', {}, [El('DIV', {class: 'stdhd'})]));"
                "const c = p.childNodes[0]; console.log(JSON.stringify({same: c === a, a: c._a}));")
        self.assertTrue(o["same"])
        self.assertEqual(o["a"], {"class": "stdhd"})


if __name__ == "__main__":
    unittest.main()
