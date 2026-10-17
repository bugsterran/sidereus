"""Session work-log identity: two sessions in one cwd each open their own transcript, and the timeline
row tid always carries the sid (a plain `sess:<cwd>` opened the cwd's newest session instead of the clicked one)."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

wk = sidereus("work")
tl = sidereus("timeline")

CWD = "/x/proj"


def _write(fp, cmd):
    with open(fp, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "assistant", "timestamp": "2026-10-05T00:00:00.000Z", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}]}}) + "\n")


class SessionWorkBySid(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.fa = os.path.join(self.d, "sid-a.jsonl")
        self.fb = os.path.join(self.d, "sid-b.jsonl")
        _write(self.fa, "echo a")
        _write(self.fb, "echo b")
        self.saved = {k: getattr(wk, k) for k in ("_allowed_cwds", "_slug_files", "_sid_path", "_work_acct")}
        wk._allowed_cwds = lambda ttl=5: {CWD: {"project": "proj"}}
        wk._slug_files = lambda cwd: [self.fb, self.fa]          # newest first: sid-b
        wk._sid_path = lambda cwd, sid: {"sid-a": self.fa, "sid-b": self.fb}.get(sid, "")
        wk._work_acct = lambda sid, fp: {}

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(wk, k, v)
        shutil.rmtree(self.d)

    def _cmd(self, r):
        self.assertTrue(r.get("ok"), r)
        return [s.get("arg") for s in r["steps"]]

    def test_each_sid_reads_its_own_file(self):
        a = self._cmd(wk.session_work(CWD, "sid-a"))
        b = self._cmd(wk.session_work(CWD, "sid-b"))
        self.assertTrue(any("echo a" in str(x) for x in a), a)
        self.assertTrue(any("echo b" in str(x) for x in b), b)
        self.assertFalse(any("echo b" in str(x) for x in a), a)

    def test_no_sid_falls_back_to_newest(self):
        r = self._cmd(wk.session_work(CWD))
        self.assertTrue(any("echo b" in str(x) for x in r), r)


class TimelineSessTid(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.fp = os.path.join(self.d, "sid-live.jsonl")
        _write(self.fp, "echo")
        self.saved = {k: getattr(tl, k) for k in ("_sess_segments", "_compacts")}
        tl._sess_segments = lambda fp, cut, tok_out=None: ([], 0)
        tl._compacts = lambda fp, cut: []

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(tl, k, v)
        shutil.rmtree(self.d)

    def test_live_row_tid_has_sid(self):
        srow = {"sid": "sid-live", "cwd": CWD, "state": "tool", "ageSec": 1}
        r = tl._tl_sess_row(self.fp, "sid-live", srow, 0, CWD, "proj")
        self.assertEqual(r["tid"], "sess:" + CWD + "|sid-live")

    def test_past_row_tid_has_sid(self):
        r = tl._tl_sess_row(self.fp, "sid-old", None, 0, CWD, "proj")
        self.assertEqual(r["tid"], "sess:" + CWD + "|sid-old")


if __name__ == "__main__":
    unittest.main()
