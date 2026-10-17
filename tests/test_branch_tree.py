"""Branch tab folder tree default open state (web/js/89-branch-worktree.js brTreeModel/brTreeOpen), run through node."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import js_all   # all web/js joined - functions are found by name, whichever file holds them
from tests._node import node_e


def _fn(src, name):
    m = re.search(r"^function " + name + r"\(.*?^}", src, re.S | re.M)
    return m.group(0)


def _run(branches, head):
    src = js_all()
    js = "\n".join([
        "const T = s => s; let brMerge = true, brTreeSt = {};",
        "let BR = " + json.dumps({"ok": True, "head": head, "detached": False, "branches": branches, "worktrees": []}) + ";",
        _fn(src, "brTreeModel"), _fn(src, "brTreeOpen"),
        "const out = {}; const walk = (n, d) => { out[n.id] = brTreeOpen(n, d); n.kids.forEach(k => walk(k, d + 1)); };",
        "brTreeModel().forEach(g => walk(g, 0)); console.log(JSON.stringify(out));",
    ])
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class BranchTreeOpen(unittest.TestCase):
    OLD = 1_000_000_000      # far older than 7 days

    def test_cold_group_opens_top_folders(self):
        # repo-J shape: every non-HEAD branch old -> folders must not all stay closed (read as "remote only").
        bl = [{"name": "main", "kind": "local", "upstream": "origin/main", "ts": self.OLD},
              {"name": "origin/main", "kind": "remote", "upstream": "", "ts": self.OLD},
              {"name": "fix/a", "kind": "local", "upstream": "", "ts": self.OLD},
              {"name": "fix/b", "kind": "local", "upstream": "", "ts": self.OLD},
              {"name": "docs/c", "kind": "local", "upstream": "", "ts": self.OLD}]
        o = _run(bl, "main")
        self.assertTrue(o["L/fix"])
        self.assertTrue(o["L/docs"])

    def test_hot_folder_keeps_old_folders_closed(self):
        import time
        now = int(time.time())
        bl = [{"name": "main", "kind": "local", "upstream": "", "ts": self.OLD},
              {"name": "fix/new", "kind": "local", "upstream": "", "ts": now},
              {"name": "docs/old", "kind": "local", "upstream": "", "ts": self.OLD}]
        o = _run(bl, "main")
        self.assertTrue(o["L/fix"])
        self.assertFalse(o["L/docs"])


if __name__ == "__main__":
    unittest.main()
