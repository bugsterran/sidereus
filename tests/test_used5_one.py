"""One 5h «used» figure: `burn.used5_peek` (status bar `cur.used_local`) drives usage.block and quotaWho.

`_qburn` is swapped per test and `now` is passed in — no live file, clock or network.
"""
import unittest
from datetime import datetime, timezone

from tests import _load

b = _load.sidereus("burn")
st = _load.sidereus("state")

NOW = 1_800_000_000.0
START = NOW - 3600.0


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


class Used5Case(unittest.TestCase):
    def setUp(self):
        self.saved = dict(b._qburn)
        b._qburn["at"] = NOW - 5
        b._qburn["out"] = {"cur": {"start": START, "reset": START + 18000, "used_local": 220_300_000}}

    def tearDown(self):
        b._qburn.clear()
        b._qburn.update(self.saved)

    def test_peek_reads_cached_used_local(self):
        self.assertEqual(b.used5_peek(NOW), (START, START + 18000, 220_300_000))

    def test_peek_none_when_stale_or_missing(self):
        self.assertIsNone(b.used5_peek(NOW + b.USED5_MAX_AGE + 10))
        b._qburn["out"] = {"cur": {"start": START, "used_local": None}}
        self.assertIsNone(b.used5_peek(NOW))

    def test_same_window_takes_status_bar_figure(self):
        usg = {"block": {"tokens": 223_400_000, "cost": 9.0, "start": _iso(START)}}
        who = {"start": int(START), "total": 223_500_000, "rows": []}
        u2, w2 = st._used5_one(usg, who, NOW)
        self.assertEqual(u2["block"]["tokens"], 220_300_000)
        self.assertEqual(w2["total"], 220_300_000)
        self.assertEqual(usg["block"]["tokens"], 223_400_000)   # inputs not mutated
        self.assertEqual(u2["block"]["cost"], 9.0)

    def test_rows_scaled_to_headline(self):
        rows = [{"name": "a", "tok": 61_500_000, "share": 50.0}, {"name": "b", "tok": 41_000_000, "share": 33.3},
                {"name": "c", "tok": 20_500_001, "share": 16.7}]
        who = {"start": int(START), "total": 123_000_001, "rows": rows}
        _, w2 = st._used5_one(None, who, NOW)
        self.assertEqual(sum(r["tok"] for r in w2["rows"]), 220_300_000)
        self.assertEqual([r["share"] for r in w2["rows"]], [50.0, 33.3, 16.7])
        self.assertEqual(rows[0]["tok"], 61_500_000)   # inputs not mutated
        empty = {"start": int(START), "total": 0, "rows": []}
        self.assertEqual(st._used5_one(None, empty, NOW)[1]["rows"], [])

    def test_rows_with_others_keep_ratio(self):
        who = {"start": int(START), "total": 200, "rows": [{"tok": 100}, {"tok": 50}], "others": 2}
        b._qburn["out"]["cur"]["used_local"] = 400
        _, w2 = st._used5_one(None, who, NOW)
        self.assertEqual([r["tok"] for r in w2["rows"]], [200, 100])

    def test_other_window_left_alone(self):
        usg = {"block": {"tokens": 5, "start": _iso(START - 7200)}}
        who = {"start": int(START - 7200), "total": 6}
        u2, w2 = st._used5_one(usg, who, NOW)
        self.assertEqual((u2["block"]["tokens"], w2["total"]), (5, 6))

    def test_no_cache_keeps_values(self):
        b._qburn["out"] = None
        usg, who = {"block": {"tokens": 5, "start": _iso(START)}}, {"start": int(START), "total": 6}
        self.assertEqual(st._used5_one(usg, who, NOW), (usg, who))
        self.assertEqual(st._used5_one(None, None, NOW), (None, None))


class WhoPiCase(unittest.TestCase):
    """`_who_pi`: pi's Anthropic use joins the primary account's QWHO; `plat_pi.who_5h` is stubbed."""
    def setUp(self):
        self.pi = {}
        self.seen = []
        self._w = st.pi_who_5h
        st.pi_who_5h = lambda start, now: (self.seen.append((start, now)), self.pi)[1]

    def tearDown(self):
        st.pi_who_5h = self._w

    def who(self, acct=""):
        rows = [{"name": "c%d" % i, "tok": 100 - i * 10, "share": 0, "n": 1, "sids": []} for i in range(6)]
        return {"start": int(START), "acct": acct, "total": 600, "rows": rows, "others": 1,
                "othersTok": 600 - sum(r["tok"] for r in rows)}

    def test_primary_adds_pi_row_and_total(self):
        self.pi = {"pp": {"tok": 95, "sids": {"0199aaaa-bbbb-7ccc-8ddd-0000000000c1": 95}}}
        w = st._who_pi(self.who(), NOW)
        self.assertEqual(self.seen, [(float(int(START)), NOW)])
        # ⚠local total excludes pi, so pi adds to it (no rescale of Claude rows)
        self.assertEqual(w["total"], 695)
        self.assertEqual([r["name"] for r in w["rows"]], ["c0", "pp", "c1", "c2", "c3", "c4"])
        p = w["rows"][1]
        self.assertEqual((p["plat"], p["tok"], p["n"], p["sids"]), ("pi", 95, 1, [{"sid": "0199aaaa", "tok": 95}]))
        self.assertEqual(p["share"], round(95 * 100.0 / 695, 1))
        self.assertEqual(w["rows"][0]["tok"], 100)          # Claude rows not rescaled
        self.assertEqual((w["others"], w["othersTok"]), (2, 695 - sum(r["tok"] for r in w["rows"])))
        self.assertEqual(sum(r["tok"] for r in w["rows"]) + w["othersTok"], w["total"])

    def test_extra_account_in_use_also_gets_pi(self):
        self.pi = {"pp": {"tok": 95, "sids": {"s": 95}}}
        w = st._who_pi(self.who("work"), NOW)
        self.assertEqual((w["acct"], w["total"], w["rows"][1]["plat"]), ("work", 695, "pi"))
        self.assertIs(st._who_pi({"acct": "", "total": 5}, NOW).get("rows"), None)   # no start: left alone

    def test_no_pi_use_unchanged(self):
        who = self.who()
        self.assertIs(st._who_pi(who, NOW), who)
        self.assertIsNone(st._who_pi(None, NOW))


if __name__ == "__main__":
    unittest.main()
