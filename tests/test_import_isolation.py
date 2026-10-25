"""Importing sidereus from a test module never touches the real data dir, even when `from sidereus import x`
comes before `tests._load` (ext_store, bgtasks_parse, features, live_win, config read data files at import)."""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Child: a fake HOME whose ~/.mailbox-mcp holds a sentinel ext row; an audit hook records every open under it.
_CHILD = r"""
import os, sys
real = os.path.realpath(os.path.join(os.environ["HOME"], ".mailbox-mcp"))
hits = []
def _audit(ev, args):
    if ev == "open" and args and isinstance(args[0], (str, bytes)):
        p = os.fsdecode(args[0])
        if os.path.realpath(p).startswith(real + os.sep):
            hits.append(p)
sys.addaudithook(_audit)
import tests                               # what every tests.* module runs first
import sidereus.ext_store as ext           # a sidereus import before tests._load (the leaking order)
from tests import _load
_load.load()
import sidereus.config as cfg
print("DATA_DIR_LIVE=%d" % os.path.realpath(cfg.DATA_DIR).startswith(real))
print("SENTINEL=%d" % any(k[1] == "sentinel-live-row" for k in ext._ext))
print("HITS=%r" % sorted(set(hits)))
"""


class ImportIsolation(unittest.TestCase):
    def test_no_real_data_dir_reads_at_import(self):
        with tempfile.TemporaryDirectory() as home:
            data = os.path.join(home, ".mailbox-mcp")
            os.makedirs(data)
            with open(os.path.join(data, "ext-sessions.json"), "w", encoding="utf-8") as f:
                f.write('[{"platform": "gemini", "session_id": "sentinel-live-row", "pid": 1, "lastSeen": 0}]')
            env = {k: v for k, v in os.environ.items()
                   if k not in ("MAILBOX_DIR", "MAILBOX_CONFIG", "CODEX_HOME", "SIDEREUS_HOOK_NO_PID")}
            env["HOME"] = home
            r = subprocess.run([sys.executable, "-c", _CHILD], cwd=ROOT, env=env,
                               capture_output=True, text=True, encoding="utf-8", timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            self.assertIn("DATA_DIR_LIVE=0", r.stdout)
            self.assertIn("SENTINEL=0", r.stdout)
            self.assertIn("HITS=[]", r.stdout)


if __name__ == "__main__":
    unittest.main()
