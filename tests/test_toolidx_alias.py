"""toolidx: a projects dir reached through two spellings (CLAUDE_CONFIG_DIR alias / symlink) and a dropped file
must not turn already-indexed ids into duplicates (issue #17). Temp dirs only; disk cache patched to the temp dir."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import load, sidereus

load()
ti = sidereus("toolidx")
NOW = 1_800_000_000.0


def _tu(tid, ts):
    return {"type": "assistant", "timestamp": "2027-01-15T08:00:00.000Z",
            "message": {"content": [{"type": "tool_use", "id": tid, "name": "Skill", "input": {"skill": "s"}}]}}


class ToolIdxAliasTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-tialias-")
        self.real = os.path.join(self.tmp, "real", "projects")
        os.symlink(os.path.join(self.tmp, "real"), os.path.join(self.tmp, "alias"))
        self.alias = os.path.join(self.tmp, "alias", "projects")
        self.saved = (ti.CLAUDE_PROJECTS, ti._TI_ROOT, ti.TI_CACHE, ti.TI_BG, ti.projects_dirs, ti._scan_file)
        ti.TI_BG = False
        ti.TI_CACHE = os.path.join(self.tmp, "cache.json")
        ti.projects_dirs = lambda p: [p]
        self.files = []
        for i in range(6):
            ids = ["toolu_%d_%d" % (i, j) for j in range(3)] + (["toolu_shared"] if i < 2 else [])
            p = os.path.join(self.real, "-p%d" % i, "s.jsonl")
            os.makedirs(os.path.dirname(p))
            with open(p, "w", encoding="utf-8") as f:
                f.write("".join(json.dumps(_tu(t, NOW)) + "\n" for t in ids))
            os.utime(p, (NOW - 3600, NOW - 3600))
            self.files.append(p)

    def tearDown(self):
        (ti.CLAUDE_PROJECTS, ti._TI_ROOT, ti.TI_CACHE, ti.TI_BG, ti.projects_dirs, ti._scan_file) = self.saved
        ti.reset()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _use(self, root):
        ti.CLAUDE_PROJECTS = ti._TI_ROOT = root
        ti.reset()
        self.calls, real = [], self.saved[5]
        ti._scan_file = lambda *a: self.calls.append(a[0]) or real(*a)
        self.assertTrue(ti._refresh(NOW, 1 << 30))

    def test_other_spelling_reuses_cache(self):
        self._use(self.real)
        dup = set(ti._TI_DUP)
        self.assertEqual(len(dup), 2)       # toolu_shared in two files: its `t#` tool id + its skill id
        ti._TI_STATE["saved"] = -1e9
        ti._save(ti._snapshot(NOW))
        self._use(self.alias)
        self.assertEqual((self.calls, ti._TI_DUP), ([], dup))   # no rescan, no new dups

    def test_dropped_file_rescan_keeps_dups(self):
        self._use(self.real)
        dup, n = set(ti._TI_DUP), sum(len(e["ids"]) for e in ti._TI_FILES.values())
        p = self.files[3]
        os.rename(p, p + ".x")
        self.assertTrue(ti._refresh(NOW, 1 << 30))
        os.rename(p + ".x", p)
        self.assertTrue(ti._refresh(NOW, 1 << 30))
        self.assertEqual(self.calls[-1], p)
        self.assertEqual((ti._TI_DUP, sum(len(e["ids"]) for e in ti._TI_FILES.values())), (dup, n))


if __name__ == "__main__":
    unittest.main()
