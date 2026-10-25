"""file_owner edit count `n` follows the FO_KEEP_S ownership window (it used to be a running total that never aged out)."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from tests import _clock
from tests._load import sidereus, load

load()
fo = sidereus("file_owner")


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _edit_line(path, t):
    return json.dumps({"timestamp": _iso(t), "cwd": "/r", "message": {"content": [
        {"type": "tool_use", "name": "Edit", "input": {"file_path": path}}]}})


class FoCountWindow(unittest.TestCase):
    def setUp(self):
        self.saved = ({k: dict(v) if isinstance(v, dict) else v for k, v in fo._FO.items()}, dict(fo._FO_N),
                      fo.CLAUDE_PROJECTS)
        fo._FO.update(at=0.0, off={}, per={}, who={})
        fo._FO_N.clear()
        fz = _clock.frozen(fo)
        fz.__enter__()
        self.addCleanup(fz.__exit__, None, None, None)

    def tearDown(self):
        fo._FO.clear(); fo._FO.update(self.saved[0])
        fo._FO_N.clear(); fo._FO_N.update(self.saved[1])
        fo.CLAUDE_PROJECTS = self.saved[2]

    def test_index_counts_only_edits_in_window(self):
        now = _clock.NOW
        fo._FO.update(at=now + 1e6, off={"t": (0, 1)}, per={"t": {"/r/a.py": now - 5}},
                      who={"t": ("s1", fo.FO_MAIN, "", "", "/r")})
        fo._FO_N["t"] = {"/r/a.py": [now - fo.FO_KEEP_S - 3600, now - fo.FO_KEEP_S - 60, now - 100, now - 5]}
        self.assertEqual(fo.index(now)["/r/a.py"][("s1", fo.FO_MAIN)]["n"], 2)

    def test_scan_ages_out_old_edits(self):
        root = tempfile.mkdtemp()
        fo.CLAUDE_PROJECTS = root
        os.makedirs(os.path.join(root, "-r"))
        fp = os.path.join(root, "-r", "sid1.jsonl")
        t0 = _clock.NOW
        with open(fp, "w", encoding="utf-8") as f:
            f.write("\n".join(_edit_line("/r/a.py", t0 - 60 * k) for k in (30, 20, 10)) + "\n")
        os.utime(fp, (t0, t0))
        idx = fo.index(t0)
        k = os.path.normpath("/r/a.py")    # scan normpaths the edited path (backslashes on Windows)
        self.assertEqual(idx[k][("sid1", fo.FO_MAIN)]["n"], 3)
        # A day later one fresh edit arrives: the three old calls must drop out of the count.
        later = t0 + fo.FO_KEEP_S + fo.FO_TTL
        with open(fp, "a", encoding="utf-8") as f:
            f.write(_edit_line("/r/a.py", later - 5) + "\n")
        os.utime(fp, (later, later))
        self.assertEqual(fo.index(later)[k][("sid1", fo.FO_MAIN)]["n"], 1)
        self.assertEqual(len(fo._FO_N[fp][k]), 1)       # pruned in storage too, not only at read


if __name__ == "__main__":
    unittest.main()


class FoIndexMemo(unittest.TestCase):
    """index() is built once per scan generation; a new scan or an entry aging out rebuilds it."""
    setUp, tearDown = FoCountWindow.setUp, FoCountWindow.tearDown

    def _seed(self, now):
        fo._FO.update(at=now + 1e6, off={"t": (0, 1)}, per={"t": {"/r/a.py": now - 5}},
                      who={"t": ("s1", fo.FO_MAIN, "", "", "/r")})
        fo._FO_N["t"] = {"/r/a.py": [now - 100, now - 5]}

    def test_same_generation_builds_once(self):
        now = _clock.NOW
        self._seed(now)
        first = fo.index(now)
        self.assertIs(fo.index(now + 1), first)
        self.assertIs(fo.index(now + 2), first)

    def test_new_generation_rebuilds(self):
        now = _clock.NOW
        self._seed(now)
        first = fo.index(now)
        fo._FO["per"]["t"]["/r/b.py"] = now - 1          # what a scan commit would add
        fo._FO_IDX["gen"] += 1
        second = fo.index(now)
        self.assertIsNot(second, first)
        self.assertEqual(set(second), {"/r/a.py", "/r/b.py"})

    def test_cut_passing_an_entry_rebuilds(self):
        now = _clock.NOW
        self._seed(now)
        self.assertEqual(fo.index(now)["/r/a.py"][("s1", fo.FO_MAIN)]["n"], 2)
        later = now - 100 + fo.FO_KEEP_S + 1             # the older count timestamp leaves the window
        self.assertEqual(fo.index(later)["/r/a.py"][("s1", fo.FO_MAIN)]["n"], 1)
