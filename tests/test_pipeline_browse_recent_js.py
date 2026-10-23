"""48f folder picker «Recent session folders» row (R1-R4): rendered only when the server returned entries, escaped, click = plBrLoad(path)."""
import json
import os
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import ROOT
from tests._node import node_e

_F = os.path.join(ROOT, "web", "js", "48f-pipeline-browse.js")
_STUB = """
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[c]);
function lsGet(k, d){ return d; } function lsSet(){}
function agoAt(t){ return 'AGO:' + t; }
const CL = []; const document = {addEventListener(t, f){ if(t === 'click') CL.push(f); }, querySelector(){ return null; }, getElementById(){ return null; }};
"""


def _run(body):
    with open(_F, encoding="utf-8") as f:
        src = _STUB + i18n_prelude("'ko'", ("T", "TV", "U")) + f.read() + "\n" + body
    return json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


_B = {"path": "/h", "home": "/h", "parent": "", "dirs": [], "busy": False}


class RecentRow(unittest.TestCase):
    def test_hidden_when_empty(self):
        """R2: no entries (or missing/garbage) -> no row, no «rec» class."""
        for rec in ([], None, [{"name": "x"}]):
            out = _run("console.log(JSON.stringify(plBrHtml(%s)))" % json.dumps(dict(_B, recent=rec)))
            self.assertNotIn("plbrrec", out)
            self.assertNotIn("최근 세션 폴더", out)

    def test_row_escaped_with_goto_path(self):
        """R1/R4: title (ko), name + path + time; values escaped; data-plbrgo is the path; capped at 8."""
        rec = [{"name": "<img onerror=1>", "path": "/h/<a>\"b", "at": 1700000000, "plat": "claude"},
               {"name": "p2", "path": "/h/p2", "at": "2023-11-14T22:13:20Z"}] + [{"name": "n%d" % i, "path": "/h/n%d" % i, "at": 1} for i in range(9)]
        out = _run("console.log(JSON.stringify(plBrHtml(%s)))" % json.dumps(dict(_B, recent=rec)))
        self.assertIn("최근 세션 폴더", out)
        for bad in ("<img", "<a>", '"b'):
            self.assertNotIn(bad, out)
        self.assertIn('data-plbrgo="/h/&lt;a&gt;&quot;b"', out)
        self.assertIn("&lt;img onerror=1&gt;", out)
        self.assertEqual(out.count("AGO:1700000000"), 2)   # ISO and epoch seconds read the same
        self.assertEqual(out.count("plbrrn"), 8)
        self.assertNotIn("plat", out)
        self.assertIn("plbrbox rec", out)
        self.assertLess(out.index("plbrrec"), out.index("plbrc"))   # above the crumbs

    def test_click_calls_plbrload(self):
        """R3: clicking an entry = plBrLoad(path), the same call as typing the path + Enter."""
        body = """
PLBR = %s; const got = [];
plBrLoad = (p, fb) => { got.push([p, fb]); };
const el = {dataset: {plbrgo: '/h/w x'}};
const ev = {preventDefault(){}, target: {id: '', closest: s => s === '#plbr' || s === '[data-plbrgo]' ? el : null}};
CL.forEach(f => f(ev));
console.log(JSON.stringify(got));
""" % json.dumps(dict(_B, recent=[{"name": "w x", "path": "/h/w x", "at": 1}]))
        self.assertEqual(_run(body), [["/h/w x", False]])

    def test_fetch_failure_no_row(self):
        """R2: a failed ?recent=1 fetch leaves recent empty and paints nothing."""
        body = """
let paints = 0; plBrPaint = () => { paints++; };
globalThis.fetch = () => Promise.reject(new Error('down'));
PLBR = %s;
plBrRecentLoad().then(() => console.log(JSON.stringify([PLBR.recent, paints])));
""" % json.dumps(dict(_B, recent=[]))
        self.assertEqual(_run(body), [[], 0])

    def test_open_fetches_recent_in_parallel(self):
        """R1: plBrOpen fires both requests without awaiting the folder list."""
        body = """
const urls = [];
globalThis.fetch = u => { urls.push(u); return new Promise(() => {}); };
plBrPaint = () => {};
plBrOpen();
console.log(JSON.stringify(urls));
"""
        urls = _run(body)
        self.assertEqual(len(urls), 2)
        self.assertIn("/api/pipelines/projects/dirs?recent=1", urls)


if __name__ == "__main__":
    unittest.main()
