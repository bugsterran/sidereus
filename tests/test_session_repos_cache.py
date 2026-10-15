"""session_repos (sidereus/gitinfo.py): one cache entry per transcript; incremental scan keeps early repos."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

gi = sidereus("gitinfo")


class SessionReposCache(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="sidereus-repocache-")
        self.saved = (gi._tool_inputs, gi._git_root)
        self.reads = []
        gi._tool_inputs = lambda fp, off: (self.reads.append(fp), ([], off, False))[1]
        gi._git_root = lambda d: ""
        gi._REPO_CACHE.clear()

    def tearDown(self):
        gi._tool_inputs, gi._git_root = self.saved
        gi._REPO_CACHE.clear()
        shutil.rmtree(self.d, ignore_errors=True)

    def test_active_writes_keep_stable_entry(self):
        stable, active = os.path.join(self.d, "s.jsonl"), os.path.join(self.d, "a.jsonl")
        gi.session_repos(stable, 1.0, None)
        for mt in range(2, 500):                 # far more writes than the cap
            gi.session_repos(active, float(mt), None)
        self.reads.clear()
        gi.session_repos(stable, 1.0, None)
        self.assertEqual(self.reads, [])         # stable session served from cache
        self.assertEqual(len(gi._REPO_CACHE), 2)

    def test_mtime_change_recomputes(self):
        fp = os.path.join(self.d, "x.jsonl")
        gi.session_repos(fp, 1.0, None)
        gi.session_repos(fp, 1.0, None)
        gi.session_repos(fp, 2.0, None)
        self.assertEqual(self.reads, [fp, fp])

    def test_lru_cap(self):
        for i in range(gi._REPO_CACHE_MAX + 10):
            gi.session_repos(os.path.join(self.d, "%d" % i), 1.0, None)
        self.assertEqual(len(gi._REPO_CACHE), gi._REPO_CACHE_MAX)
        self.assertNotIn(os.path.join(self.d, "0"), gi._REPO_CACHE)


class SessionReposIncremental(unittest.TestCase):
    """Roots are found anywhere in the transcript, not just in a tail window, and survive appended scans."""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="sidereus-repokeep-")
        self.saved = gi._git_root
        base = os.path.dirname(os.path.expanduser("~")) or "/Users"
        self.wt = os.path.join(base, "someone", "proj-wt-agent")
        self.other = os.path.join(base, "someone", "other")
        gi._git_root = lambda d: next((r for r in (self.wt, self.other) if d.startswith(r)), "")
        gi._REPO_CACHE.clear()
        self.fp = os.path.join(self.d, "t.jsonl")

    def tearDown(self):
        gi._git_root = self.saved
        gi._REPO_CACHE.clear()
        shutil.rmtree(self.d, ignore_errors=True)

    def _edit(self, root):
        return json.dumps({"message": {"content": [{"type": "tool_use", "name": "Edit",
                                                    "input": {"file_path": root + "/src/a.py"}}]}}) + "\n"

    def _filler(self):
        return (json.dumps({"message": {"content": "x" * 1000}}) + "\n") * 1700   # >1.5MB, past a tail window

    def test_cold_scan_finds_early_root(self):
        with open(self.fp, "w") as f:
            f.write(self._edit(self.wt) + self._filler())
        self.assertEqual(gi.session_repos(self.fp, 1.0, None), [self.wt])

    def test_root_survives_append_and_recent_first(self):
        with open(self.fp, "w") as f:
            f.write(self._edit(self.wt))
        self.assertEqual(gi.session_repos(self.fp, 1.0, None), [self.wt])
        with open(self.fp, "a") as f:
            f.write(self._filler() + self._edit(self.other))
        self.assertEqual(gi.session_repos(self.fp, 2.0, None), [self.other, self.wt])

    def test_shrunk_file_rescans_from_zero(self):
        with open(self.fp, "w") as f:
            f.write(self._edit(self.wt) + self._filler())
        gi.session_repos(self.fp, 1.0, None)
        with open(self.fp, "w") as f:
            f.write(self._edit(self.other))
        self.assertEqual(gi.session_repos(self.fp, 2.0, None), [self.other])


if __name__ == "__main__":
    unittest.main()
