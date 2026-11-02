"""web/js/17-attention.js focus restore after a redraw: same row (same control), else next, else previous, else the list."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def run(src):
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class AttnFocus(unittest.TestCase):
    def test_pick(self):
        out = run(js_fn("attnFocusPick") + "\nconst o = ['a', 'b', 'c'];\nprocess.stdout.write(JSON.stringify(["
                  "attnFocusPick(o, ['a', 'b', 'c'], 'b'), attnFocusPick(o, ['a', 'c'], 'b'), attnFocusPick(o, ['a'], 'b'),"
                  " attnFocusPick(o, [], 'b'), attnFocusPick(o, ['c'], 'x')]));")
        self.assertEqual(out, ["b", "c", "a", "", ""])

    def test_back_same_control_then_row_then_list(self):
        src = (
            "let FOC = ''; const CSS = {escape: s => s};\n"
            "function softErr(){} function a11yOne(t){ if(t.n.startsWith('row')) t.attrs.tabindex = 0; }   // the list itself is not cursor:pointer\n"
            "function node(n, tag, attrs, kids){ return {n, tagName: tag, attrs: attrs || {}, kids: kids || [],\n"
            "  getAttribute(k){ return k in this.attrs ? this.attrs[k] : null; }, hasAttribute(k){ return k in this.attrs; },\n"
            "  set tabIndex(v){ this.attrs.tabindex = v; },\n"
            "  querySelector(s){ const m = /data-aa=\"(.*)\"/.exec(s); return this.kids.find(k => k.attrs['data-aa'] === m[1]) || null; },\n"
            "  focus(){ FOC = this.n; }}; }\n"
            "function row(aid){ return node('row:' + aid, 'DIV', {'data-aid': aid}, [node('work:' + aid, 'BUTTON', {'data-aa': 'work'})]); }\n"
            "function list(rows){ return Object.assign(node('list', 'DIV'), {querySelectorAll: () => rows}); }\n"
            + js_fn("attnFocusPick") + "\n" + js_fn("attnFocusBack") + "\n"
            "const r = [], fo = {aid: 'b', aa: 'work', aids: ['a', 'b', 'c']};\n"
            "attnFocusBack(list([row('a'), row('b'), row('c')]), fo); r.push(FOC);\n"
            "const c = row('c'); attnFocusBack(list([row('a'), c]), fo); r.push(FOC, c.attrs.tabindex);\n"
            "attnFocusBack(list([row('b')]), {aid: 'b', aa: '', aids: ['b']}); r.push(FOC);\n"
            "const l = list([]); attnFocusBack(l, fo); r.push(FOC, l.attrs.tabindex);\n"
            "process.stdout.write(JSON.stringify(r));")
        self.assertEqual(run(src), ["work:b", "row:c", 0, "row:b", "list", -1])


if __name__ == "__main__":
    unittest.main()
