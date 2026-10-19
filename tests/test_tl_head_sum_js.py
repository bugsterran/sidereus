"""Timeline head summary (74b tlHeadHtml): .tlsum span with a plain-text title of the same counts, error first;
CSS basis 200px + ellipsis so the head's line count never follows the text length. Pure functions; no live files."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import ROOT, js_fn
from tests._node import node_e

PRE = r"""
let tlErr = ERR;
const T = s => s, TV = o => o.msg.replace(/\{(\w+)\}/g, (m, k) => String(o.vars[k]));
const U = (n, u) => n + u, fmtTok = n => n + 'T', thc = (a, b) => b, platName = p => p, aiLogo = () => '';
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
"""


def _head(err=None, hidden=0):
    code = PRE.replace("ERR", json.dumps(err)) + js_fn("tlHeadHtml") + (
        "\nconsole.log(JSON.stringify(tlHeadHtml({hours: 6, peak: 3, tok: {sum: 9}}, [{kind: 'a'}, {kind: 'sess'}], %d, '<LG>')));" % hidden)
    r = subprocess.run(node_e(code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class HeadSummary(unittest.TestCase):
    def test_title_is_the_counts(self):
        h = _head(hidden=2)
        self.assertIn('<span class=tlsum title="Last 6h · 1 subagents · peak 3 at once · tokens 9T · 2 off-window sessions hidden">', h)
        self.assertIn("<div class=tlhr><LG></div>", h)

    def test_error_first(self):
        h = _head(err="Could not fetch")
        self.assertIn('title="Could not fetch · Last 6h', h)
        sp = h[h.index("<span class=tlsum"):]
        sp = sp[sp.index(">") + 1:]   # body only, past the title
        self.assertLess(sp.index("Could not fetch · </em>"), sp.index("Last 6h · 1 subagents"))   # the ellipsis cuts the end, never the error

    def test_css_basis(self):
        with open(os.path.join(ROOT, "web", "css", "20-timeline.css"), encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn("#feed .wvh.wvht > .tlsum{flex:1 1 200px;min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}", css)
        with open(os.path.join(ROOT, "web", "css", "21-timeline-plrun.css"), encoding="utf-8") as fh:
            self.assertIn("#feed .wvh.wvht:has(.tlplhb){padding-right:80px}", fh.read())   # «Runs N» slot on every head line


if __name__ == "__main__":
    unittest.main()
