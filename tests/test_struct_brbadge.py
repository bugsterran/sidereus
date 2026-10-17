"""구조 toolbar branch badge (strBrInfo/strBrBadge): page data only, detached, ahead/behind/dirty, escape, non-git."""
import json
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def run(body):
    src = ("const esc = s => String(s).replace(/[&<>\"']/g, c => '&#' + c.charCodeAt(0) + ';');\n"
           "const T = s => s;\n" + js_fn("brNorm") + "\n" + js_fn("strBrRows") + "\n" + js_fn("strBrPick")
           + "\n" + js_fn("strBrInfo") + "\n" + js_fn("strBrBadge")
           + "\n" + body)
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


class Badge(unittest.TestCase):
    def test_info(self):
        out = run(
            "const S = [{cwd: '/w/a', branch: 'old', git: '', ageSec: 90},"
            " {cwd: '/w/a/', branch: 'main', git: '↑2 ~3', ageSec: 5}, {cwd: '/w/n', branch: '', git: ''}];"
            "const BR = {ok: true, cwd: '/private/w/a', head: 'main', detached: false,"
            " branches: [{name: 'main', kind: 'local', upstream: 'origin/main', ahead: 1, behind: 4}]};"
            "const D = {ok: true, cwd: '/w/a', head: 'abcdef1234', detached: true, branches: []};"
            "process.stdout.write(JSON.stringify([strBrInfo('/w/a', S, null), strBrInfo('/w/a', S, BR),"
            " strBrInfo('/w/a', S, D), strBrInfo('/w/n', S, null), strBrInfo('/w/x', S, BR), strBrInfo('', S, null)]));")
        self.assertEqual(out[0], {"name": "main", "sha": "", "ahead": 2, "behind": 0, "dirty": 3})   # most recent row
        self.assertEqual(out[1], {"name": "main", "sha": "", "ahead": 1, "behind": 4, "dirty": 3})   # BR adds behind
        self.assertEqual(out[2]["name"], "")
        self.assertEqual(out[2]["sha"], "abcdef1")
        self.assertIsNone(out[3])                                            # non-git -> no badge
        self.assertIsNone(out[4])                                            # BR of another repo is ignored
        self.assertIsNone(out[5])

    def test_repo_root(self):
        out = run(
            "const S = [{cwd: '/w/r/sub', branch: 'dev', git: '~1', wt: {root: '/w/r'}, repos: ['/w/r']},"
            " {cwd: '/w/o', branch: 'other', git: '', wt: {root: '/w/o'}, repos: ['/w/o', '/w/q']}];"
            "const BR = {ok: true, cwd: '/w/q', head: 'qmain', detached: false, branches: []};"
            "process.stdout.write(JSON.stringify([strBrInfo('/w/r', S, null), strBrInfo('/w/q', S, null),"
            " strBrInfo('/w/q', S, BR)]));")
        self.assertEqual(out[0]["name"], "dev")                              # cwd inside the repo (wt.root)
        self.assertIsNone(out[1])                                            # repos-only: that row's branch is another repo's
        self.assertEqual(out[2]["name"], "qmain")                            # ...but BR for it is used

    def test_html(self):
        out = run(
            "process.stdout.write(JSON.stringify([strBrBadge(null),"
            " strBrBadge({name: 'fix/<x>\"', sha: '', ahead: 2, behind: 1, dirty: 3}),"
            " strBrBadge({name: '', sha: 'abc1234', ahead: 0, behind: 0, dirty: 0}),"
            " strBrBadge({name: '', sha: '', ahead: 0, behind: 0, dirty: 0})]));")
        self.assertEqual(out[0], "")
        self.assertIn("<i class=strbrn>fix/&#60;x&#62;&#34;</i>", out[1])
        self.assertNotIn("<x>", out[1])
        self.assertIn("<small class=strbra>↑2 ↓1</small>", out[1])
        self.assertIn("<small class=strbrd>● 3</small>", out[1])
        self.assertIn("<i class=strbrn>detached @ abc1234</i></em>", out[2])
        self.assertIn(">detached</i></em>", out[3])

    def test_fallback_fetch(self):
        out = run(
            "const S = [{cwd: '/w/a', branch: 'main', git: ''}], calls = [], C = {};"
            "const get = (p, e) => calls.push(p);"
            "const BR = {ok: true, cwd: '/w/b', head: 'bm', detached: false, branches: []};"
            "const r = [];"
            "r.push(strBrPick('/w/a', S, null, C, 0, get));"                 # session row -> no fetch
            "r.push(strBrPick('/w/b', S, BR, C, 0, get) === BR);"            # own BR -> no fetch
            "r.push(strBrPick('/w/x/', S, null, C, 1000, get));"             # fetch #1, nothing yet
            "r.push(strBrPick('/w/x', S, null, C, 2000, get));"              # in flight -> no second fetch
            "C['/w/x'].busy = 0; C['/w/x'].br = {ok: true, cwd: '/w/x', head: 'dev', detached: false,"
            " branches: [{name: 'dev', kind: 'local', upstream: 'o/dev', ahead: 0, behind: 2}]};"
            "r.push(strBrInfo('/w/x', S, strBrPick('/w/x', S, null, C, 30000, get)));"   # cached, fresh
            "C['/w/y'] = {at: 0, br: null, busy: 0};"
            "r.push(strBrPick('/w/y', S, null, C, 50000, get));"             # failure cached < 60 s -> no retry
            "r.push(strBrPick('/w/y', S, null, C, 70000, get));"             # > 60 s -> one retry
            "r.push(strBrPick('', S, null, C, 0, get));"
            "process.stdout.write(JSON.stringify({r, calls}));")
        r = out["r"]
        self.assertIsNone(r[0])
        self.assertTrue(r[1])
        self.assertIsNone(r[2])
        self.assertIsNone(r[3])
        self.assertEqual(r[4], {"name": "dev", "sha": "", "ahead": 0, "behind": 2, "dirty": 0})
        self.assertIsNone(r[5])
        self.assertIsNone(r[6])
        self.assertIsNone(r[7])
        self.assertEqual(out["calls"], ["/w/x/", "/w/y"])                   # one fetch per path, retry after 60 s

    def test_popup_badge(self):
        out = run(js_fn("strTreeBrHtml") + "\n"
            "const SESS = [{cwd: '/w/a', branch: 'main', git: '↑1 ~2'}], BR = null, STR_BRF = {}, got = [];"
            "const strBrGet = (p, e) => got.push(p);"
            "process.stdout.write(JSON.stringify([strTreeBrHtml('/w/a'), strTreeBrHtml('/w/z'), strTreeBrHtml(''),"
            " strBrBadge({name: 'm', sha: '', ahead: 0, behind: 0, dirty: 0}), got]));")
        self.assertIn(" id=spbr ", out[0])                                   # popup id, same markup otherwise
        self.assertIn("<small class=strbrd>● 2</small>", out[0])
        self.assertIn("<small class=strbra>↑1</small>", out[0])
        self.assertEqual(out[1], "")                                         # nothing known yet -> fetch, no badge
        self.assertEqual(out[2], "")
        self.assertIn(" id=strbr ", out[3])                                  # toolbar id unchanged by default
        self.assertEqual(out[4], ["/w/z"])


if __name__ == "__main__":
    unittest.main()
