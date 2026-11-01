"""Session to-do chip and layer (web/js/40c-sessions-todo.js): count, empty state, order, escaping, no T() on item text."""
import json
import os
import shutil
import subprocess
import unittest

from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "web", "js", "40c-sessions-todo.js"), encoding="utf-8") as _f:
    SRC = _f.read()

STUB = ("const TCALLS = [];"
        "const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\"/g, '&quot;');"
        "const T = s => { TCALLS.push(s); return s; };"
        "const TV = o => { TCALLS.push(o.msg); return o.msg.replace(/\\{(\\w+)\\}/g, (m, k) => o.vars[k]); };"
        "const sessLabel = x => 'LIVE-' + x.state; const softErr = () => {}; const note = () => {};"
        "const getJSON = () => new Promise(() => {}); const postJSON = () => new Promise(() => {});"
        "let sessHover = false, sessDirty = false; const buildSessions = () => {};"
        "const document = {getElementById: () => null};\n")


def _js(body):
    r = subprocess.run(node_e(STUB + SRC + "\n" + body), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


ITEMS = "[{i: 0, s: 'x', t: 'done one', h: 'a'}, {i: 1, s: ' ', t: 'open <b>&', h: 'b'}, {i: 2, s: '~', t: 'busy', h: 'c'}]"


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TodoChip(unittest.TestCase):
    def test_count_is_open_plus_working(self):
        o = _js("stodoSet({'/r': {o: 2, w: 1, d: 5}}); console.log(JSON.stringify(stodoChip({cwd: '/r', sid: 's'})));")
        self.assertIn(">To-do 3<", o)

    def test_empty_or_missing_draws_nothing(self):
        o = _js("const a = stodoChip({cwd: '/r'}); stodoSet({'/r': {o: 0, w: 0, d: 0}});"
                "console.log(JSON.stringify([a, stodoChip({cwd: '/r'}), stodoChip({cwd: '/q'}),"
                " (STODO_OPEN.add('|/r'), stodoLayer({cwd: '/r'})), (stodoSet(undefined), stodoChip({cwd: '/r'}))]));")
        self.assertEqual(o, ["", "", "", "", ""])

    def test_order_working_open_done_and_live_label(self):
        o = _js("console.log(JSON.stringify(stodoItemsHtml(" + ITEMS + ", {state: 'tool'})));")
        self.assertLess(o.index("busy"), o.index("open &lt;b&gt;&amp;"))
        self.assertLess(o.index("open &lt;b&gt;&amp;"), o.index("done one"))
        self.assertIn("Working</span> <span class=stds>LIVE-tool<", o)
        self.assertEqual(o.count("LIVE-"), 1)   # only the `- [~]` item carries the state label

    def test_text_escaped_and_never_through_T(self):
        o = _js("const h = stodoItemsHtml(" + ITEMS + ", {state: 'wait'}) + stodoDaysHtml([{day: '2026-01-01', added: ['<i>x'], started: [], done: ['busy']},"
                " {day: '2026-01-02', added: ['n'], started: ['m'], done: []}]);"
                "console.log(JSON.stringify({h: h, t: TCALLS}));")
        self.assertNotIn("<b>", o["h"])
        self.assertNotIn("<i>", o["h"])
        self.assertIn("&lt;i&gt;x", o["h"])
        for t in ("done one", "open <b>&", "busy", "<i>x", "n", "m"):
            self.assertNotIn(t, o["t"])
        self.assertLess(o["h"].index("2026-01-02"), o["h"].index("2026-01-01"))   # newest day first


if __name__ == "__main__":
    unittest.main()
