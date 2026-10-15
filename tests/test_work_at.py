"""Session work log at a past moment (retro failure drill-down): transcript._lines_until reads the window ending at `at`."""
import json
import os
import tempfile
import unittest

from tests._load import sidereus

tr = sidereus("transcript")
st = sidereus("steps")


def _iso(t):
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))


class LinesUntil(unittest.TestCase):
    def setUp(self):
        self.t0 = 1_790_000_000
        fd, self.fp = tempfile.mkstemp(suffix=".jsonl")
        with os.fdopen(fd, "w") as f:
            for i in range(5000):           # one line per minute, with a non-timestamp line every 50
                if i % 50 == 0:
                    f.write(json.dumps({"type": "summary"}) + "\n")
                f.write(json.dumps({"timestamp": _iso(self.t0 + i * 60), "n": i, "pad": "x" * 200}) + "\n")

    def tearDown(self):
        os.unlink(self.fp)

    def _ns(self, ls):
        return [json.loads(l)["n"] for l in ls if '"n"' in l]

    def test_window_ends_at_moment(self):
        ns = self._ns(tr._lines_until(self.fp, self.t0 + 2000 * 60, nbytes=60_000, limit=100))
        self.assertTrue(ns)
        self.assertLessEqual(len(ns), 100)
        self.assertIn(2000, ns)              # the line at `at` itself
        self.assertLess(max(ns), 2000 + 80)  # only a short margin after it, never up to EOF
        self.assertEqual(ns, sorted(ns))

    def test_before_start_and_after_end(self):
        early = self._ns(tr._lines_until(self.fp, self.t0 - 999, nbytes=60_000, limit=50))
        self.assertTrue(all(n < 80 for n in early))
        late = self._ns(tr._lines_until(self.fp, self.t0 + 10 ** 7, nbytes=60_000, limit=50))
        self.assertEqual(late[-1], 4999)     # past the end = the plain tail

    def test_missing_file(self):
        self.assertEqual(tr._lines_until("/nonexistent/x.jsonl", self.t0), [])

    def test_open_or_tail_routes_at(self):
        a = self._ns(st._open_or_tail(self.fp, tail=20, at=self.t0 + 100 * 60))
        b = self._ns(st._open_or_tail(self.fp, tail=20))
        self.assertLess(max(a), 200)
        self.assertEqual(b[-1], 4999)


class ToolResults(unittest.TestCase):
    """tool_result blocks ride on `user` lines — they must reach `results` (the popup's «오류 N건» and `⎿`)."""

    def test_error_result_counted(self):
        ts = "2026-10-05T00:00:00.000Z"
        lines = [json.dumps(x) for x in (
            {"type": "assistant", "timestamp": ts, "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "false"}},
                {"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": "/x/a.py"}}]}},
            {"type": "user", "timestamp": ts, "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t1", "is_error": True, "content": "Exit code 1"},
                {"type": "tool_result", "tool_use_id": "t2", "content": [{"type": "text", "text": "ok\nline2"}]},
                {"type": "text", "text": "human words"}]}},
            {"type": "user", "timestamp": ts, "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t3", "is_error": True, "content": ""}]}},
        )]
        (steps, says, results, *_), err = st._work_scan(iter(lines), "/x")
        self.assertIsNone(err)
        self.assertEqual(len(steps), 2)
        self.assertTrue(results["t1"]["err"])
        self.assertEqual(results["t1"]["lines"], ["Exit code 1"])
        self.assertFalse(results["t2"]["err"])
        self.assertTrue(results["t3"]["err"])               # empty error body still counts
        self.assertEqual(says, [])                         # user text is never a «says»


if __name__ == "__main__":
    unittest.main()
