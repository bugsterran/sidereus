"""review._owned: the per-sid file map is built once per file_owner.index() result, not per file x session.
No live data: `file_owner.index`, `file_owner._by_sid` and `review._edit_target` are faked."""
import unittest
from unittest import mock

from tests._load import load, sidereus

load()
rv = sidereus("review")
fo = sidereus("file_owner")
A, B, C = "aaaa0000-0000-4000-8000-000000000001", "bbbb0000-0000-4000-8000-000000000002", "cccc0000"
NOW = 1_800_000_000.0
N = 40


def _units(*sids):
    return {(s, "main"): {"ts": NOW - 60, "n": 1, "agent": "", "desc": "", "cwd": "/r"} for s in sids}


class Owned(unittest.TestCase):
    def setUp(self):
        idx = {"/r/f%02d.py" % i: _units(A, B) if i % 2 else _units(A) for i in range(N)}
        idx["/r/sub.py"] = {(B, "agent-1"): {"ts": NOW, "n": 1, "agent": "x", "desc": "", "cwd": "/r"}}
        idx["/outside.py"] = _units(A)
        self.idx = idx
        self.by_sid = mock.Mock(side_effect=fo._by_sid)
        self.targets = []
        for name, val in (("index", lambda now=None: self.idx), ("_by_sid", self.by_sid)):
            p = mock.patch.object(fo, name, val)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(rv, "_edit_target", self._target)
        p.start()
        self.addCleanup(p.stop)
        rv._RV_OWN[0] = (None, {})

    def _target(self, path):
        self.targets.append(path)
        return {"cwd": "/r", "path": path[3:]} if path.startswith("/r/") else None

    def test_same_result_and_built_once(self):
        a, b, c = rv._owned(A, NOW), rv._owned(B, NOW), rv._owned(C, NOW)
        self.assertEqual(a, {"/r": sorted("f%02d.py" % i for i in range(N))})
        self.assertEqual(b, {"/r": sorted(["f%02d.py" % i for i in range(1, N, 2)] + ["sub.py"])})
        self.assertEqual(c, {})
        self.assertEqual(self.by_sid.call_count, 0)
        self.assertEqual(len(self.targets), len(self.idx))   # one pass over the index for all sessions

    def test_new_index_object_rebuilds(self):
        rv._owned(A, NOW)
        self.idx = dict(self.idx, **{"/r/new.py": _units(A)})
        self.assertIn("new.py", rv._owned(A, NOW)["/r"])


if __name__ == "__main__":
    unittest.main()
