"""Arrow keys open the landed-on file once the cursor settles: structure tree (81b strTreeOpenLater) and
diff popup file list (35c dfListKey / dfPickOpen), run through node with a fake timer."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all
from tests._node import node_e


def _fn(src, name):
    return re.search(r"^function " + name + r"\(.*?^}", src, re.S | re.M).group(0)


def _const(src, name):
    return re.search(r"^const " + name + r" = .*?;$", src, re.M).group(0)


TIMER = ("let tq = [], tid = 0;"
         "function setTimeout(f, ms){ tq.push({id: ++tid, f: f, ms: ms}); return tid; }"
         "function clearTimeout(id){ tq = tq.filter(t => t.id !== id); }"
         "function flush(){ const q = tq; tq = []; q.forEach(t => t.f()); }"
         "function softErr(){}")


def _run(js):
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def _str(tail):
    src = js_all()
    return _run("\n".join([
        TIMER,
        "let opened = [], foc = '';",
        "let strPop = {tree: {cur: 'f:a.py', file: ''}};",
        "function strTreeOpenFile(p){ opened.push(p); strPop.tree.file = p; }",
        "function strPopDoc(){ return {querySelector: s => ({focus: () => { foc = s; }})}; }",
        _const(src, "STR_TREE_OPEN_MS"), "let strTreeOpenT = 0;", _fn(src, "strTreeOpenLater"), tail,
    ]))


def _df(tail):
    src = js_all()
    return _run("\n".join([
        TIMER,
        "let diffPick = -1, fullOn = true, shows = 0, focused = null, marked = [];",
        "function mk(fi){ const cls = new Set(); return {fi: fi, classList: {toggle: (c, on) => on ? cls.add(c) : cls.delete(c), has: c => cls.has(c)},"
        "  getAttribute: () => String(fi), focus: function(){ focused = this.fi; }, scrollIntoView: () => {},"
        "  closest: function(){ return this; }}; }",
        "let rows = [mk(-1), mk(0), mk(1), mk(2)];",
        "const document = {querySelectorAll: () => rows, querySelector: s => rows.find(r => s.indexOf('\"' + r.fi + '\"') >= 0) || null};",
        "function diffShow(){ shows++; rows = rows.map(r => mk(r.fi)); }",
        "function a11yMark(el){ marked.push(el.fi); }",
        _fn(src, "dfPickOpen"), _const(src, "DF_KEY_OPEN_MS"), "let dfKeyT = 0;", _fn(src, "dfListKey"),
        "function key(k, t){ let pd = 0; dfListKey({key: k, target: t, preventDefault: () => { pd = 1; }}); return pd; }",
        tail,
    ]))


@unittest.skipUnless(shutil.which("node"), "node not installed")
class StructureTreeArrowOpen(unittest.TestCase):
    def test_burst_opens_only_the_last_file_and_refocuses_tree(self):
        o = _str("strTreeOpenLater(strPop, '.srtt'); strPop.tree.cur = 'f:b.py'; strPop.tree.file = '';"
                 "strTreeOpenLater(strPop, '.srtt'); const n = tq.length; flush();"
                 "console.log(JSON.stringify({opened: opened, foc: foc, n: n}));")
        self.assertEqual(o["n"], 1)
        self.assertEqual(o["opened"], ["b.py"])
        self.assertEqual(o["foc"], "#spbody .srtt")

    def test_directory_row_or_open_file_or_other_window_opens_nothing(self):
        o = _str("strPop.tree.cur = 'd:src'; strTreeOpenLater(strPop, '.srtq'); flush();"
                 "strPop.tree = {cur: 'f:x.py', file: 'x.py'}; strTreeOpenLater(strPop, '.srtq'); flush();"
                 "const sp = strPop; sp.tree = {cur: 'f:y.py', file: ''}; strTreeOpenLater(sp, '.srtq');"
                 "strPop = {tree: {cur: 'f:z.py', file: ''}}; flush();"
                 "console.log(JSON.stringify({opened: opened, foc: foc}));")
        self.assertEqual(o["opened"], [])
        self.assertEqual(o["foc"], "")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class DiffListArrowOpen(unittest.TestCase):
    def test_arrows_move_highlight_now_and_open_once_after_burst(self):
        o = _df("const pd = key('ArrowDown', rows[0]); const mid = [focused, rows[1].classList.has('on'), shows];"
                "key('ArrowDown', rows[1]); const n = tq.length; flush();"
                "console.log(JSON.stringify({pd: pd, mid: mid, n: n, pick: diffPick, shows: shows, full: fullOn,"
                " focused: focused, marked: marked}));")
        self.assertEqual(o["pd"], 1)
        self.assertEqual(o["mid"], [0, True, 0])     # highlight + focus move at once, no render yet
        self.assertEqual(o["n"], 1)                  # second key replaced the first timer
        self.assertEqual(o["pick"], 1)
        self.assertEqual(o["shows"], 1)
        self.assertFalse(o["full"])
        self.assertEqual(o["focused"], 1)            # the re-rendered row gets focus back
        self.assertIn(1, o["marked"])

    def test_edges_other_keys_and_same_pick(self):
        o = _df("const up = key('ArrowUp', rows[0]); const lr = key('ArrowLeft', rows[1]);"
                "const off = key('ArrowDown', {closest: () => null});"
                "diffPick = 1; key('ArrowDown', rows[1]); flush();"
                "console.log(JSON.stringify({up: up, lr: lr, off: off, shows: shows, q: tq.length}));")
        self.assertEqual(o["up"], 1)                 # top edge: swallowed, nothing scheduled
        self.assertEqual(o["lr"], 0)
        self.assertEqual(o["off"], 0)                # outside the file list: page keeps the key
        self.assertEqual(o["shows"], 0)              # landed on the already shown file


if __name__ == "__main__":
    unittest.main()
