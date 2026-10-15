"""ident._mbox_env_default parses ~/.claude.json once per (mtime_ns, size) and per path — no re-read on every row."""
import json
import os
import tempfile
import unittest

from tests._load import sidereus

ident = sidereus("ident")


class _CountJson:
    def __init__(self):
        self.n = 0

    def load(self, f):
        self.n += 1
        return json.load(f)


class MboxEnvMemo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-cj-")
        self.path = os.path.join(self.tmp, ".claude.json")
        self._write("alice", 1_000_000_000_000_000_000)
        self.counter = _CountJson()
        self.saved = (ident.claude_json, ident.json)
        ident.claude_json = lambda: self.path
        ident.json = self.counter
        ident._ENV_MEMO.clear()

    def tearDown(self):
        ident.claude_json, ident.json = self.saved
        ident._ENV_MEMO.clear()

    def _write(self, me, ns, path=None):
        p = path or self.path
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": {"mailbox": {"env": {"MAILBOX_ME": me}}}}, f)
        os.utime(p, ns=(ns, ns))

    def test_unchanged_stat_does_not_reread(self):
        self.assertEqual(ident._mbox_env_default(), "alice")
        self.assertEqual(ident._mbox_env_default(), "alice")
        self.assertEqual(self.counter.n, 1)

    def test_changed_mtime_rereads(self):
        ident._mbox_env_default()
        self._write("bobby", 2_000_000_000_000_000_000)   # same size, new mtime
        self.assertEqual(ident._mbox_env_default(), "bobby")
        self.assertEqual(self.counter.n, 2)

    def test_other_path_not_shared(self):
        ident._mbox_env_default()
        other = os.path.join(self.tmp, "other.json")
        self._write("carol", 1_000_000_000_000_000_000, path=other)
        ident.claude_json = lambda: other
        self.assertEqual(ident._mbox_env_default(), "carol")
        self.assertEqual(self.counter.n, 2)

    def test_missing_file_is_empty(self):
        os.remove(self.path)
        self.assertEqual(ident._mbox_env_default(), "")


if __name__ == "__main__":
    unittest.main()
