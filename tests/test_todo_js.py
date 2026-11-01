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
        "const sessLabel = x => 'LIVE-' + x.state; const softErr = () => {}; let note = () => {};"
        "const getJSON = () => new Promise(() => {}); let postJSON = () => new Promise(() => {});"
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


def _key(post):
    """Enter in the add box with postJSON = `post`; prints box value, draft and notes after the POST settles."""
    return ("const NOTES = []; note = m => NOTES.push(m); postJSON = " + post + ";"
            "const t = {value: ' buy milk ', classList: {contains: c => c === 'stda'}, getAttribute: () => 'S|/r'};"
            "STODO_DRAFT['S|/r'] = t.value; let n = 0; postJSON = (f => (u, b) => (n++, f(u, b)))(postJSON);"
            "const ev = {key: 'Enter', target: t, preventDefault(){}, stopPropagation(){}};"
            "stodoKeydown(ev); stodoKeydown(ev);"
            "setTimeout(() => console.log(JSON.stringify({v: t.value, d: STODO_DRAFT['S|/r'] || null, n: NOTES, calls: n})), 0);")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TodoAddBox(unittest.TestCase):
    def test_maxlength_follows_server_max(self):
        o = _js("stodoSet({'/r': {o: 1, w: 0, d: 0}}); STODO_OPEN.add('|/r'); const a = stodoLayer({cwd: '/r'});"
                "STODO_DATA['/r'] = {sig: '1,0,0', at: Date.now(), items: [], days: [], max: 120};"
                "console.log(JSON.stringify([a, stodoLayer({cwd: '/r'})]));")
        self.assertIn("maxlength=200 ", o[0])   # before GET answers: the server default
        self.assertIn("maxlength=120 ", o[1])

    def test_failed_post_keeps_text_and_shows_reason(self):
        o = _js(_key("() => Promise.reject(Object.assign(new Error('text too long'), {status: 400}))"))
        self.assertEqual(o["v"], " buy milk ")
        self.assertEqual(o["d"], " buy milk ")
        self.assertEqual(o["n"], ["Could not save the to-do: text too long"])
        self.assertEqual(o["calls"], 1)   # second Enter while in flight does not post again

    def test_saved_post_clears_box(self):
        o = _js(_key("() => Promise.resolve({ok: true})"))
        self.assertEqual([o["v"], o["d"], o["n"]], ["", None, []])


if __name__ == "__main__":
    unittest.main()
