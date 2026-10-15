"""Timeline git rail untracked filter (web/js/77-timeline-git.js): hidden by default, checkbox, hidden count, no fetch."""
import json
import re
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

FILES = [{"path": "a.py", "st": "M"}, {"path": "scratch/x.txt", "st": "A", "new": True},
         {"path": "<b>.tmp", "st": "A", "new": True}, {"path": "b.js", "st": "A"}]


def run(body, ls=""):
    init = re.search(r"^let tlgUntr = .*$", js_all(), re.M).group(0)
    src = ("const UIS_ = {'sidereus.tlgUntr': %s}; const sets = [], calls = {fetch: 0, paint: 0};\n"
           "function lsGet(k, d){ return k in UIS_ ? UIS_[k] : d; } function lsSet(k, v){ sets.push([k, v]); }\n"
           "function getJSON(){ calls.fetch++; return Promise.resolve({}); } function tlgPaint(){ calls.paint++; }\n"
           "function T(s){ return s; } const TLG_KB = ' data-kb';\n"
           "function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;'); }\n"
           % json.dumps(ls)) + init + "\n" + "\n".join(js_fn(n) for n in ("tlgShown", "tlgUntrHtml", "tlgUntrSet")) + "\n" + body
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


class Untracked(unittest.TestCase):
    def test_hidden_by_default_with_count(self):
        o = run("process.stdout.write(JSON.stringify({p: tlgShown(%s).map(f => f.path), h: tlgUntrHtml(%s)}));"
                % (json.dumps(FILES), json.dumps(FILES)))
        self.assertEqual(o["p"], ["a.py", "b.js"])
        self.assertIn("2 untracked hidden", o["h"])
        self.assertIn("data-tgu", o["h"])
        self.assertNotIn(" checked", o["h"])

    def test_checkbox_on_shows_all(self):
        o = run("process.stdout.write(JSON.stringify({p: tlgShown(%s).length, h: tlgUntrHtml(%s)}));"
                % (json.dumps(FILES), json.dumps(FILES)), ls="1")
        self.assertEqual(o["p"], 4)
        self.assertIn(" checked", o["h"])
        self.assertNotIn("data-tgu", o["h"])

    def test_no_hidden_text_without_untracked(self):
        o = run("process.stdout.write(JSON.stringify(tlgUntrHtml([{path: 'a', st: 'M'}])));")
        self.assertNotIn("data-tgu", o)

    def test_hidden_text_escaped(self):
        o = run("T = s => s === '{n} untracked hidden' ? '<i>{n}</i>' : s;"
                "process.stdout.write(JSON.stringify(tlgUntrHtml(%s)));" % json.dumps(FILES))
        self.assertIn("&lt;i&gt;2&lt;/i&gt;", o)
        self.assertNotIn("<i>2", o)

    def test_toggle_repaints_without_fetch(self):
        o = run("tlgUntrSet(true); const a = tlgShown(%s).length; tlgUntrSet(false);"
                "process.stdout.write(JSON.stringify({a, b: tlgShown(%s).length, sets, calls}));"
                % (json.dumps(FILES), json.dumps(FILES)))
        self.assertEqual((o["a"], o["b"]), (4, 2))
        self.assertEqual(o["sets"], [["sidereus.tlgUntr", "1"], ["sidereus.tlgUntr", "0"]])
        self.assertEqual(o["calls"], {"fetch": 0, "paint": 2})


if __name__ == "__main__":
    unittest.main()
