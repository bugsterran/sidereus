"""Diff view (web/js/30-diff.js): splitDiff per-file counts, sbsRows side-by-side pairing and numbering, diffHtml numbering,
inlineMark changed-middle, the review «+» gutter only with rvp AND RVN_SID, dfTree folding, DF_TEST. One node run."""
import json
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_all, js_fn
from tests._node import node_e

BASE = i18n_prelude("'ko'", ("T",)) + r"""
const NL = String.fromCharCode(10);
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const hl = (s, lang) => esc(s);
let RVN_SID = '';
const proseCls = s => /^\s*(```|~~~)/.test(s) ? 'cc' : (/^#{1,6}\s/.test(s) ? 'ck' : '');
"""
FNS = ("dhl", "diffHtml", "gitUnq", "dfHdrPath", "splitDiff", "sbsRows", "inlineMark", "sbsHtml", "pathTree", "dfTree", "dfCount", "rvnGut", "rvnAttr")

DIFF = "\n".join([
    "diff --git a/src/a.py b/src/a.py", "index 1..2 100644", "--- a/src/a.py", "+++ b/src/a.py",
    "@@ -10,4 +10,5 @@ def f():", " keep", "-old1", "-old2", "+new1", "+new2", "+new3", " tail",
    "diff --git a/gone.txt b/gone.txt", "deleted file mode 100644", "--- a/gone.txt", "+++ /dev/null",
    "@@ -1 +0,0 @@", "-bye",
    "diff --git a/lib.jar b/lib.jar", "new file mode 100644", "Binary files /dev/null and b/lib.jar differ",
])


def run(body):
    dft = re.search(r"^const DF_TEST = .*$", js_all(), re.M).group(0)
    src = BASE + dft + "\n" + "\n".join(js_fn(f) for f in FNS) + "\nconst D = " + json.dumps(DIFF) \
        + ";\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));"
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class DiffView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
const files = splitDiff(D);
R.split = files.map(f => [f.path, f.add, f.del, f.isNew, f.isGone, f.isBin]);
R.splitEmpty = splitDiff('  ');
const body = files[0].body;
R.bodyEnd = body.slice(-5);
R.phantom = sbsRows(body + NL).slice(-1)[0];   // a raw trailing newline is ignored too
R.rows = sbsRows(body).map(r => r.hunk ? 'H' : [r.ln, r.lc, r.lt === undefined ? null : r.lt, r.rn, r.rc, r.rt === undefined ? null : r.rt]);
R.addOnly = sbsRows('@@ -1,0 +5,2 @@' + NL + '+a' + NL + '+b').map(r => r.hunk ? 'H' : [r.ln, r.lc, r.rn, r.rc]);
// Unified: one number column; removed lines use the old number, the rest the new one.
const uni = diffHtml(body, 'py');
R.uniNos = [...uni.matchAll(/<td class=xn>(\d*)/g)].map(m => +m[1]);
R.uniMarks = [...uni.matchAll(/<td class=xk>(.)<\/td>/g)].map(m => m[1]).join('');
R.gut = {
  uniNoSid: diffHtml(body, 'py', 'src/a.py'),
  sbsNoSid: sbsHtml(body, 'py', 'src/a.py'),
};
RVN_SID = 's1';
R.gut.uniNoRvp = diffHtml(body, 'py', '');
R.gut.uni = diffHtml(body, 'py', 'src/a.py');
R.gut.sbs = sbsHtml(body, 'py', 'src/a.py');
R.im = inlineMark('x = 1;', 'x = 22;', 'py');
R.imSame = inlineMark('same', 'same', 'py');
R.imNull = inlineMark(null, 'new', 'py');
R.sbsEmpty = sbsHtml('diff --git a/x b/x' + NL + 'Binary files a/x and b/x differ', 'py');   // headers only
R.empty = [sbsHtml('', 'py'), diffHtml('', 'py'), diffHtml(null, 'py'), sbsRows('').length];
const tree = dfTree([{i: 0, f: {path: 'src/main/java/A.java'}}, {i: 1, f: {path: 'src/main/java/B.java'}},
                     {i: 2, f: {path: 'src/test/T.java'}}, {i: 3, f: {path: 'README.md'}}]);
const shape = n => ({l: n.label, f: n.files.map(x => x.name), d: n.dirs.map(shape)});
R.tree = shape(tree);
R.count = dfCount(tree);
R.single = shape(dfTree([{i: 0, f: {path: 'a/b/c/x.py'}}]));
R.test = ['src/test/Foo.java', 'FooTest.java', 'a/foo.test.ts', 'a/foo_spec.rb', 'tests/x.py',
          'IT.java', 'a/FooIT.java'].map(p => DF_TEST.test(p));
