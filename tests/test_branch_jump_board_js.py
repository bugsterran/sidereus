"""Branch jumps (strBrGo in 81, brWuJump in 89) clear a remembered Board sub-view, run through node."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all
from tests._node import node_e


def _fn(src, name):
    return re.search(r"^function " + name + r"\(.*?^}", src, re.S | re.M).group(0)


def _run(tail):
    src = js_all()
    js = "\n".join([
        "let brBoardOn = true, SAVED = null, VIEW = '', mainView = 'x', BR = null, brRepo = '/r', brSel = '', brDet = null, brWu = '', SESS = [];",
        "function brBoardSave(){ SAVED = brBoardOn ? '1' : '0'; } function setMainView(v){ VIEW = v; } function loadBr(){}",
        "function brNorm(p){ return p; } function brRepos(){ return ['/r']; } function tabSet(){} function brWtFind(){ return null; } function brWuFetch(){}",
        _fn(src, "strBrGo"), _fn(src, "brWuJump"), tail,
    ])
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class BranchJumpBoard(unittest.TestCase):
    def test_struct_badge_jump_clears_board(self):
        self.assertEqual(_run("strBrGo('/r'); console.log(JSON.stringify([brBoardOn, SAVED, VIEW]));"), [False, "0", "br"])

    def test_worktree_chip_jump_clears_board(self):
        self.assertEqual(_run("brWuJump('/r/wt', '/r/wt'); console.log(JSON.stringify([brBoardOn, SAVED, VIEW, brWu]));"),
                         [False, "0", "br", "/r/wt"])


if __name__ == "__main__":
    unittest.main()
