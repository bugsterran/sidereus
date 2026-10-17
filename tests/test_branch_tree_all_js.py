"""Branch tree «모두 펼치기/접기» (web/js/89-branch-worktree.js brTreeAll) and treeitem roles, run through node."""
import json
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_all
from tests._node import node_e


def _fn(src, name):
    return re.search(r"^function " + name + r"\(.*?^}", src, re.S | re.M).group(0)


BL = [{"name": "main", "kind": "local", "upstream": "", "ts": 1, "sha": "a1"},
      {"name": "fix/a/b", "kind": "local", "upstream": "", "ts": 1, "sha": "a2"},
      {"name": "origin/x", "kind": "remote", "upstream": "", "ts": 1, "sha": "a3"}]


def _run(tail):
    src = js_all()
    js = "\n".join([
        i18n_prelude("'ko'", ("T", "KE", "U", "TV")), "const esc = s => String(s), agoAt = () => '', brSgHtml = () => '', lsSetJson = () => {};",
        "let brMerge = true, brTreeSt = {}, brTreeFor = 'r', brRepo = 'r', brSel = '', painted = 0, foc = '';",
        "let BR = " + json.dumps({"ok": True, "head": "main", "detached": False, "branches": BL, "worktrees": []}) + ";",
        "const sc = {p: {scrollTop: 40}, feed: {scrollTop: 300}};",
        "const document = {getElementById: id => id === 'brpan' ? sc.p : sc.feed, body: {contains: () => true}};",
        "function brPanPaint(){ painted++; sc.p.scrollTop = 0; sc.feed.scrollTop = 0; }",
        "function brTreeFocus(s){ foc = s; }",
        _fn(src, "brTreeLoad"), _fn(src, "brTreeSave"), _fn(src, "brTreeModel"), _fn(src, "brTreeOpen"),
        _fn(src, "brTreeHtml"), _fn(src, "brTreeAll"), tail,
    ])
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class BranchTreeAll(unittest.TestCase):
    def test_expand_then_collapse_all_keeps_scroll(self):
        o = _run("brTreeAll(true); const a = Object.assign({}, brTreeSt), s1 = [sc.p.scrollTop, sc.feed.scrollTop];"
                 "brTreeAll(false); console.log(JSON.stringify({a: a, b: brTreeSt, s1: s1,"
                 "s2: [sc.p.scrollTop, sc.feed.scrollTop], painted: painted, foc: foc}));")
        self.assertEqual(set(o["a"]), {"L", "L/fix", "L/fix/a", "R:origin"})
        self.assertTrue(all(v == 1 for v in o["a"].values()))
        self.assertTrue(all(v == 0 for v in o["b"].values()))
        self.assertEqual(o["s1"], [40, 300])
        self.assertEqual(o["s2"], [40, 300])
        self.assertEqual(o["painted"], 2)
        self.assertEqual(o["foc"], '[data-bta="0"]')

    def test_rows_are_treeitems_and_buttons_present(self):
        o = _run("brTreeAll(true); const h = brTreeHtml(); console.log(JSON.stringify({h: h}));")
        h = o["h"]
        rows = len(re.findall(r'<button class="(?:brtf|brpr brtl)', h))
        self.assertEqual(rows, h.count("role=treeitem"))
        self.assertEqual(rows, 7)       # 3 groups/folders under L (L, fix, a) + R:origin + 3 leaves
        self.assertIn("data-bta=1>모두 펼치기", h)
        self.assertIn("data-bta=0>모두 접기", h)


if __name__ == "__main__":
    unittest.main()
