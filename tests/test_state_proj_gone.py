"""sidereus/state.py `proj_gone`: session cwd/repos folders missing on disk, memoized per path for PROJ_DIR_TTL_S.
No live files or clock: `_isdir` and `_mono` are patched on the state module."""
import unittest

from tests._load import sidereus

st = sidereus("state")


class ProjGone(unittest.TestCase):
    def setUp(self):
        saved = {k: getattr(st, k) for k in ("_isdir", "_mono")}
        self.addCleanup(lambda: [setattr(st, k, v) for k, v in saved.items()])
        old = st._proj_dir_memo
        self.addCleanup(setattr, st, "_proj_dir_memo", old)
        st._proj_dir_memo = type(old)(st.PROJ_DIR_MAX)
        self.exists = {"/u/keep"}
        self.calls = []
        self.t = 1000.0
        st._isdir = lambda p: (self.calls.append(p), p in self.exists)[1]
        st._mono = lambda: self.t

    def test_missing_dropped_existing_kept(self):
        rows = [{"cwd": "/u/keep", "repos": ["/u/keep", "/u/wt-old"]}, {"cwd": "/u/gone"}, "junk", {"cwd": "rel/x"}]
        self.assertEqual(st.proj_gone(rows), ["/u/gone", "/u/wt-old"])

    def test_cache_respected_until_ttl(self):
        rows = [{"cwd": "/u/keep"}, {"cwd": "/u/gone"}]
        st.proj_gone(rows)
        n = len(self.calls)
        self.exists.add("/u/gone")
        self.t += st.PROJ_DIR_TTL_S - 1
        self.assertEqual(st.proj_gone(rows), ["/u/gone"])   # memo still says missing
        self.assertEqual(len(self.calls), n)
        self.t += 2
        self.assertEqual(st.proj_gone(rows), [])
        self.assertEqual(len(self.calls), n + 2)

    def test_cap_holds_with_fresh_paths(self):
        rows = [{"cwd": "/u/p%d" % i} for i in range(st.PROJ_DIR_MAX + 50)]
        self.assertEqual(len(st.proj_gone(rows)), st.PROJ_DIR_MAX + 50)
        self.assertEqual(len(st._proj_dir_memo), st.PROJ_DIR_MAX)

    def test_empty(self):
        self.assertEqual(st.proj_gone(None), [])
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
