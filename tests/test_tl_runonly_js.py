"""Timeline «실행 중만» filter (web/js/74 tlOrdered runOnly): only branches with a running agent
(row `run`) stay, finished ancestors of a running child are kept for lineage, session heads always stay."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlRunOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = js_fn("tlOrdered") + r"""
const ag = (key, start, run, aid, par) => ({key, items: [{start, run, aid, par}]});
const mk = () => {
  const p1 = ag('p1', 1, false, 'A'), c1 = ag('c1', 2, true, 'B', 'A'), d1 = ag('d1', 3, false, 'C');
  const d2 = ag('d2', 4, false, 'D');
  return [{head: {key: 'S1', items: []}, kids: [p1, c1, d1]},
          {head: {key: 'S2', items: []}, kids: [d2]}];
};
const keys = rs => rs.map(g => g.key);
process.stdout.write(JSON.stringify({all: keys(tlOrdered(mk())), on: keys(tlOrdered(mk(), true))}));
"""
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        cls.R = json.loads(r.stdout)

    def test_off_keeps_everything(self):
        self.assertEqual(self.R["all"], ["S1", "p1", "c1", "d1", "S2", "d2"])

    def test_on_keeps_running_branch_only(self):
        self.assertEqual(self.R["on"], ["S1", "p1", "c1", "S2"])


if __name__ == "__main__":
    unittest.main()
