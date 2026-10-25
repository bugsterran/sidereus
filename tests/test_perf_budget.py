"""scripts/perf_budget.py: p90, budget compare, last line, and the simulated `claude agents` minute (no server, no clock)."""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus  # noqa: F401  (puts the repo on sys.path)
from sidereus import live_probe

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("perf_budget", os.path.join(os.path.dirname(HERE), "scripts", "perf_budget.py"))
pb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pb)

B = {"rss": 100, "warm": 10, "cold": 50, "agents": 2}


class P90(unittest.TestCase):
    def test_nearest_rank(self):
        self.assertEqual(pb.p90([7]), 7)
        self.assertEqual(pb.p90(list(range(10, 0, -1))), 9)      # ceil(9)-1 = index 8
        self.assertEqual(pb.p90(list(range(1, 21))), 18)          # ceil(18)-1 = index 17
        self.assertIsNone(pb.p90([]))


class Compare(unittest.TestCase):
    def test_over_names_value_and_limit(self):
        n, over = pb.compare({"rss": 150, "warm": 5, "cold": 60, "agents": 1}, B)
        self.assertEqual(n, 4)
        self.assertEqual(over, [("rss", 150, 100), ("cold", 60, 50)])

    def test_none_skipped_and_not_counted(self):
        n, over = pb.compare({"rss": None, "warm": 50, "cold": None, "agents": 1}, B)
        self.assertEqual((n, over), (2, [("warm", 50, 10)]))

    def test_all_none_is_failure(self):
        vals = dict.fromkeys(B)
        self.assertEqual(pb.compare(vals, B), (0, []))
        self.assertEqual(pb.exit_code(vals, B), 1)
        self.assertEqual(pb.exit_code({"rss": 1, "warm": 1, "cold": 1, "agents": 1}, B), 0)
        self.assertEqual(pb.exit_code({"rss": 101}, B), 1)

    def test_last_line_format(self):
        ln = pb.last_line({"rss": 98.4, "warm": 12.2, "cold": 340, "agents": 1.0}, {"rss": 200, "warm": 300, "cold": 2000, "agents": 2})
        self.assertEqual(ln, "perf_budget: 4 budgets, 0 over — rss 98MB/200MB · warm p90 12ms/300ms · cold 340ms/2000ms · agents 1/min/2")
        ln = pb.last_line({"rss": None, "warm": 20, "cold": None, "agents": None}, B, {"rss": "skipped (Windows)"})
        self.assertEqual(ln, "perf_budget: 1 budgets, 1 over — rss skipped (Windows) · warm p90 20ms/10ms · cold skipped/50ms · agents skipped/min/2")
        ln = pb.last_line({"warm": 2}, {"warm": 300}, labels={"warm": "warm p90 (cached)"})
        self.assertEqual(ln, "perf_budget: 1 budgets, 0 over — warm p90 (cached) 2ms/300ms")

    def test_demo_time_floors(self):
        self.assertGreaterEqual(pb.DEMO_BUDGETS["warm"], pb.DEMO_FLOORS["warm"])
        self.assertGreaterEqual(pb.DEMO_BUDGETS["cold"], pb.DEMO_FLOORS["cold"])


class AgentsMinute(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "sessions"))
        self._put("s1")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _put(self, sid, pid=None):
        pid = pid or os.getpid()
        with open(os.path.join(self.d, "sessions", "%d.json" % pid), "w", encoding="utf-8") as f:
            json.dump({"pid": pid, "sessionId": sid, "cwd": self.d}, f)

    def test_unchanged_registry_one_spawn(self):
        self.assertEqual(pb.simulate_agents(live_probe, self.d), 1.0)

    def test_registry_change_spawns_again(self):
        done = []

        def tick(t):
            if t >= 30 and not done:
                done.append(t)
                self._put("s2")              # /clear: same pid, new sessionId
        self.assertEqual(pb.simulate_agents(live_probe, self.d, on_tick=tick), 2.0)

    def test_restores_module(self):
        before = (live_probe.time, live_probe.subprocess, live_probe._av_accounts)
        pb.simulate_agents(live_probe, self.d, seconds=5)
        self.assertEqual((live_probe.time, live_probe.subprocess, live_probe._av_accounts), before)


if __name__ == "__main__":
    unittest.main()
