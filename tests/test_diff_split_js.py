"""Diff window file list (web/js/30-diff.js splitDiff/dfFiles) vs `git show --stat -M` on a temp repo commit with
renames-with-spaces, a Korean-named rename, a pure rename and binaries; full-file expand of a rename (git_view)."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from tests._i18n_js import i18n_switch
from tests._load import sidereus, js_all, js_fn
from tests._node import node_e

gv = sidereus("git_view")
gi = sidereus("gitinfo")

FNS = ("gitUnq", "dfHdrPath", "splitDiff", "dfFiles")


@unittest.skipUnless(shutil.which("node") and shutil.which("git"), "node/git not installed")
class DiffSplit(unittest.TestCase):
    def setUp(self):
        self.d = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d)
        self._sess = gv.sessions_rows
        gv.sessions_rows = lambda **k: [{"cwd": self.d, "repos": []}]
        self.addCleanup(setattr, gv, "sessions_rows", self._sess)
        self.git("init", "-q", "-b", "main")
        body = "".join("line %d\n" % i for i in range(20))
        self.put("old name.txt", body)
        self.put("가.txt", body)
        self.put("p.txt", "pure\n")
        self.put("sp ace.sql", "-- keep\n-- drop\n")
        self.put("img.bin", b"\0\1\2" * 50)
        self.git("add", "-A")
        self.git("commit", "-qm", "init")
        self.git("mv", "old name.txt", "new name.txt")
        self.put("new name.txt", body + "added\n")
        self.git("mv", "가.txt", "나 다.txt")
        self.put("나 다.txt", body.replace("line 3\n", "line three\n"))
        self.git("mv", "p.txt", "q.txt")
        self.put("sp ace.sql", "-- keep\n")
        self.put("img.bin", b"\0\3\2" * 60)
        self.put("new.bin", b"\0\9" * 10)
        self.git("add", "-A")
        self.git("commit", "-qm", "renames")
        self.sha = self.git("rev-parse", "HEAD").strip()

    def put(self, name, data):
        with open(os.path.join(self.d, name), "wb") as fh:
            fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))

    def git(self, *a):
        return subprocess.run(["git", "-C", self.d, "-c", "user.name=t", "-c", "user.email=t@t",
                               "-c", "commit.gpgsign=false"] + list(a),
                              check=True, capture_output=True, text=True).stdout

    def node(self, d):
        src = "const NL = String.fromCharCode(10); const T = s => s;\n" + "\n".join(js_fn(f) for f in FNS) \
            + "\nconst d = " + json.dumps(d) + ";\nconst f = dfFiles(d), p = splitDiff(d.diff);\n" \
            + "process.stdout.write(JSON.stringify({files: f.map(x => [x.path, x.add, x.del, x.cut || '']),\n" \
            + "  split: p.map(x => [x.path, x.add, x.del, x.isBin])}));"
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        return json.loads(r.stdout)

    def test_matches_git_stat(self):
        d = gv.git_diff(self.d, scope="c:" + self.sha)
        self.assertTrue(d["ok"], d)
        self.assertEqual(d["scope"], "")
        self.assertTrue(d["scopeCommit"].startswith(self.sha[:7]), d["scopeCommit"])
        R = self.node(d)
        stat = self.git("show", "-M", "--stat", "--format=", self.sha)
        m = re.search(r"(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?)?", stat)
        self.assertEqual(len(R["files"]), int(m.group(1)))
        self.assertEqual(sum(f[1] for f in R["files"]), int(m.group(2) or 0))
        self.assertEqual(sum(f[2] for f in R["files"]), int(m.group(3) or 0))
        self.assertEqual(sorted(f[0] for f in R["files"]),
                         sorted(["new name.txt", "나 다.txt", "q.txt", "sp ace.sql", "img.bin", "new.bin"]))
        self.assertEqual([f[3] for f in R["files"]], [""] * 6)          # no false «패치 생략»
        # The patch alone (no numstat) already yields the same paths and line counts.
        nst = {s["path"]: s for s in d["numstat"]}
        self.assertEqual(sorted(p[0] for p in R["split"]), sorted(nst))
        for path, add, dele, _b in R["split"]:
            self.assertEqual((add, dele), (nst[path]["add"], nst[path]["del"]), path)

    def test_quoted_header_path(self):
        R = self.node({"diff": 'diff --git "a/x\\"y" "b/x\\"y"\nindex 1..2\n--- "a/x\\"y"\n+++ "b/x\\"y"\n@@ -1 +1 @@\n-a\n+b\n'
                               + 'diff --git "a/\\352\\260\\200" "b/\\352\\260\\200"\nBinary files differ\n'})
        self.assertEqual([p[0] for p in R["split"]], ['x"y', "가"])

    def test_full_expand_of_rename(self):
        f = gv.git_file_diff(self.d, "new name.txt", "c:" + self.sha)
        self.assertTrue(f["ok"], f)
        self.assertIn("rename from old name.txt", f["diff"])
        self.assertEqual(sum(1 for ln in f["diff"].split("\n") if ln.startswith("+") and not ln.startswith("+++")), 1)

    def test_scope_labels_follow_language(self):
        base = self.git("rev-parse", "HEAD~1").strip()
        d = gv.git_diff(self.d, scope="b:" + base)
        self.assertTrue(d["ok"], d)
        self.assertEqual(d["scopeBase"], base[:7])
        w = gv.git_diff(self.d, scope="work")
        self.assertEqual((w["scope"], w["scopeBase"]), ("Working tree (uncommitted)", ""))
        # Client header: base label built with KE, fixed labels through T() + I18N.ko (no Korean left in en).
        ko = re.search(r"Object\.assign\(I18N\.ko, \{\n  'Unpushed \+ working tree'[\s\S]*?\}\);", js_all()).group(0)
        src = ("let LANG = 'en';\n" + i18n_switch(("T", "TV")) +   # real dictionaries; the server scope may still be Korean (bridge)
               "const hd = d => d.scopeBase ? TV({msg: 'Since {n}', vars: {n: d.scopeBase}}) : T(d.scope);\n"
               "const r = [hd(" + json.dumps(d) + "), hd(" + json.dumps(w) + ")];\n"
               "LANG = 'ko'; r.push(hd(" + json.dumps(d) + "));\nprocess.stdout.write(JSON.stringify(r));")
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), ["Since " + base[:7], "Working tree (uncommitted)", "기준 " + base[:7] + " 이후"])
        body = js_fn("diffBody")
        self.assertIn("TV({msg: 'Since {n}', vars: {n: d.scopeBase}})", body)
        self.assertIn("head.push(T(d.scope))", body)
        for k in gv.DIFF_SCOPES.values():
            self.assertIn("'" + k + "':", ko)   # server scopes are English keys of I18N.ko

    def test_quote_path_off(self):
        self.assertIn("core.quotePath=false", gi.GIT_SAFE_OPTS)


if __name__ == "__main__":
    unittest.main()
