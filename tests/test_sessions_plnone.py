"""R4: row `plNone` (sessions._row_children) and the session-list chip (40b sessPlChip): a pipeline run, a declared
[pl-none] and an undeclared edit render three different chips. ⚠pl_runs.pl_none / pl_model and the row helpers are
stubbed — no live files, clock or network."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn, sidereus
from tests._node import node_e

S = sidereus("sessions")
R = sidereus("pl_runs")


class RowKey(unittest.TestCase):
    def setUp(self):
        self.saved = {k: getattr(S, k) for k in ("_team_row", "plm_of", "_wf_sets", "_pl_off", "_mon_rows")}
        self.r0 = (R.pl_none, R.pl_model)
        S._team_row = lambda fp: None
        S.plm_of = lambda sid, now: None
        S._wf_sets = lambda fp, now, dead: ([], [])
        S._pl_off = lambda *a: False
        S._mon_rows = lambda *a: []
        R.pl_model = lambda *a: []
        self.v = None
        R.pl_none = lambda sid: self.v

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(S, k, v)
        R.pl_none, R.pl_model = self.r0

    def _row(self, dead):
        return S._row_children("/x/s.jsonl", {"sid": "abcd1234-0000"}, 1000.0, dead)

    def test_absent_when_none(self):
        self.assertNotIn("plNone", self._row(False))

    def test_present_live_absent_dead(self):
        self.v = {"cat": "explore"}
        self.assertEqual(self._row(False)["plNone"], {"cat": "explore"})
        self.assertNotIn("plNone", self._row(True))


PRE = r"""
const T = s => s;
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Chip(unittest.TestCase):
    def _chips(self, rows):
        code = PRE + js_fn("sessPlChip") + "\nconsole.log(JSON.stringify(%s.map(sessPlChip)));" % json.dumps(rows)
        r = subprocess.run(node_e(code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        if r.returncode != 0:
            raise AssertionError(r.stderr.decode())
        return json.loads(r.stdout)

    def test_three_differ(self):
        run, decl, und = self._chips([
            {"plrun": [{"name": "old", "cur": "A", "end": 5}, {"name": "sidereus-change", "cur": "Verify"}]},
            {"plNone": {"cat": "explore"}},
            {"plNone": {"u": 1}},
        ])
        self.assertIn(">sidereus-change · Verify</span>", run)
        self.assertIn('class="spl spln"', decl)
        self.assertIn(">No pipeline · explore</span>", decl)
        self.assertIn('class="spl splu"', und)
        self.assertIn(">Undeclared</span>", und)
        self.assertEqual(len({run, decl, und}), 3)

    def test_ended_run_outranks_nudge(self):
        # R4: edit -> nudge -> pipeline run -> run ends: still a pipeline row, never «Undeclared».
        ended, = self._chips([{"plrun": [{"name": "sidereus-change", "cur": "Commit", "end": 9}], "plNone": {"u": 1}}])
        self.assertIn('class="spl spln"', ended)
        self.assertIn(">sidereus-change</span>", ended)
        self.assertNotIn("Undeclared", ended)

    def test_empty_and_escaped(self):
        none, x = self._chips([{}, {"plrun": [{"name": "<b>", "cur": "\"q"}]}])
        self.assertEqual(none, "")
        self.assertNotIn("<b>", x)
        self.assertIn("&lt;b> · &quot;q", x)


if __name__ == "__main__":
    unittest.main()
