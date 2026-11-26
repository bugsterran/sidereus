"""One run-verdict rule on both sides: sidereus/state_v1.py `verdict` (GET /api/v1/state runs[].verdict) and
48n `visitVerdict` («Since your last visit» strip) over the same vectors in tests/fixtures/verdict_vectors.json."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import ROOT, js_fn, sidereus
from tests._node import node_e

sv = sidereus("state_v1")
VEC = os.path.join(ROOT, "tests", "fixtures", "verdict_vectors.json")
ARGS = ("S", "end", "stop", "titles", "cur", "past")


def _rows():
    with open(VEC, encoding="utf-8") as f:
        return json.load(f)


class VerdictVectors(unittest.TestCase):
    def test_table_shape(self):
        rows = _rows()
        self.assertGreaterEqual(len(rows), 12)
        for r in rows:
            self.assertEqual(set(r), {"why", "want"} | set(ARGS), r.get("why"))
            self.assertIn(r["want"], ("pass", "fail", "unknown"))
        self.assertEqual({r["want"] for r in rows}, {"pass", "fail", "unknown"})

    def test_python(self):
        for r in _rows():
            self.assertEqual(sv.verdict(*[r[k] for k in ARGS]), r["want"], r["why"])

    def test_js(self):
        if not shutil.which("node"):
            self.skipTest("node not installed")
        js = (js_fn("visitVerdict") + "\nconst R = " + json.dumps(_rows()) + ";\n"
              "process.stdout.write(JSON.stringify(R.map(r => visitVerdict(r.S, r.end, r.stop, r.titles, r.cur, r.past))));")
        p = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(p.returncode, 0, p.stderr)
        got = json.loads(p.stdout)
        for r, g in zip(_rows(), got):
            self.assertEqual(g, r["want"], r["why"])
        self.assertEqual(len(got), len(_rows()))


if __name__ == "__main__":
    unittest.main()
