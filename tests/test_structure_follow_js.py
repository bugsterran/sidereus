"""Source viewer folding, markdown preview and back/forward (web/js/81c-structure-fold.js, 81d-structure-follow.js,
00-core.js md/mdLinks). One node run over fixtures — no server, no fetch."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

FNS = ("codeBlock", "mdLinks", "md", "strFoldKind", "strIsMd", "strFoldRanges", "strFoldHidden", "strFoldReveal",
       "strSrcTable", "strMdBody", "strMdBtns", "strMdRel", "strSrcDeclLine",
       "strNavPush", "strNavMove", "strSplitGet", "strSplitCols", "strSplitDecl", "strSplitStyle", "strSplitGrip")

PRE = (r"""const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const NL = String.fromCharCode(10);
const inline = s => esc(s).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
function hl(s){ return esc(s).replace(/\b([A-Z]\w*)\b/g, '<span class=ct>$1</span>'); }
function T(s){ return s; } function KE(k, e){ return k; }
const STR_FOLD_BRACE = {java: 1, ts: 1}, STR_FOLD_INDENT = {py: 1, yaml: 1, yml: 1}; let strTreeMdv = 'split';
const STR_SPLIT_MIN = 0.15, STR_SPLIT_PX = {srt: 140}, STR_SPLIT_RPX = {archbody: 240}, LS = {}; function lsGet(k, d){ return k in LS ? LS[k] : d; }
""")

# md() output before the doc flag existed — callers without it must stay byte-identical.
MD_SRC = ("# T <b>\n\n- a **b** `c<d>`\n1. x [l](http://e.x) ![i](http://i/x.png)\n\n| h | k |\n|---|---|\n| <i> | 2 |\n\n"
          "```js\nvar a = '<s>';\n```\n---\nplain & text <script>alert(1)</script>\n## sub")
MD_PIN = ("<h3>T &lt;b&gt;</h3><ul><li>a <strong>b</strong> <code>c&lt;d&gt;</code></li><li>x [l](http://e.x) ![i](http://i/x.png)"
          "</li></ul><table><thead><tr><th>h</th><th>k</th></tr></thead><tbody><tr><td>&lt;i&gt;</td><td>2</td></tr></tbody></table>"
          "<pre class=cb><span class=cl>js</span><code>var a = &#39;&lt;s&gt;&#39;;</code></pre><hr>"
          "<p>plain &amp; text &lt;script&gt;alert(1)&lt;/script&gt;</p><h3>sub</h3>")
# md(src, 1) before code spans were allowed in link text (the mermaid change) — only [`x`](u) may differ.
MD_PIN_DOC = ("<h1>T &lt;b&gt;</h1><ul><li>a <strong>b</strong> <code>c&lt;d&gt;</code></li><li>x <a href=\"http://e.x\" target=_blank "
              "rel=\"noopener noreferrer\">l</a> <span class=mdimg>i</span></li></ul><table><thead><tr><th>h</th><th>k</th></tr></thead>"
              "<tbody><tr><td>&lt;i&gt;</td><td>2</td></tr></tbody></table><pre class=cb><span class=cl>js</span><code>var a = &#39;&lt;s&gt;"
              "&#39;;</code></pre><hr><p>plain &amp; text &lt;script&gt;alert(1)&lt;/script&gt;</p><h2>sub</h2>")
XSS = ("# Hi\n<script>alert(1)</script>\n<img src=x onerror=alert(1)>\n[a](javascript:alert`1`)\n[b](JavaScript:x)\n"
       "[c](data:text/html,x)\n[d](//evil.example/x)\n![e](http://img.example/p.png)\n[f](https://ok.example/?a=1&b=\"q)\n"
       "[g](docs/x.md#top)\n`[h](http://in.code)`")
JAVA = ("package a;\n\npublic class A {\n  void f() {\n    if (x) {\n      y();\n    } else {\n      z();\n    }\n  }\n"
        "  String s = \"{\";\n}\nvoid g() {\n}\n")
YAML = "server:\n  port: 8080\n  ssl:\n    enabled: true\n    # c\n    key: x\nspring:\n  a: 1\n"


def run(body):
    src = PRE + "\n".join(js_fn(f) for f in FNS) + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));"
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Follow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
const J = %s, Y = %s;
R.fj = strFoldRanges(J, strFoldKind('A.java'));
R.fy = strFoldRanges(Y, strFoldKind('c/app.yml'));
R.kind = [strFoldKind('x.md'), strFoldKind('a.py'), strFoldKind('b.ts')];
const sh = new Set([2, 3, 4]);
R.hid = strFoldHidden(R.fj, new Set([2]), 15).map((h, i) => h ? i : -1).filter(i => i >= 0);
strFoldReveal(R.fj, sh, 5); R.rev = Array.from(sh);
R.pin = md(%s);
R.pind = md(%s, 1);
R.xss = md(%s, 1);
R.body = strMdBody('# a <b>', '<table></table>', 'split');
LS['sidereus.srmds'] = '0.3'; R.split = [strMdBody('x', '', 'split'), strSplitStyle('strsp')];
LS['sidereus.strsp'] = '0.99'; R.split.push(strSplitStyle('strsp'));
R.srt = [strSplitStyle('srt')]; LS['sidereus.srt'] = '90'; R.srt.push(strSplitStyle('srt'));
LS['sidereus.srt'] = '312.4'; R.srt.push(strSplitStyle('srt'));
R.arb = [strSplitStyle('archbody')]; LS['sidereus.archbody'] = '200'; R.arb.push(strSplitStyle('archbody')); LS['sidereus.archbody'] = '420.6'; R.arb.push(strSplitStyle('archbody'));
R.rel = [strMdRel('docs/a.md', '../README.md'), strMdRel('a.md', '../../x'), strMdRel('d/a.md', '#top')];
R.tbl = strSrcTable("import z from './<b>';\nRepo r = new Nope();", 'js', [[0, 1]]);
R.decl = [strSrcDeclLine('x\n  public interface Repo {', 'Repo'), strSrcDeclLine('class Repox', 'Repo'), strSrcDeclLine('a', 'a(b')];
const h = {b: [], f: []};
strNavPush(h, {file: 'a', line: 1}); strNavPush(h, {file: 'b', line: 0}); strNavPush(h, {file: 'b', line: 0});
R.h1 = h.b.length;
R.back = strNavMove(h, {file: 'c', line: 9}, -1);
R.fwd = strNavMove(h, {file: 'b', line: 0}, 1);
R.none = strNavMove({b: [], f: []}, {file: 'c'}, -1);
strNavMove(h, {file: 'c', line: 9}, -1); strNavPush(h, {file: 'b', line: 0}); R.fcut = h.f.length;
""" % (json.dumps(JAVA), json.dumps(YAML), json.dumps(MD_SRC), json.dumps(MD_SRC), json.dumps(XSS)))

    def test_fold_java(self):
        self.assertEqual(self.R["fj"], [[2, 10], [3, 8], [4, 5], [6, 7]])    # class, f, if, else; "{" in a string ignored
        self.assertEqual(self.R["hid"], list(range(3, 11)))

    def test_fold_yaml(self):
        self.assertEqual(self.R["fy"], [[0, 5], [2, 5]])                     # 2-line «spring» block does not fold
        self.assertEqual(self.R["kind"], ["", "indent", "brace"])

    def test_reveal_unfolds_ancestors(self):
        self.assertEqual(self.R["rev"], [])                                  # row 5 sits inside 2, 3 and 4

    def test_md_unchanged_without_doc(self):
        self.assertEqual(self.R["pin"], MD_PIN)
        self.assertEqual(self.R["pind"], MD_PIN_DOC)

    def test_md_preview_safe(self):
        h = self.R["xss"]
        for bad in ("<script", "<img", "javascript:alert`1`\"", "href=\"javascript", "href=\"JavaScript", "href=\"data:",
                    "href=\"//", "onerror=alert(1)>", "\"q"):
            self.assertNotIn(bad, h)
        self.assertIn("&lt;script&gt;", h)
        self.assertIn('<a href="https://ok.example/?a=1&amp;b=&quot;q" target=_blank rel="noopener noreferrer">f</a>', h)
        self.assertIn('<span class=mdimg>e</span>', h)
        self.assertIn('<a class=mdrel data-mdrel="docs/x.md#top">g</a>', h)
        self.assertIn('<code>[h](http://in.code)</code>', h)
        self.assertIn("<h1>Hi</h1>", h)
        self.assertIn("<h1>a &lt;b&gt;</h1>", self.R["body"])
        self.assertEqual(self.R["rel"], ["README.md", None, None])

    def test_split_grip(self):
        d, sv = self.R["body"], self.R["split"]
        self.assertTrue(d.startswith("<div class=srmds><div class=srmdc>"))   # no key -> CSS default 1fr 1fr
        self.assertIn("<i class=strspg data-spk=srmds", d)
        self.assertIn('<div class=srmds style="grid-template-columns:0.3000fr 0.7000fr">', sv[0])
        self.assertEqual(sv[1:], ["", ""])                                  # unset and out-of-range -> default
        # tree | code: px width, below 140 ignored, capped at 60% by CSS min()
        self.assertEqual(self.R["srt"], ["", "", ' style="grid-template-columns:min(312px,60%) 1fr"'])
        # arch map | Edges: right pane px width, below 240 ignored, capped at 60% so the map keeps room
        self.assertEqual(self.R["arb"], ["", "", ' style="--spw:421px"'])

    def test_table_escaped(self):
        t = self.R["tbl"]
        self.assertNotIn("<b>.ts", t)
        self.assertIn("<span class=ct>Repo</span>", t)                       # names are plain text (no following)
        self.assertNotIn("data-sym", t)
        self.assertIn('data-fs="0"', t)
        self.assertEqual(self.R["decl"], [2, 0, 0])

    def test_history(self):
        self.assertEqual(self.R["h1"], 2)                                    # repeated entry not stacked
        self.assertEqual(self.R["back"], {"file": "b", "line": 0})
        self.assertEqual(self.R["fwd"], {"file": "c", "line": 9})
        self.assertIsNone(self.R["none"])
        self.assertEqual(self.R["fcut"], 0)                                  # a new jump drops the forward stack


if __name__ == "__main__":
    unittest.main()
