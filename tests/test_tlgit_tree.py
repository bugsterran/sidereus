"""Timeline git rail tree builder (web/js/77-timeline-git.js): per-folder sums, chain merge, status mapping."""
import json
import re
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_all, js_fn
from tests._node import node_e


def run(body):
    src = "\n".join(js_fn(n) for n in ("pathTree", "tlgSt", "tlgTree")) + "\n" + body
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


FILES = [{"path": "web/js/a.js", "st": "M", "add": 3, "del": 1},
         {"path": "web/js/b.js", "st": "A", "add": 10, "del": 0},
         {"path": "web/css/x.css", "st": "D", "add": 0, "del": 7},
         {"path": "sidereus/deep/one/y.py", "st": "R", "add": 2, "del": 2, "old": "sidereus/x.py"},
         {"path": "README", "st": "T", "add": 1, "del": 0},
         {"path": "img.png", "st": "M", "add": 0, "del": 0, "bin": True}]


class Tree(unittest.TestCase):
    def test_sums_and_shape(self):
        t = run("const t = tlgTree(%s); const s = n => ({name: n.name, path: n.path, add: n.add, del: n.del, n: n.n,"
                " files: n.files.map(f => f.name + ':' + f.st), dirs: n.dirs.map(s)});"
                " process.stdout.write(JSON.stringify(s(t)));" % json.dumps(FILES))
        self.assertEqual((t["add"], t["del"], t["n"]), (16, 10, 6))
        self.assertEqual(t["files"], ["README:M", "img.png:M"])            # typechange T -> modified
        sidereus, web = t["dirs"]
        self.assertEqual((sidereus["name"], sidereus["path"]), ("sidereus/deep/one", "sidereus/deep/one"))   # chain merged
        self.assertEqual(sidereus["files"], ["y.py:R"])
        self.assertEqual((web["add"], web["del"], web["n"]), (13, 8, 3))
        self.assertEqual([d["name"] for d in web["dirs"]], ["css", "js"])
        self.assertEqual((web["dirs"][1]["add"], web["dirs"][1]["del"]), (13, 1))

    def test_status_map(self):
        out = run("process.stdout.write(JSON.stringify(['A','M','D','R','U','T','?'].map(s => tlgSt(s).k + tlgSt(s).cls + tlgSt(s).en)));")
        self.assertEqual(out, ["Aaadded", "Mmmodified", "Dddeleted", "Rrrenamed", "Uuunmerged", "Mmmodified", "Mmmodified"])

    def test_file_type_icons(self):
        src = js_all()
        tabs = "\n".join(re.search(r"^const %s = .*?;$" % n, src, re.S | re.M).group(0)
                         for n in ("FI_EXT", "FI_NAME", "FI_S", "FI_TILE", "FI_TX", "FI_PAGE", "FI_ATOM", "FI_SVG"))
        tabs += "\n" + js_fn("fileIcoKey") + "\n" + js_fn("fileIco") + "\n"
        names = ["a.py", "b.JS", "c.tsx", "d.jsx", "e.ts", "i.html", "s.css", "M.java", "k.kt", "m.go", "r.rs",
                 "n.md", "p.json", "c.yaml", "x.toml", "x.sh", "q.sql", "t.txt", "Dockerfile", "Makefile", "README",
                 "README.md", "readme.txt", ".gitignore", "img.png", "yarn.lock", "package-lock.json", "web/js/a.mjs",
                 ".env", "noext", "archive.tar.gz"]
        r = subprocess.run(node_e(tabs + "const ns = %s; process.stdout.write(JSON.stringify({k: ns.map(fileIcoKey),"
                            " miss: Object.keys(FI_SVG).length && [...Object.values(FI_EXT), ...Object.values(FI_NAME),"
                            " 'readme', 'file'].filter(k => !FI_SVG[k]), svg: ns.every(n => /<svg[^>]*>.+<\\/svg><\\/i>$/.test(fileIco(n)))}));"
                            % json.dumps(names)),
                           capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["k"],
                         ["py", "js", "tsx", "jsx", "ts", "html", "css", "java", "kt", "go", "rs", "md", "json",
                          "config", "config", "sh", "sql", "txt", "docker", "make", "readme", "readme", "readme", "git",
                          "image", "lock", "lock", "js", "config",
                          "file", "file"])                               # no ext / unknown ext -> generic file glyph
        self.assertEqual(out["miss"], [])                                # every key has a glyph
        self.assertTrue(out["svg"])

    def test_fold_all(self):
        pre = ("const tlgShut = new Set(); const T = s => s, esc = s => String(s);\n"
               + js_fn("tlgFoldAll") + "\n" + js_fn("tlgFoldBtns") + "\n")
        out = run(pre + "const F = tlgTree(%s); tlgShut.add('other\\0x');"
                  " const n = tlgFoldAll(F, 'r', false); const shut = [...tlgShut].sort();"
                  " tlgFoldAll(F, 'r', true);"
                  " process.stdout.write(JSON.stringify({n, shut, after: [...tlgShut], btn: tlgFoldBtns(F),"
                  " flat: tlgFoldBtns(tlgTree([{path: 'a.py', st: 'M'}]))}));" % json.dumps(FILES))
        self.assertEqual(out["n"], 2)
        self.assertEqual(out["shut"], ["other\0x", "r\0sidereus/deep/one", "r\0web", "r\0web/css", "r\0web/js"])  # nested too
        self.assertEqual(out["after"], ["other\0x"])                     # other repos untouched
        self.assertIn("data-tga=1>Expand all", out["btn"])
        self.assertIn("data-tga=0>Collapse all", out["btn"])
        self.assertEqual(out["flat"], "")                               # no folders -> no buttons

    def test_paint_builds_tree_once(self):
        # tlgHtml with stubbed helpers: one tlgTree per file list; repaints and fold-all reuse it, a new list or tlgUntr rebuilds.
        pre = (i18n_prelude("'ko'") + "let tlgTreeMemo = null; const tlgShut = new Set(); let tlgUntr = false; const TLG_KB = '', LBL = {}, TLG_MODES = [];"
               " const esc = s => String(s), tlgShownMode = () => 'head', tlgRepoOrder = r => r,"
               " tlgBaseHtml = () => '', tlgUntrHtml = () => '', fileIco = () => '', tlgOwnHtml = () => '';"
               " const F = %s.concat([{path: 'web/new.txt', st: 'A', new: true}]);"
               " const tlgC = {k: {d: {ok: true, files: F, n: F.length}}};"
               " const tlgTarget = () => ({cwd: '/r', repo: '/r', row: {cwd: '/r'}, how: 'auto', all: [], key: 'k', repos: ['/r'], ck: 'k'});\n"
               % json.dumps(FILES)
               + "\n".join(js_fn(n) for n in ("tlgShown", "tlgShownTree", "tlgFoldBtns", "tlgFoldAll", "tlgTreeHtml",
                                              "tlgHtml", "tlgMid", "tlgNum", "tlgShownN", "tlgRepoChips")) + "\n")
        out = run(pre + "let cnt = 0; const _t = tlgTree; tlgTree = (...a) => (cnt++, _t(...a));"
                  " const h1 = tlgHtml(); const one = cnt; tlgFoldAll(tlgShownTree(F), '/r', false); const h2 = tlgHtml();"
                  " const reuse = cnt; tlgC.k.d = {ok: true, files: F.slice(), n: F.length}; tlgHtml(); const fresh = cnt;"
                  " tlgUntr = true; tlgShut.clear(); const h3 = tlgHtml();"
                  " process.stdout.write(JSON.stringify({one, reuse, fresh, all: cnt, btn: h1.includes('data-tga=1'),"
                  " shut: h2.includes('▸') && !h2.includes('▾'), rows: (h1.match(/data-tgf=/g) || []).length,"
                  " rowsU: (h3.match(/data-tgf=/g) || []).length}));")
        self.assertEqual((out["one"], out["reuse"], out["fresh"], out["all"]), (1, 1, 2, 3))
        self.assertTrue(out["btn"])
        self.assertTrue(out["shut"])                                    # fold-all on the cached tree still folds every dir
        self.assertEqual((out["rows"], out["rowsU"]), (6, 7))           # untracked toggle rebuilds with the hidden file

    def test_empty(self):
        t = run("process.stdout.write(JSON.stringify(tlgTree([])));")
        self.assertEqual((t["n"], t["dirs"], t["files"]), (0, [], []))


