"""Demo world reads one clock per request: a second tick mid-build must not split running `end` ties (timeline group order)."""
import itertools
import unittest
from urllib.parse import urlparse

from tests._load import sidereus

demo = sidereus("demo")

A = 1_790_000_000


def _get(w, path, q=""):
    return demo.respond(w, path, urlparse(path + ("?" + q if q else "")))


class DemoOneClockPerRequest(unittest.TestCase):
    def setUp(self):
        self._time = demo.time.time
        tick = itertools.count(A + 600)
        demo.time.time = lambda: float(next(tick))   # every read is one second later
        self.w = demo.World(anchor=A)

    def tearDown(self):
        demo.time.time = self._time

    def test_timeline_running_rows_share_now(self):
        code, out = _get(self.w, "/api/agents/timeline", "hours=3")
        self.assertEqual(code, 200)
        ends = {r["end"] for r in out["rows"] if r.get("run")}
        self.assertTrue(any(r.get("kind") == "wf" for r in out["rows"]))   # workflow rows built through wf_runs
        self.assertEqual(ends, {out["at"]})

    def test_state_runs_share_now(self):
        code, out = _get(self.w, "/api/state")
        self.assertEqual(code, 200)
        wf = [w for s in out["sessions"] for w in s.get("wf") or []]
        self.assertTrue(wf)
        self.assertEqual({w["end"] for w in wf}, {out["usage"]["at"]})

    def test_next_request_reads_a_new_clock(self):
        a1 = _get(self.w, "/api/agents/timeline")[1]["at"]
        a2 = _get(self.w, "/api/agents/timeline")[1]["at"]
        self.assertGreater(a2, a1)


if __name__ == "__main__":
    unittest.main()
