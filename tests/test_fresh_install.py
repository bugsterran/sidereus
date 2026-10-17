"""First start on a fresh machine: no bus.jsonl and no ~/.claude/projects must not raise health warnings.
Temp paths only (never the live bus or transcripts)."""
import os
import shutil
import stat
import tempfile
import time
import unittest

from tests._load import sidereus

bus = sidereus("bus")
cards = sidereus("cards")


class FreshInstall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ensure_bus_creates_empty_0600(self):
        p = os.path.join(self.tmp, "bus.jsonl")
        bus.ensure_bus(p)
        self.assertEqual(os.path.getsize(p), 0)
        self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)

    def test_ensure_bus_keeps_existing(self):
        p = os.path.join(self.tmp, "bus.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"t": 1}\n')
        os.chmod(p, 0o644)
        bus.ensure_bus(p)
        with open(p, encoding="utf-8") as f:
            self.assertEqual(f.read(), '{"t": 1}\n')
        self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o644)

    def test_ensure_bus_missing_dir_is_quiet(self):
        p = os.path.join(self.tmp, "nope", "bus.jsonl")
        bus.ensure_bus(p)                  # must not raise
        self.assertFalse(os.path.exists(p))

    def test_no_projects_dir_is_empty_not_error(self):
        saved = cards.CLAUDE_PROJECTS
        cards.CLAUDE_PROJECTS = os.path.join(self.tmp, "no-projects")
        try:
            self.assertEqual(cards._recent_transcripts(time.time(), 12), [])
        finally:
            cards.CLAUDE_PROJECTS = saved


if __name__ == "__main__":
    unittest.main()