R.test.push(...['a/test_foo.py', 'a/foo_test.py', 'a/foo.spec.ts', 'src/Test/X.java'].map(p => DF_TEST.test(p)));
R.testFalse = ['src/main/Contest.java', 'src/latest.py', 'src/app.py', 'EDIT.java', 'a/protest/x.py', 'a/mytest_x.py'].map(p => DF_TEST.test(p));
""")

    def test_split_counts_and_flags(self):
        self.assertEqual(self.R["split"], [["src/a.py", 3, 2, False, False, False],
                                           ["gone.txt", 0, 1, False, True, False],     # +++ /dev/null -> path from diff --git
                                           ["lib.jar", 0, 0, True, False, True]])
        self.assertEqual(self.R["splitEmpty"], [])

    def test_side_by_side_pairing(self):
        self.assertEqual(self.R["rows"], [
            "H",
            [10, "", "keep", 10, "", "keep"],
            [11, "xm", "old1", 11, "xm", "new1"],       # runs of - and + pair row by row
            [12, "xm", "old2", 12, "xm", "new2"],
            [None, "xe", None, 13, "xa", "new3"],       # leftover add: left filler, right numbering continues
            [13, "", "tail", 14, "", "tail"],
        ])
        self.assertEqual(self.R["addOnly"], ["H", [None, "xe", 5, "xa"], [None, "xe", 6, "xa"]])

    def test_unified_numbers(self):
        self.assertEqual(self.R["uniMarks"], " --+++ ")
        self.assertEqual(self.R["uniNos"], [10, 11, 12, 11, 12, 13, 14])

    def test_review_gutter_needs_rvp_and_sid(self):
        g = self.R["gut"]
        for k in ("uniNoSid", "sbsNoSid", "uniNoRvp"):
            self.assertNotIn("rvnb", g[k], k)
            self.assertNotIn("data-rvp", g[k], k)
        self.assertIn('data-rvp="src/a.py"', g["uni"])
        # Unified: every non-removed line gets «+» (5), removed lines (old numbers) never do.
        self.assertEqual(re.findall(r'data-rn="(\d+)"', g["uni"]), ["10", "11", "12", "13", "14"])
        # Side by side: only the right (new) side, and not on the left-only filler rows.
        self.assertEqual(re.findall(r'data-rn="(\d+)"', g["sbs"]), ["10", "11", "12", "13", "14"])
        self.assertEqual(g["sbs"].count("rvnb"), 5)

    def test_inline_mark_middle_only(self):
        self.assertEqual(self.R["im"], {"l": 'x = <span class="wd">1</span>;', "r": 'x = <span class="wa">22</span>;'})
        self.assertEqual(self.R["imSame"], {"l": "same", "r": "same"})
        self.assertEqual(self.R["imNull"], {"l": "", "r": '<span class="wa">new</span>'})
        self.assertIn("표시할 변경이 없습니다", self.R["sbsEmpty"])

    def test_tree_folds_single_child_dirs(self):
        self.assertEqual(self.R["tree"], {"l": "", "f": ["README.md"], "d": [
            {"l": "src", "f": [], "d": [{"l": "main/java", "f": ["A.java", "B.java"], "d": []},
                                        {"l": "test", "f": ["T.java"], "d": []}]}]})
        self.assertEqual(self.R["count"], 4)
        self.assertEqual(self.R["single"], {"l": "a/b/c", "f": ["x.py"], "d": []})

    def test_test_path_rule(self):
        self.assertEqual(self.R["test"], [True] * 11)

    def test_test_rule_word_suffix(self):
        # «test»/«spec» inside a word (Contest.java, latest.py) is not a test file
        self.assertEqual(self.R["testFalse"], [False] * 6)

    def test_no_phantom_trailing_row(self):
        self.assertEqual(self.R["bodyEnd"], " tail")        # no newline kept before the next `diff --git`
        self.assertEqual(self.R["phantom"]["lt"], "tail")

    def test_empty_source_says_no_changes(self):
        e = self.R["empty"]
        for h in e[:3]:
            self.assertIn("표시할 변경이 없습니다", h)
        self.assertEqual(e[3], 0)


@unittest.skipUnless(shutil.which("git"), "git not installed")
class DiffUntracked(unittest.TestCase):
    """git_diff(untr="1"): untracked files as all-added patches for work/b: scopes, capped at DIFF_UNTR_MAX (temp repo)."""
    def setUp(self):
        import os
        import tempfile
        from tests._load import sidereus
        self.gv = gv = sidereus("git_view")
        self.d = d = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d)
        self.addCleanup(setattr, gv, "sessions_rows", gv.sessions_rows)
        gv.sessions_rows = lambda **k: [{"cwd": d, "repos": []}]
        self.git("init", "-q", "-b", "main")
        with open(os.path.join(d, "a.txt"), "w") as fh:
            fh.write("a\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")
        os.makedirs(os.path.join(d, "n"))
        for i in range(gv.DIFF_UNTR_MAX + 5):
            with open(os.path.join(d, "n", "f%02d.txt" % i), "w") as fh:
                fh.write("x%d\n" % i)

    def git(self, *a):
        return subprocess.run(["git", "-C", self.d, "-c", "user.name=t", "-c", "user.email=t@t",
                               "-c", "commit.gpgsign=false"] + list(a), check=True, capture_output=True, text=True).stdout

    def test_untracked_only_when_asked_and_capped(self):
        off = self.gv.git_diff(self.d, "work")
        self.assertTrue(off["ok"])
        self.assertNotIn("n/f00.txt", off["diff"])
        on = self.gv.git_diff(self.d, "work", untr="1")
        self.assertIn("diff --git a/n/f00.txt b/n/f00.txt\nnew file mode 100644\n--- /dev/null\n+++ b/n/f00.txt\n@@ -0,0 +1,1 @@\n+x0\n",
                      on["diff"])
        self.assertEqual(on["diff"].count("new file mode"), self.gv.DIFF_UNTR_MAX)
        self.assertEqual(self.gv.DIFF_UNTR_MAX, 40)

    def test_commit_scopes_ignore_untr(self):
        # (no upstream here: «all» falls back to the working tree, so only a single commit is checked)
        sha = self.git("rev-parse", "HEAD").strip()
        self.assertNotIn("n/f00.txt", self.gv.git_diff(self.d, "c:" + sha, untr="1")["diff"])
        self.assertIn("n/f00.txt", self.gv.git_diff(self.d, "b:" + sha, untr="1")["diff"])


if __name__ == "__main__":
    unittest.main()
