"""tests/_load.py redirects live paths; by-value copies (`from sidereus.quota import QUOTA_LOG`) must follow."""
import os
import sys
import tempfile
import unittest

from tests._load import sidereus

TMP = os.path.realpath(tempfile.gettempdir())


def _under_tmp(p):
    return os.path.realpath(p).startswith(TMP + os.sep)


class LivePathCopies(unittest.TestCase):
    def test_quota_log_copies_under_tmp(self):
        for name in ("quota", "burn", "burn_week", "burn_hist"):
            p = sidereus(name).QUOTA_LOG
            self.assertTrue(_under_tmp(p), name + ".QUOTA_LOG=" + p)

    def test_claude_projects_copies_under_tmp(self):
        sidereus("transcript")
        mods = [m for n, m in sorted(sys.modules.items())
                if n.startswith("sidereus.") and m is not None and hasattr(m, "CLAUDE_PROJECTS")]
        self.assertTrue(len(mods) > 5)
        for m in mods:
            self.assertTrue(_under_tmp(m.CLAUDE_PROJECTS), m.__name__ + ".CLAUDE_PROJECTS=" + m.CLAUDE_PROJECTS)

    def test_named_data_paths_under_tmp(self):
        for mod, name in (("config", "DATA_DIR"), ("config", "BUS"), ("config", "BUS_PATH"), ("bus", "BUS"),
                          ("bus", "DATA_DIR"), ("routes_post", "BUS_PATH"), ("cards", "CARDS"), ("notes", "CARDS"),
                          ("usage", "ANCHOR_FILE"), ("quota_loop", "ANCHOR_FILE"), ("room_tags", "ROOMS_PATH")):
            p = getattr(sidereus(mod), name)
            self.assertTrue(_under_tmp(p), mod + "." + name + "=" + p)

    def test_no_module_constant_under_live_data_dir(self):
        # ⚠DATA_DIR and CODE_DIR are the same folder live: code subtrees are allowed, anything else is data.
        sidereus("config")
        live = os.path.realpath(os.path.expanduser("~/.mailbox-mcp"))
        code = {"web", "features", ".claude", "sidereus", "hooks", "scripts", "docs", "tests", "mailbox_config.py"}
        bad = []
        for n, m in sorted(sys.modules.items()):
            if not n.startswith("sidereus.") or m is None:
                continue
            for k, v in vars(m).items():
                if k.isupper() and isinstance(v, str) and os.path.isabs(v):
                    rel = os.path.relpath(os.path.realpath(v), live)
                    if not rel.startswith("..") and rel != "." and rel.split(os.sep)[0] not in code:
                        bad.append(n + "." + k + "=" + v)
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
