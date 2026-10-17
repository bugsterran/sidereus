"""Structure source viewer tree (web/js/81b-structure-tree.js): strTreeHtml over the diff popup's dfTree/dfTreeHtml —
names are escaped, locked (sec) entries carry no data-fi, the filter keeps parent dirs; strTreeAdapt field mapping.
One node run; the file list is a fixture (no server, no fetch)."""
import json
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_fn
from tests._node import node_e

FNS = ("ficon", "dicon", "pathTree", "dfTree", "dfCount", "dfTreeHtml", "strTreeDirs", "strTreeHtml", "strTreeAdapt", "strTreeFoldAll")


def run(body):
    src = ("const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'})[c]);\n"
           "const FT = {}, FTL = {}; const thc = (dk, lt) => dk; let diffPick = 0; const dfShut = new Set();\n" + i18n_prelude("'ko'", ("T", "U"))
           + "const STR_TREE_ST = { A: 'A', R: 'A', M: 'M', D: 'D' };\n"
           + "\n".join(js_fn(f) for f in FNS) + "\nconst R = {};\n" + body
           + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


FILES = [
    {"p": "src/app/<img src=x onerror=alert(1)>.py"},
    {"p": "src/app/main.py"},
    {"p": "src/.env", "sec": 1},
    {"p": "docs/deep/nested/readme.md"},
    {"p": "top.txt"},
]


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Tree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
const F = %s;
R.all = strTreeHtml(F, '', 'f:src/app/main.py', 'src/app/main.py');
R.flt = strTreeHtml(F, 'README', '', '');
R.none = strTreeHtml(F, 'zzz', '', '');
R.cur = strTreeHtml(F, '', 'd:src/app', '').html;
R.ad = strTreeAdapt('tree', {ok: true, files: ['a.py', {path: 'b.py', sec: 1, sz: 7}, {p: ''}], truncated: 1});
R.af = strTreeAdapt('file', {ok: false, locked: true});
R.ok = strTreeAdapt('file', {ok: true, code: 'x', n: 3, bytes: 1, enc: 'cp949', masked: 2});
R.st = strTreeAdapt('tree', {ok: true, files: [{p: 'a/n.py', st: 'R'}, {p: 'a/m.py', st: 'M'}, {p: 'g.py', st: 'D'}, {p: 'c.py', st: 'Z'}]});
R.stn = strTreeAdapt('tree', {ok: true, files: [], stn: {A: 2, M: '3', D: 1}}).stn;
R.gone = strTreeAdapt('file', {ok: false, gone: true, msg: 'x'});
R.sth = strTreeHtml(R.st.files, '', '', '').html;
const all = strTreeHtml(F, '', '', '').dirs, openOf = sh => all.filter(d => !sh.has(d));
R.dirs = all;
R.exAll = openOf(strTreeFoldAll(new Set(all), all, true));
R.exFlt = openOf(strTreeFoldAll(new Set(all), strTreeHtml(F, 'readme', '', '').dirs, true));
R.col = openOf(strTreeFoldAll(new Set(), all, false));
""" % json.dumps(FILES))

    def test_names_escaped(self):
        h = self.R["all"]["html"]
        self.assertNotIn("<img", h)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;.py", h)

    def test_locked_has_no_data_fi(self):
        h = self.R["all"]["html"]
        rows = [r for r in h.split("<div ") if ".env" in r]
        self.assertEqual(len(rows), 1)
        self.assertIn("data-lk=1", rows[0])
        self.assertNotIn("data-fi", rows[0])
        self.assertIn("dflk", rows[0])
        self.assertEqual(h.count("data-fi="), 4)       # every other file stays clickable

    def test_open_and_cursor_marks(self):
        h = self.R["all"]["html"]
        row = [r for r in h.split("<div ") if "main.py" in r][0]
        self.assertIn(" on", row.split('"')[1])
        self.assertIn("srtcur", row)
        self.assertNotIn("+0", h)                      # diff counters stripped
        self.assertIn('class="dfd srtcur" data-dir="src/app"', self.R["cur"])

    def test_filter_keeps_parent_dirs(self):
        f = self.R["flt"]
        self.assertEqual(f["paths"], ["docs/deep/nested/readme.md"])
        self.assertIn('data-dir="docs/deep/nested"', f["html"])
        self.assertIn("readme.md", f["html"])
        self.assertNotIn("main.py", f["html"])
        self.assertEqual(self.R["none"]["html"], "")

    def test_git_status(self):
        self.assertEqual([f["st"] for f in self.R["st"]["files"]], ["A", "M", "D", ""])     # R reads as added
        self.assertEqual(self.R["st"]["stn"], {"A": 1, "M": 1, "D": 1})
        self.assertEqual(self.R["stn"], {"A": 2, "M": 3, "D": 1})
        self.assertTrue(self.R["gone"]["gone"])
        h = self.R["sth"]
        self.assertIn('class="dfd srtdc" data-dir="a"', h)
        row = [r for r in h.split("<div ") if "g.py" in r][0]
        self.assertIn("srtD", row)
        self.assertIn("삭제된 파일", row)
        self.assertEqual(len([r for r in h.split("<div ") if "srtA" in r or "srtM" in r]), 2)
        self.assertNotIn("srtdc", [r for r in h.split("<div ") if "c.py" in r][0])

    def test_no_rewrite_of_diff_markup(self):
        # Row marks come from dfTreeHtml's deco hook, never from regexes over the diff tree's rendered HTML.
        src = js_fn("strTreeHtml")
        self.assertIn("dfTreeHtml(root, 0, '', {", src)
        self.assertNotIn(".replace(/class=", src)
        h = run("R.h = strTreeHtml([{p: 'a&b/x.py', st: 'M'}], '', 'd:a&b', '').html;")["h"]
        self.assertIn('class="dfd srtcur srtdc" data-dir="a&amp;b"', h)   # raw dir key, escaped attribute

    def test_fold_all(self):
        self.assertEqual(self.R["exAll"], self.R["dirs"])            # expand-all opens every dir
        self.assertTrue(self.R["exFlt"])
        self.assertTrue(all(d.startswith("docs") for d in self.R["exFlt"]))   # filter: only dirs holding matches
        self.assertNotIn("src", self.R["exFlt"])
        self.assertEqual(self.R["col"], [])                          # collapse-all shuts all

    def test_adapter(self):
        self.assertEqual(self.R["ad"]["files"], [{"p": "a.py", "sec": 0, "bytes": 0, "st": ""}, {"p": "b.py", "sec": 1, "bytes": 7, "st": ""}])
        self.assertTrue(self.R["ad"]["truncated"])
        self.assertTrue(self.R["af"]["locked"])
        self.assertFalse(self.R["af"]["ok"])
        self.assertEqual((self.R["ok"]["text"], self.R["ok"]["lines"], self.R["ok"]["enc"], self.R["ok"]["masked"]), ("x", 3, "cp949", 2))
        self.assertEqual(self.R["ok"]["note"], "")


if __name__ == "__main__":
    unittest.main()
