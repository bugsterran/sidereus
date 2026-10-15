"""Usage index stores per-request tier (`|long`) and 1h cache-write (`|1h`) keys; display merges them by model."""
import json
import os
import shutil
import tempfile
import time
import types
import unittest
from unittest import mock

from tests._load import sidereus, load

load()
U = sidereus("usage_index")
H = sidereus("history")

T0 = 1_899_997_200            # fixed on-the-hour epoch; nothing reads the clock
HK = "claude-haiku-5-5"


def _clock(mod):
    """Module-local `time` stand-in pinned to T0 (other attributes pass through)."""
    ns = types.SimpleNamespace(**{k: getattr(time, k) for k in dir(time) if not k.startswith("_")})
    ns.time = lambda: T0 + 1800
    return mock.patch.object(mod, "time", ns)


def _line(i, model, inp, cc=0, cr=0, out=7, h1=None):
    u = {"input_tokens": inp, "output_tokens": out, "cache_creation_input_tokens": cc, "cache_read_input_tokens": cr}
    if h1 is not None:
        u["cache_creation"] = {"ephemeral_5m_input_tokens": cc - h1, "ephemeral_1h_input_tokens": h1}
    ts = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(T0 + 60 + i))
    return json.dumps({"type": "assistant", "timestamp": ts, "requestId": "r%d" % i,
                       "message": {"id": "m%d" % i, "model": model, "usage": u}}) + "\n"


class UidxTier(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-uidx-tier-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fp = os.path.join(self.tmp, "-proj", "s1.jsonl")
        os.makedirs(os.path.dirname(self.fp))
        self.idx = os.path.join(self.tmp, "usage-index.json")
        for p in (mock.patch.object(U, "USAGE_INDEX", self.idx),
                  mock.patch.object(U, "_uidx_paths", lambda: [(self.fp, "-proj")]),
                  mock.patch.dict(U._uidx, {"files": {}, "at": 0.0, "loaded": False}, clear=True),
                  _clock(U)):
            p.start()
            self.addCleanup(p.stop)

    def _write(self, *lines):
        with open(self.fp, "w") as f:
            f.write("".join(lines))

    def _keys(self):
        U._uidx_refresh(max_age=0)
        h = U._uidx["files"][self.fp]["h"]
        self.assertEqual(len(h), 1)
        return next(iter(h.values()))

    def test_two_tiers_same_hour(self):
        self._write(_line(1, HK, 50_000), _line(2, HK, 150_000))
        mm = self._keys()
        self.assertEqual(mm, {HK: [50_000, 7, 0, 0], HK + "|long": [150_000, 7, 0, 0]})
        cost = sum(U._cost4(k, v) for k, v in mm.items())
        self.assertAlmostEqual(cost, (50_000 * 0.10 + 7 * 0.50 + 150_000 * 0.50 + 7 * 2.50) / 1e6)

    def test_one_hour_cache_split_keeps_tokens(self):
        self._write(_line(1, "claude-opus-5-5", 10, cc=3000, cr=40, h1=1000), _line(2, "claude-opus-5-5", 5, cc=20))
        mm = self._keys()
        self.assertEqual(mm, {"claude-opus-5-5": [15, 14, 2020, 40], "claude-opus-5-5|1h": [0, 0, 1000, 0]})
        self.assertEqual(sum(sum(v) for v in mm.values()), 15 + 14 + 3020 + 40)
        self.assertAlmostEqual(U._cost4("claude-opus-5-5|1h", mm["claude-opus-5-5|1h"]), 1000 * 8 / 1e6)

    def test_old_index_version_rescans(self):
        self._write(_line(1, HK, 150_000))
        st = os.stat(self.fp)
        stale = {"sl": "-proj", "off": st.st_size, "sz": st.st_size, "mt": st.st_mtime, "tv": U.UIDX_META_V,
                 "h": {str(T0): {HK: [150_000, 7, 0, 0]}}}
        with open(self.idx, "w") as f:
            json.dump({"v": 1, "files": {self.fp: stale}}, f)
        self.assertEqual(self._keys(), {HK + "|long": [150_000, 7, 0, 0]})
        with open(self.idx) as f:
            self.assertEqual(json.load(f)["v"], U.UIDX_V)

    def test_breakdown_and_history_merge_by_model(self):
        self._write(_line(1, HK, 50_000), _line(2, HK, 150_000, cc=2000, h1=2000))
        U._uidx_refresh(max_age=0)
        rows = U._uidx_projects(1)["-proj"]
        self.assertEqual(len(rows), 1)
        bd = rows[0]["modelBreakdowns"]
        self.assertEqual([b["modelName"] for b in bd], [HK])
        self.assertEqual(bd[0]["inputTokens"], 200_000)
        self.assertEqual(bd[0]["cacheCreationTokens"], 2000)
        want = (50_000 * 0.10 + 7 * 0.50 + 150_000 * 0.50 + 7 * 2.50 + 2000 * 1.0) / 1e6
        self.assertAlmostEqual(bd[0]["cost"], want)
        self.assertAlmostEqual(rows[0]["totalCost"], want)
        with _clock(H), mock.patch.object(H, "_uidx_refresh", lambda *a, **k: (0, 0)), \
                mock.patch.object(H, "_cwd_from_slug", lambda s: "/x/proj"), \
                mock.patch.object(H, "PLAT_MODS", {}), mock.patch.dict(H._hist_cache, {}, clear=True):
            out = H.history(1)
        r = out["list"][0]["rows"][0]
        self.assertEqual(r["models"], 1)
        self.assertEqual(r["tok"], 200_000 + 14 + 2000)
        self.assertAlmostEqual(r["cost"], round(want, 4))


if __name__ == "__main__":
    unittest.main()