class SharedBuilder(unittest.TestCase):
    def test_callers_agree(self):
        # dfTree · tlgTree both go through pathTree: same folders and merged chains, only order/shape differ.
        paths = ["src/main/java/A.java", "src/main/java/B.java", "src/test/T.java", "a-c/x", "a/b/y", "a/b/z", "README"]
        src = "\n".join(js_fn(n) for n in ("pathTree", "tlgSt", "tlgTree", "dfTree")) + """
const P = %s, norm = (n, nm, kid, leaf) => [n[nm], n.dirs.map(d => norm(d, nm, kid, leaf)).sort(), n[kid].map(leaf).sort()];
process.stdout.write(JSON.stringify({
  df: norm(dfTree(P.map((p, i) => ({i, f: {path: p}}))), 'label', 'files', f => f.name),
  tlg: norm(tlgTree(P.map(p => ({path: p}))), 'name', 'files', f => f.name),
  tlgOrder: tlgTree(P.map(p => ({path: p}))).dirs.map(d => d.name)}));""" % json.dumps(paths)
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["df"], out["tlg"])
        self.assertIn(["main/java", [], ["A.java", "B.java"]], out["df"][1][2][1])     # src → main/java chain merged
        self.assertEqual(out["tlgOrder"], ["a/b", "a-c", "src"])    # 'seg': by own segment before merging («a» < «a-c»)


if __name__ == "__main__":
    unittest.main()
