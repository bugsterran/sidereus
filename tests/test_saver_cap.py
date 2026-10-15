"""sidereus/saver_cap.py: concurrency cap formula. Runs, snapshot and burn body are faked — no live files or clock."""
import unittest
from unittest import mock

from tests._load import load, sidereus

load()
sc = sidereus("saver_cap")

NOW = 1_000_000.0
# 6 ended runs at 1.0M tokens/min each (10 min, 10M tokens) -> median 1.0M/min
RUNS = [(NOW - 1800, NOW - 1200, 10_000_000)] * 6


def body(eff=60_000_000, left=600, src="win"):
    # 60M over 10 min = 6M/min, x0.8 SAFETY = 4.8M/min
    return {"ok": True, "cur": {"left": left}, "head": {"eff": eff, "src": src}}


def rows(working=1, subs=0):
    out = [{"state": "tool", "sub": []} for _ in range(working)]
    if subs:
        out.append({"state": "wait", "sub": [{"lab": "x", "min": 1}] * subs})
    return out


class CapT(unittest.TestCase):
    def _cap(self, b, runs=RUNS, snap=None):
        with mock.patch.object(sc, "_ended_runs", lambda now: list(runs)), \
             mock.patch.object(sc, "sessions_snapshot", lambda *a, **k: rows() if snap is None else snap):
            return sc.cap(NOW, b)

    def test_formula(self):
        c = self._cap(body())
        self.assertEqual((c["avail_tpm"], c["per_tpm"], c["per_src"]), (4_800_000, 1_000_000, "meas"))
        self.assertEqual((c["n"], c["running"], c["conf"]), (4, 0, "high"))   # floor(4.8) - 0

    def test_self_session_minus_one(self):
        c = self._cap(body(), snap=rows(working=2, subs=1))   # 2 working mains + 1 sub - self
        self.assertEqual((c["running"], c["n"]), (2, 2))
        self.assertEqual(self._cap(body(), snap=[])["running"], 0)   # clamped at 0

    def test_clamp_0_6(self):
        self.assertEqual(self._cap(body(eff=600_000_000))["n"], 6)
        self.assertEqual(self._cap(body(), snap=rows(working=9))["n"], 0)

    def test_est_fallback(self):
        c = self._cap(body(), runs=RUNS[:4])
        self.assertEqual((c["per_src"], c["per_tpm"]), ("est", sc.PER_TPM_EST))

    def test_low_conf_clamps(self):
        c = self._cap(body(eff=600_000_000, src="anchor"))
        self.assertEqual((c["conf"], c["n"]), ("low", 2))

    def test_left_zero(self):
        self.assertEqual(self._cap(body(left=0))["n"], 0)

    def test_avail_unmeasured_is_none(self):
        # stale body (no head/cur) -> None, not 0; a measured empty headroom stays 0
        c = self._cap({"ok": False, "why": "stale"})
        self.assertEqual((c["avail_tpm"], c["n"]), (None, 0))
        self.assertIsNone(self._cap(body(left=0))["avail_tpm"])
        self.assertEqual(self._cap(body(eff=0))["avail_tpm"], 0)
        self.assertEqual(self._cap({})["n"], 0)

    def test_short_run_floor(self):
        c = self._cap(body(), runs=[(NOW - 1000, NOW - 995, 1_000_000)] * 5)   # 5 s run read as >= 60 s
        self.assertEqual(c["per_tpm"], 1_000_000)


if __name__ == "__main__":
    unittest.main()
