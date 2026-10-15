"""sidereus/routes_get.hook_state — quota subset for saver.py. No live files: quota() is monkeypatched."""
import unittest
from tests._load import sidereus, load

rg = sidereus("routes_get")

FULL = {"at": 100, "age": 5, "err": None, "src": "api",
        "five_hour": {"pct": 42, "resets_at": "2026-09-25T12:00:00Z", "leftSec": 3600, "keptAt": 9},
        "seven_day": {"pct": 17.5, "resets_at": "2026-09-30T00:00:00Z", "leftSec": 400000},
        "extra": {"seat": "x", "age": 1}}


class HookState(unittest.TestCase):
    def patch(self, val):
        old = rg.quota
        rg.quota = lambda: val
        self.addCleanup(setattr, rg, "quota", old)

    def test_subset_same_values(self):
        self.patch(FULL)
        self.assertEqual(rg.hook_state(), {"ok": True, "quota": {
            "five_hour": {"pct": 42, "leftSec": 3600}, "seven_day": {"pct": 17.5, "leftSec": 400000}}})

    def test_hook_reads_match_state_quota(self):
        self.patch(FULL)
        h = rg.hook_state()["quota"]
        for k in ("five_hour", "seven_day"):
            for f in ("pct", "leftSec"):
                self.assertEqual(h[k][f], FULL[k][f])

    def test_missing_slot_stays_missing(self):
        self.patch({"at": 1, "age": 0, "err": None, "src": "api", "five_hour": {"pct": 3, "leftSec": None}})
        self.assertEqual(rg.hook_state()["quota"], {"five_hour": {"pct": 3, "leftSec": None}})

    def test_no_data(self):
        self.patch({"err": "boom"})
        self.assertEqual(rg.hook_state(), {"ok": True, "quota": {}})

    def test_route_registered(self):
        cs = load()
        self.assertIs(cs.Handler._GET_ROUTES["/api/hookstate"], rg._GetRoutes._g_hookstate)


if __name__ == "__main__":
    unittest.main()
