"""Ext platform usage today: 10-min rate and Codex limit windows.
Server side via ext_usage_today with patched scanners (no live files)."""
import unittest

from tests._load import sidereus

ext = sidereus("ext")
NOW = 1_790_000_000.0      # fixed clock, mid-day local time is irrelevant: all messages are within the same day


class Rate10(unittest.TestCase):
    def setUp(self):
        self._tok = dict(ext._tok)
        ext._tok.clear()
        self._mods = dict(ext.PLAT_MODS)
        ext.PLAT_MODS.clear()

    def tearDown(self):
        ext.PLAT_MODS.clear(); ext.PLAT_MODS.update(self._mods)
        ext._tok.clear(); ext._tok.update(self._tok)

    def usage(self, gm_msgs, cx=None):
        class G:
            scan = staticmethod(lambda since=0.0: [{"sid": "g1", "msgs": gm_msgs}])
        ext.PLAT_MODS["gemini"] = G
        if cx is not None:
            class M:
                scan = staticmethod(lambda since=0.0: cx)
            ext.PLAT_MODS["codex"] = M
        return ext.ext_usage_today(NOW)

    def test_window_inside_vs_outside(self):
        u = self.usage({"in": (1000, 100, 500, 0, NOW - 120, "gemini-2.5-flash", 0.02),
                        "edge": (400, 0, 0, 0, NOW - 600, "gemini-2.5-flash", 0.01),
                        "out": (9000, 900, 0, 0, NOW - 601, "gemini-2.5-flash", 0.50),
                        "future": (7, 0, 0, 0, NOW + 60, "gemini-2.5-flash", 0.0)})
        g = u["gm"]
        self.assertEqual(g["rate10"]["tok"], 1600 + 400)
        self.assertAlmostEqual(g["rate10"]["perMin"], 200.0)
        self.assertAlmostEqual(g["rate10"]["cost"], 0.03)
        self.assertEqual(g["rate10"]["win"], 600)
        self.assertEqual(g["tok"], 1600 + 400 + 9900 + 7)        # today's totals untouched by the window

    def test_no_rate_when_quiet(self):
        u = self.usage({"old": (1000, 0, 0, 0, NOW - 3600, "gemini-2.5-flash", 0.1)})
        self.assertNotIn("rate10", u["gm"])
        self.assertEqual(self.usage({}), {})

    def test_unpriced_window(self):
        g = self.usage({"a": (100, 0, 0, 0, NOW - 30, "gemini-x", None)})["gm"]["rate10"]
        self.assertEqual((g["cost"], g["costMiss"]), (None, 1))

    def test_codex_rate_and_limits(self):
        cx = [{"sid": "c1", "msgs": {"k": (300, 30, 0, 0, NOW - 60, "gpt-6-luna", 0.001)},
               "rate": (NOW - 60, {"primary": {"pct": 42.0, "win": 300, "reset": int(NOW + 3600)},
                                   "secondary": {"pct": 18.0, "win": 10080, "reset": int(NOW - 5)}})}]
        u = self.usage({}, cx)
        self.assertEqual(list(u), ["cx"])
        self.assertEqual(u["cx"]["rate10"]["tok"], 330)
        self.assertEqual(list(u["cx"]["rate"]), ["primary"])      # the reset window is dropped



if __name__ == "__main__":
    unittest.main()
