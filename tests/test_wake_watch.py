"""A fresh `.wake/<sid>.lock` (hooks/mailbox_wake.py waiter) counts as a mailbox watch on that session row. Tmp dirs only."""
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

ss = sidereus("sessions")
SID = "7ba0c383-957c-46fe-92e4-2e401caef4c1"


class WakeWatch(unittest.TestCase):
    def setUp(self):
        g = ss._mon_rows.__globals__
        self.saved = {k: g[k] for k in ("DATA_DIR", "mailbox_watches")}
        self.tmp = tempfile.mkdtemp(prefix="sidereus-wake-")
        g["DATA_DIR"] = self.tmp
        g["mailbox_watches"] = lambda: {}
        os.makedirs(os.path.join(self.tmp, ".wake"))
        self.lock = os.path.join(self.tmp, ".wake", SID + ".lock")
        with open(self.lock, "w", encoding="utf-8") as f:
            f.write("12345")
        os.utime(self.lock, (1000.0, 1000.0))
        self.fp = os.path.join(self.tmp, "proj", SID + ".jsonl")

    def tearDown(self):
        ss._mon_rows.__globals__.update(self.saved)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fresh_lock_is_proc_watch(self):
        rows = ss._mon_rows(self.fp, [], 1010.0, False)
        self.assertEqual(rows, [{"lab": "Mailbox watch", "src": "proc"}])

    def test_stale_lock_is_ignored(self):
        self.assertEqual(ss._mon_rows(self.fp, [], 1016.0, False), [])

    def test_other_session_and_dead_row(self):
        other = os.path.join(self.tmp, "proj", "aaaa1111-0000-4000-8000-000000000000.jsonl")
        self.assertEqual(ss._mon_rows(other, [], 1010.0, False), [])
        self.assertEqual(ss._mon_rows(self.fp, [], 1010.0, True), [])

    def test_lookup_failure_keeps_wake_row(self):
        ss._mon_rows.__globals__["mailbox_watches"] = lambda: None
        rows = ss._mon_rows(self.fp, [], 1010.0, False)
        self.assertEqual([r["src"] for r in rows], ["proc"])

    def test_bad_name_never_builds_path(self):
        self.assertEqual(ss._wake_rows(os.path.join(self.tmp, "a/../b c.jsonl"), 1010.0), [])
        self.assertEqual(ss._wake_rows("", 1010.0), [])


if __name__ == "__main__":
    unittest.main()
