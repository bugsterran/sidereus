"""84m archBriefHtml: structure «Architecture» header «Overview» link to the HEAD commit's brief.html (arch-brief)."""
import json
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_fn
from tests._node import node_e

PRE = "\n".join([
    "let LANG = 'ko';", i18n_prelude("LANG", ("T",)),
    "const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));",
])
C = "a" * 40


def run(expr):
    js = PRE + "\n" + js_fn("archBriefHtml") + "\nprocess.stdout.write(JSON.stringify(" + expr + "));"
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchBriefJs(unittest.TestCase):
    def test_no_brief_is_empty(self):
        out = run("[archBriefHtml({ok: true, brief: null}, '/r'), archBriefHtml({ok: true}, '/r'), archBriefHtml(null, '/r'),"
                  " archBriefHtml({ok: false, brief: {commit: 'c', file: 'f'}}, '/r'), archBriefHtml({ok: true, brief: {commit: 'c', file: 'f'}}, '')]")
        self.assertEqual(out, ["", "", "", "", ""])

    def test_link(self):
        d = {"ok": True, "brief": {"commit": C, "file": "/st/<b>&\"x/brief.html"}}
        h = run("archBriefHtml(" + json.dumps(d) + ", '/my repo/a&b')")
        self.assertIn('href="/api/arch/brief?path=%2Fmy%20repo%2Fa%26b&amp;commit=' + C + '"', h)
        self.assertIn("target=_blank", h)
        self.assertIn('rel="noopener noreferrer"', h)
        self.assertIn("개요", h)
        self.assertIn("/st/&lt;b&gt;&amp;&quot;x/brief.html", h)
        self.assertNotIn("<b>", h)
        self.assertIn("text-overflow:ellipsis", h)


    def test_run_end_refetches(self):
        js = PRE + "\n" + "\n".join(js_fn(n) for n in ("archBriefEnded", "archBriefPoll")) + """
let BRIEFRUN = {}; const ARCH = {cache: {'/a': {}, '/b': {}}, load: {'/b': 1}}, F = [];
function archFetch(p, force){ F.push([p, force]); }
archBriefPoll({'/a': {stage: 'x'}, '/b': {stage: 'y'}, '/c': {stage: 'z'}});
const f0 = F.length;
archBriefPoll({'/b': {stage: 'y'}});
const f1 = F.slice();
archBriefPoll({});   // /b ended but still loading: no double fetch
process.stdout.write(JSON.stringify([f0, f1, F, Object.keys(BRIEFRUN)]));"""
        r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        f0, f1, f, keys = json.loads(r.stdout)
        self.assertEqual(f0, 0)                       # runs starting fetch nothing
        self.assertEqual(f1, [["/a", True]])          # /a ended (cached) -> forced re-fetch; /c ended but never viewed
        self.assertEqual(f, [["/a", True]])
        self.assertEqual(keys, [])


if __name__ == "__main__":
    unittest.main()
