"""agentcost iterates a snapshot of the usage index, not the live dicts a concurrent scan mutates."""
import unittest

from tests._load import sidereus, load

load()
ac = sidereus("agentcost")


class AgcSnapshot(unittest.TestCase):
    def test_snap_is_independent_two_levels(self):
        live = {"100": {"m": [1, 2, 3, 4]}}
        snap = ac._agc_snap(live)
        live["200"] = {"m": [5, 0, 0, 0]}          # scan opens a new hour bucket
        live["100"]["m2"] = [7, 0, 0, 0]           # scan adds a model to the current hour
        self.assertEqual(list(snap), ["100"])
        self.assertEqual(list(snap["100"]), ["m"])
        self.assertEqual(ac._agc_snap(None), {})
        self.assertEqual(ac._agc_snap({"1": "bad"}), {"1": "bad"})   # broken rows pass through; loops skip them

    def test_fetch_survives_concurrent_mutation(self):
        """Mutate the live index from inside the loop (as another thread would): the fetch must not raise."""
        U = sidereus("usage_index")
        fp = "/p/sid1/subagents/agent-a.jsonl"
        live_h = {str(3600 * k): {"m": [10, 0, 0, 0]} for k in range(3)}
        saved = (dict(U._uidx["files"]), ac._uidx_refresh, ac._cost4, ac._agc_type, ac._agc_rows)
        calls = {"n": 0}

        def cost(mdl, v):
            calls["n"] += 1
            live_h[str(10 ** 9 + calls["n"])] = {"m": [1, 0, 0, 0]}   # a scan adding buckets mid-iteration
            return 0.0

        try:
            U._uidx["files"].clear()
            U._uidx["files"][fp] = {"h": live_h, "mt": 1.0}
            ac._uidx_refresh = lambda *a, **k: (0, 0)
            ac._cost4 = cost
            ac._agc_type = lambda fp: "Explore"
            ac._agc_rows = lambda runs, tot: [{"tok": t} for t, _fp in runs]
            ac._agc_fetch()
            self.assertEqual(ac._agc["subtok"], 30)
            self.assertEqual(ac._agc["n"], 1)
        finally:
            U._uidx["files"].clear(); U._uidx["files"].update(saved[0])
            ac._uidx_refresh, ac._cost4, ac._agc_type, ac._agc_rows = saved[1:]
            ac._agc["at"] = 0


if __name__ == "__main__":
    unittest.main()
