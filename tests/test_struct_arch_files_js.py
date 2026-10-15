"""84j3 «Files» section of the Architecture module panel (R1-R4): list at the map commit, 200 cap with «+N more», one-line reasons,
escaped paths, stale replies dropped, no view movement and Esc / up chain unchanged."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e
from tests.test_struct_arch_js import PRE, FNS, SEND
from tests.test_struct_arch_detail_js import DET, DET_FNS, CONSTS, MAP, WEB

FL_CONSTS = "\n".join(re.findall(r"^const ARCH_FL\w* = [\s\S]*?;$", DET, re.M))
# Fake fetch: replies queued, resolved by flush(); PRE's paintStruct counts PAINTS.
STUB = """
const CALLS = [], Q = [];
globalThis.fetch = (u) => { CALLS.push(u); return new Promise(res => Q.push(j => res({ json: () => Promise.resolve(j) }))); };
const flush = async j => { Q.splice(0).forEach(f => f(j)); for(let i = 0; i < 5; i++) await Promise.resolve(); };
"""


def run(body, lang="en"):
    pre = PRE if lang == "ko" else PRE.replace("const LANG = 'ko';", "const LANG = 'en';", 1)
    fns = list(dict.fromkeys(FNS + DET_FNS))
    js = "\n".join([pre, CONSTS, FL_CONSTS, "\n".join(js_fn(n) for n in fns), SEND, STUB,
                    "const D = " + json.dumps(MAP) + "; const NAMES = {}; D.modules.forEach(m => { NAMES[m.id] = m.name; });",
                    "(async () => {\n" + body + "\n})().catch(e => { console.error(e); process.exit(1); });"])
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


def ok(n, total, cut=False):
    return {"ok": True, "commit": "c1", "id": "web", "path": "web/", "files": ["web/f%d.js" % i for i in range(n)],
            "total": total, "cut": cut, "why": ""}


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchFiles(unittest.TestCase):
    def test_r1_list_in_panel_after_owns(self):
        r = run("ARCH.cache['/r'] = D; ARCH.sel = {p: '/r', id: 'web'}; const a = archDetHtml(D, 'web', NAMES, {}, {});"
                "await flush(" + json.dumps(ok(3, 3)) + "); const b = archDetHtml(D, 'web', NAMES, {}, {});"
                "console.log(JSON.stringify([a, b, CALLS, PAINTS]));")
        a, b, calls, paints = r
        self.assertIn("Loading files…", a)
        self.assertEqual(calls, ["/api/arch/files?path=%2Fr&id=web"])   # client sends project + module id only
        self.assertEqual(paints, 1)                             # still the selected module -> repaint
        self.assertEqual(re.findall(r"<li title=\"([^\"]+)\">", b), ["web/f0.js", "web/f1.js", "web/f2.js"])
        self.assertLess(b.index("Owns"), b.index("data-arfiles"))
        self.assertLess(b.index("data-arfiles"), b.index("Neighbours"))
        self.assertIn("<small>3</small>", b)

    def test_r2_cap_and_more(self):
        r = run("console.log(JSON.stringify([archFilesHtml(" + json.dumps(ok(200, 250)) + ", false), archFilesHtml("
                + json.dumps(ok(200, 230, True)) + ", false), archFilesHtml(" + json.dumps(ok(200, 200)) + ", false)]));")
        self.assertEqual(r[0].count("<li "), 200)
        self.assertIn("+50 more", r[0])
        self.assertIn("<small>250</small>", r[0])
        self.assertIn("30+ more", r[1])                         # cut: the total is a lower bound
        self.assertIn("<small>230+</small>", r[1])
        self.assertNotIn("more", r[2])

    def test_r3_reasons_one_line(self):
        whys = ["nopath", "ext", "gone", "nomap", "bad", "git", "weird"]
        r = run("console.log(JSON.stringify([" + ",".join("archFilesHtml({ok: false, why: %s}, false)" % json.dumps(w) for w in whys)
                + ", archFilesHtml({ok: false}, false), archFilesHtml(" + json.dumps(ok(0, 0)) + ", false)]));")
        for h in r:
            body = re.findall(r"<div class=archevn>([^<]*)</div>", h)
            self.assertEqual(len(body), 1, h)
            self.assertTrue(body[0].strip())
            self.assertNotIn("<ul", h)
        self.assertEqual(len(set(r[:6])), 6)                   # each server reason has its own line

    def test_r3_local_reasons_no_fetch(self):
        r = run("const m = [{id: 'np', name: 'NP', path: ''}, {id: 'x', name: 'X', path: 'x/', ext: 'pg'}], d = {commit: 'c1', modules: m, edges: []};"
                "ARCH.cache['/r'] = d; ARCH.sel = {p: '/r', id: 'np'};"
                "console.log(JSON.stringify([archDetHtml(d, 'np', {}, {}, {}), archDetHtml(d, 'x', {}, {}, {}), CALLS]));")
        self.assertIn("This module has no path", r[0])
        self.assertIn("External module", r[1])
        self.assertEqual(r[2], [])

    def test_stale_reply_dropped_and_no_refetch(self):
        r = run("ARCH.cache['/r'] = D; ARCH.sel = {p: '/r', id: 'web'}; archFilesKick('/r', 'c1', 'web'); archFilesKick('/r', 'c1', 'web');"
                "const inflight = CALLS.length; await flush(Object.assign(" + json.dumps(ok(1, 1)) + ", {commit: 'c0'}));"
                "const kept = Object.keys(ARCH_FL.c).length, p0 = PAINTS; archFilesKick('/r', 'c1', 'web'); await flush(" + json.dumps(ok(1, 1)) + ");"
                "archFilesKick('/r', 'c1', 'web'); ARCH.sel = {p: '/r', id: 'srv'}; archFilesKick('/r', 'c1', 'srv'); await flush(" + json.dumps(ok(1, 1)) + ");"
                "console.log(JSON.stringify([inflight, kept, p0, CALLS.length, PAINTS]));")
        self.assertEqual(r[0], 1)                               # in flight: no second fetch
        self.assertEqual(r[1:3], [0, 0])                        # other commit: dropped, no repaint
        self.assertEqual(r[3], 3)                               # cached commit: no refetch
        self.assertEqual(r[4], 2)                               # srv reply repaints srv only once

    def test_escape_and_ko(self):
        r = run("console.log(JSON.stringify([archFilesHtml({ok: true, commit: 'c1', files: ['<x>'], total: 1, cut: false, why: ''}, false),"
                " archFilesHtml(null, false), archFilesHtml(null, true)]));", lang="ko")
        self.assertIn("&lt;x&gt;", r[0])
        self.assertNotIn("<x>", r[0])
        self.assertIn("파일", r[0])
        self.assertIn("aria-expanded=false", r[2])
        self.assertNotIn("archevn", r[2])                       # folded: header only

    def test_r4_rows_inert_no_view_movement(self):
        h = run("console.log(JSON.stringify(archFilesHtml(" + json.dumps(ok(5, 5)) + ", false)));")
        for li in re.findall(r"<li[^>]*>", h):
            self.assertNotRegex(li, r"data-ar")
        for bad in ("scrollIntoView", "scrollTo(", "scrollBy(", ".focus("):
            self.assertNotIn(bad, DET)
        self.assertIn("[data-arfiles]", re.search(r"t\.closest\('\[data-arpath\][^']*'\)", DET).group(0))
        self.assertNotIn("data-arfl", h)                        # ⚠84k flow <select data-arfl> lives in the same .archtab
        r = run("const st = {view: 'struct', mode: 'arch', pop: false, pal: false};"
                "console.log(JSON.stringify([archEscOk({key: 'Escape', target: {tagName: 'DIV'}}, st), archUp({sel: 'web', scope: null}, D.modules)]));")
        self.assertEqual(r, [True, {"scope": {"layer": "ui", "group": "front"}}])

    def test_new_literals_have_ko(self):
        with open(os.path.join(WEB, "js", "06-i18n-zt-arch-detail.js"), encoding="utf-8") as fh:
            ko = fh.read()
        with open(os.path.join(WEB, "js", "06-i18n-zz.js"), encoding="utf-8") as fh:
            ko += fh.read()
        lits = set(re.findall(r"T\('([^']+)'\)", DET[DET.index("const ARCH_FL"):DET.index("// Pure: side panel")]))
        lits |= set(re.findall(r"'([^']+)'", re.search(r"const ARCH_FL_WHY = \{[\s\S]*?\};", DET).group(0))) - {"nopath", "ext", "gone", "nomap", "bad", "git"}
        self.assertTrue({"Files", "+{n} more", "{n}+ more"} <= lits)
        for s in lits:
            self.assertIn("'" + s + "':", ko, s)

    def test_css_fits_panel(self):
        with open(os.path.join(WEB, "css", "79b-structure-arch-files.css"), encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn("text-overflow:ellipsis", css)
        self.assertIn("overflow-x:hidden", css)
        self.assertNotRegex(css, r"min-width:\s*[1-9]")


if __name__ == "__main__":
    unittest.main()
