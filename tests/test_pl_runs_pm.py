"""pl_runs.pl_pm (R2): no-prompt permission modes in effect during a pipeline run, and the sessions wiring.
Pure data; pl_model / pmode_spans and the row helpers are stubbed — no live files, clock or network."""
import unittest

from tests._load import sidereus

R = sidereus("pl_runs")
S = sidereus("sessions")
LP = sidereus("live_probe")
M = LP._NO_PROMPT_MODES


def pm(runs, spans, now=1000.0):
    R.pl_pm(runs, spans, now, M)
    return runs


class InEffect(unittest.TestCase):
    def test_mode_set_before_t0_counts(self):
        r, = pm([{"t0": 500, "end": 600}], [["bypassPermissions", 100, 120]])
        self.assertEqual(r["pm"], ["bypassPermissions"])

    def test_span_after_window_end_does_not(self):
        r, = pm([{"t0": 500, "end": 600}], [["default", 100, 100], ["auto", 650, 700]])
        self.assertNotIn("pm", r)

    def test_default_between_ends_the_earlier_span(self):
        # ⚠filtering before pl_pm would stretch the first bypass over [300, 400]
        r, = pm([{"t0": 300, "end": 400}], [["bypassPermissions", 100, 100], ["default", 200, 200], ["bypassPermissions", 500, 500]])
        self.assertNotIn("pm", r)

    def test_open_run_uses_now_and_sorts_unique(self):
        r, = pm([{"t0": 500, "end": 0}], [["dontAsk", 100, 100], ["default", 510, 510], ["auto", 900, 900], ["dontAsk", 950, 950]])
        self.assertEqual(r["pm"], ["auto", "dontAsk"])
        late, = pm([{"t0": 500, "end": 0}], [["default", 100, 100], ["auto", 900, 900]], now=800.0)
        self.assertNotIn("pm", late)

    def test_past_entries_annotated(self):
        r, = pm([{"t0": 500, "end": 0, "past": [{"t0": 100, "end": 0, "t1": 150}, {"t0": 200, "end": 250, "t1": 260}]}],
                [["auto", 120, 120], ["default", 180, 180], ["bypassPermissions", 600, 600]])
        self.assertEqual(r["pm"], ["bypassPermissions"])
        self.assertEqual(r["past"][0]["pm"], ["auto"])
        self.assertNotIn("pm", r["past"][1])

    def test_no_key_without_a_no_prompt_mode(self):
        r, = pm([{"t0": 500, "end": 600}], [["default", 100, 100], ["acceptEdits", 550, 550], ["plan", 590, 590]])
        self.assertNotIn("pm", r)
        r, = pm([{"t0": 500, "end": 600}], [])
        self.assertNotIn("pm", r)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.saved = {k: getattr(S, k) for k in ("_team_row", "plm_of", "_wf_sets", "_pl_off", "_mon_rows", "pmode_spans")}
        self.r0 = (R.pl_none, R.pl_model)
        S._team_row = lambda fp: None
        S.plm_of = lambda sid, now: None
        S._wf_sets = lambda fp, now, dead: ([], [])
        S._pl_off = lambda *a: False
        S._mon_rows = lambda *a: []
        R.pl_none = lambda sid: None
        self.calls = []
        S.pmode_spans = lambda fp: self.calls.append(fp) or [["bypassPermissions", 1, 1]]

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(S, k, v)
        R.pl_none, R.pl_model = self.r0

    def _row(self):
        return S._row_children("/x/s.jsonl", {"sid": "abcd1234-0000"}, 1000.0, False)

    def test_no_read_without_a_run(self):
        R.pl_model = lambda *a: []
        self.assertNotIn("plrun", self._row())
        self.assertEqual(self.calls, [])

    def test_run_gets_pm(self):
        R.pl_model = lambda *a: [{"name": "x", "t0": 500, "end": 0, "past": []}]
        row = self._row()
        self.assertEqual(self.calls, ["/x/s.jsonl"])
        self.assertEqual(row["plrun"][0]["pm"], ["bypassPermissions"])


if __name__ == "__main__":
    unittest.main()
