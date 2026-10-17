"""Session search (Cmd+K cpMatch) finds platforms by Korean alias too, since platName shows Latin only. Runs JS through node."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

STUBS = """
const AILG = {cc: ['Claude'], gm: ['Gemini'], cx: ['Codex']};
const LBL = {unknown: '', idle: '유휴'};
const stateLbl = k => LBL[k] || '';
"""
ROWS = [
    {"id": "a", "plat": "gm", "project": "alpha", "cwd": "/w/alpha", "model": "gemini-2.5-pro", "state": "idle"},
    {"id": "b", "plat": "cx", "project": "beta", "cwd": "/w/beta", "model": "gpt-5", "state": "idle"},
    {"id": "c", "project": "gamma", "cwd": "/w/gamma", "model": "opus", "state": "idle"},
]


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PlatSearch(unittest.TestCase):
    def ids(self, q):
        src = STUBS + "\n".join(js_fn(n) for n in ("platName", "platHay", "cpHay", "cpMatch")) \
            + "\nprocess.stdout.write(JSON.stringify(cpMatch(" + json.dumps(q) + ", " + json.dumps(ROWS) + ").map(x => x.id)));"
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        return json.loads(r.stdout)

    def test_korean_aliases(self):
        self.assertEqual(self.ids("제미나이"), ["a"])
        self.assertEqual(self.ids("코덱스"), ["b"])
        self.assertEqual(self.ids("클로드"), ["c"])

    def test_latin_names_case_insensitive(self):
        self.assertEqual(self.ids("GEMINI"), ["a"])
        self.assertEqual(self.ids("codex"), ["b"])
        self.assertEqual(self.ids("Claude"), ["c"])

    def test_plain_query_unchanged(self):
        self.assertEqual(self.ids(""), ["a", "b", "c"])
        self.assertEqual(self.ids("beta"), ["b"])
        self.assertEqual(self.ids("제미나이 alpha"), ["a"])
        self.assertEqual(self.ids("제미나이 beta"), [])
        self.assertEqual(self.ids("nomatch"), [])


if __name__ == "__main__":
    unittest.main()
