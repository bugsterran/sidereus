"""Rail mark moon phase (web/js/92e-moon.js): age against eclipse syzygies, phase names, path geometry. Runs the file through node."""
import json
import os
import re
import shutil
import subprocess
import unittest
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# no DOM: the file's boot calls (moonPaint, setInterval, listeners) run against inert stubs
STUBS = """
const T = s => s;
const document = {getElementById: () => null, addEventListener() {}, hidden: false};
const setInterval = () => 0, setTimeout = () => 0;
const UIS = {getItem: () => null};
"""


def _src():
    with open(os.path.join(ROOT, "web/js/92e-moon.js"), encoding="utf-8") as f:
        return f.read()


@unittest.skipUnless(shutil.which("node"), "node not installed")
class MoonJs(unittest.TestCase):
    def js(self, expr):
        src = STUBS + _src() + "\nprocess.stdout.write(JSON.stringify(" + expr + "));"
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"))
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        return json.loads(r.stdout)

    def age(self, iso):
        return self.js("moonPhase(Date.parse('%s'))" % iso)

    def test_eclipse_syzygies_within_half_a_day(self):
        P = self.js("MOON_P")
        new = self.age("2024-04-08T18:21:00Z")   # total solar eclipse = new moon
        self.assertLess(min(new["age"], P - new["age"]), 0.5)
        self.assertEqual(new["name"], "New moon")
        for iso in ("2024-09-18T02:34:00Z", "2025-03-14T06:55:00Z", "2026-03-03T11:38:00Z"):   # lunar eclipses = full moon
            ph = self.age(iso)
            self.assertLess(abs(ph["age"] - P / 2), 0.5, iso)
            self.assertEqual(ph["name"], "Full moon", iso)
            self.assertGreater(ph["k"], .99, iso)

    def test_known_day(self):
        ph = self.age("2026-10-12T00:00:00Z")   # new moon 2026-10-10
        self.assertTrue(0 < ph["age"] < 2.5, ph)
        self.assertEqual(ph["name"], "New moon")
        self.assertTrue(ph["waxing"])

    def test_pre_epoch_age_is_positive(self):
        ph = self.age("1969-07-20T20:17:00Z")
        self.assertTrue(0 <= ph["age"] < self.js("MOON_P"), ph)

    def test_path_geometry(self):
        P = self.js("MOON_P")
        self.assertEqual(self.js("moonPath(0.2, 16, 16, 12, 0)"), "")   # k < .01: no lit part
        q = self.js("moonPath(%r, 16, 16, 12, 0)" % (P / 4))
        rx = float(re.search(r"A([\d.]+) 12 0 0 \d 16,4Z$", q).group(1))
        self.assertLess(rx, 0.05)   # first quarter: straight terminator
        # waxing = lit limb on the right (sweep 1 from the top); waning = left (sweep 0)
        self.assertTrue(self.js("moonPath(5, 16, 16, 12, 0)").startswith("M16,4A12 12 0 0 1 16,28"))
        self.assertTrue(self.js("moonPath(22, 16, 16, 12, 0)").startswith("M16,4A12 12 0 0 0 16,28"))
        # crescent terminator bulges toward the lit limb (sweep 0), gibbous away from it (sweep 1)
        self.assertRegex(self.js("moonPath(4, 16, 16, 12, 0)"), r"A[\d.]+ 12 0 0 0 16,4Z$")
        self.assertRegex(self.js("moonPath(11, 16, 16, 12, 0)"), r"A[\d.]+ 12 0 0 1 16,4Z$")
        self.assertIn("A12 12 0 1 1", self.js("moonPath(%r, 16, 16, 12, 0)" % (P / 2)))

    def test_rough_path_stays_in_disc_and_finite(self):
        paths = self.js("[0, .85].flatMap(r => Array.from({length: 30}, (_, a) => moonPath(a + .37, 16, 16, 12, r)))")
        for age, d in enumerate(paths):
            self.assertNotIn("NaN", d)
            self.assertNotIn("Infinity", d)
            for x, y in re.findall(r"L([\d.-]+),([\d.-]+)", d):
                self.assertLessEqual(((float(x) - 16) ** 2 + (float(y) - 16) ** 2) ** .5, 12.01, (age, x, y))
        # same input, same path: the jitter is a fixed table, not random
        self.assertEqual(self.js("moonPath(9, 16, 16, 12, .85)"), self.js("moonPath(9, 16, 16, 12, .85)"))

    def test_peak_only_crescent_to_gibbous(self):
        self.assertIsNone(self.js("moonPeak(0.5, 16, 16, 12)"))
        self.assertIsNone(self.js("moonPeak(14.7, 16, 16, 12)"))
        x, y = self.js("moonPeak(7.38, 16, 16, 12)")   # first quarter: just left of the straight terminator
        self.assertTrue(13 < x < 16 and y == 14.6, (x, y))
        x, _ = self.js("moonPeak(22.15, 16, 16, 12)")   # last quarter: right of it
        self.assertTrue(16 < x < 19, x)

    def test_tooltip_text(self):
        self.assertEqual(self.js("moonTip({name: 'Waxing crescent', age: 3.4, k: .123})"), "Waxing crescent · day 4 · 12% lit")
        self.assertEqual(self.js("moonTitle({name: 'Full moon', age: 14.2, k: .996})"), "Today's moon: Full moon · day 15 · 100% lit")

    def test_hourly_cycle(self):
        # one lunation per hour on the local clock (TZ=UTC here): :00 new, :15 first quarter, :30 full
        P = self.js("MOON_P")
        self.assertEqual(self.js("moonHourAge(Date.parse('2026-10-12T07:00:00Z'))"), 0)
        self.assertAlmostEqual(self.js("moonHourAge(Date.parse('2026-10-12T07:15:00Z'))"), P / 4, 6)
        self.assertAlmostEqual(self.js("moonHourAge(Date.parse('2026-10-12T07:30:00Z'))"), P / 2, 6)
        self.assertEqual(self.js("moonPath(moonHourAge(Date.parse('2026-10-12T07:00:20Z')), 16, 16, 12, 0)"), "")   # new: no lit part
        self.assertIn("A12 12 0 1 1", self.js("moonPath(moonHourAge(Date.parse('2026-10-12T07:30:00Z')), 16, 16, 12, 0)"))
        self.assertLess(self.js("moonHourAge(Date.parse('2026-10-12T07:59:59Z'))"), P)
        self.assertFalse(self.js("moonReal()"))


if __name__ == "__main__":
    unittest.main()
