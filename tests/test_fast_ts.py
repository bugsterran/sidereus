"""timeline._fast_ts must equal the per-line strptime parse (_line_ts) for every input, including malformed ones."""
import random
import unittest

from tests._load import sidereus

tl = sidereus("timeline")
tr = sidereus("transcript")


def old(ts):
    return tr._line_ts({"timestamp": ts}, 0)


class FastTs(unittest.TestCase):
    def test_matches_old_parser_over_a_year(self):
        rnd = random.Random(7)
        for _ in range(20000):
            ts = "2026-%02d-%02dT%02d:%02d:%02d.%03dZ\",\"x" % (
                rnd.randint(1, 12), rnd.randint(1, 28), rnd.randint(0, 23), rnd.randint(0, 59), rnd.randint(0, 59), rnd.randint(0, 999))
            self.assertEqual(tl._fast_ts(ts[:24]), old(ts[:24]), ts)

    def test_malformed_same_fallback(self):
        for ts in ["", "2026-09-24", "2026-09-24T12:3", "2026-09-24T25:00:00.000Z", "2026-09-24T12:60:00Z",
                   "2026-09-24T12:00:60Z", "2026-02-30T01:00:00Z", "2026-09-24T12:0a:00Z", "2026-09-24T12:0²:00Z",
                   "2026-09-24 12:00:00Z", "abcd-ef-ghTij:kl:mn"]:
            self.assertEqual(tl._fast_ts(ts), old(ts), ts)


if __name__ == "__main__":
    unittest.main()
