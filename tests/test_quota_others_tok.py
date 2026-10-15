"""«그 외 N» carries the cut projects' tokens (`othersTok`): rows + othersTok == total, before and after
`state._used5_one` rescales onto the shared 5h figure. Module dicts swapped per test; `now` passed in."""
import unittest
from datetime import datetime, timezone

from tests import _load

u = _load.sidereus("usage")
b = _load.sidereus("burn")
st = _load.sidereus("state")

NOW = 1_800_000_000.0
H = 3600.0


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


class OthersTok(unittest.TestCase):
    def setUp(self):
        self.saved = (u._usage, u._sid_proj, dict(b._qburn))
        u._usage = {"live": [], "spark": [], "liveby": [], "bycSeed": {"done": False}}
        u._sid_proj = {}
        for i in range(9):   # 9 projects, top 6 shown
            sid = "%08d-x" % i
            u._sid_proj[sid] = "p%d" % i
            u._usage_add(NOW - 60 - i, 1000 + 7 * i, 0, sid)

    def tearDown(self):
        u._usage, u._sid_proj = self.saved[0], self.saved[1]
        b._qburn.clear()
        b._qburn.update(self.saved[2])

    def who(self):
        return u.quota_who({"five_hour": {"resets_at": _iso(NOW + 2 * H)}}, now=NOW)

    def test_rows_plus_others_tok_is_total(self):
        w = self.who()
        self.assertEqual((len(w["rows"]), w["others"]), (6, 3))
        self.assertEqual(w["othersTok"], 1000 + 1007 + 1014)
        self.assertEqual(sum(r["tok"] for r in w["rows"]) + w["othersTok"], w["total"])

    def test_invariant_after_rescale(self):
        w = self.who()
        b._qburn["at"] = NOW - 5
        b._qburn["out"] = {"cur": {"start": w["start"], "reset": w["start"] + 18000, "used_local": 1_234_567}}
        _, w2 = st._used5_one(None, w, NOW)
        self.assertEqual(w2["total"], 1_234_567)
        self.assertEqual(sum(r["tok"] for r in w2["rows"]) + w2["othersTok"], 1_234_567)
        self.assertGreater(w2["othersTok"], 0)


if __name__ == "__main__":
    unittest.main()
