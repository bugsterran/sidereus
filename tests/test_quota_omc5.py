"""OMC 3.x (`.usage-cache.json`) and 5.x (`.usage-cache-anthropic.json`) quota cache sharing (sidereus/quota.py).

Both paths are redirected into a temp dir; the quota clock and file mtimes use the fixed epoch NOW.
"""
import json
import os
import tempfile
import types
import unittest

from tests import _load

q = _load.sidereus("quota")

NOW = 1800000000.0

OUT = {"five_hour": {"pct": 42, "resets_at": "r5"}, "seven_day": {"pct": 7, "resets_at": "r7"}, "at": 1700000000}


class OmcCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "oh-my-claudecode")
        self.saved = (q.OMC_CACHE, q.OMC_CACHE5, q.time)
        q.time = types.SimpleNamespace(time=lambda: NOW)
        q.OMC_CACHE = os.path.join(self.dir, ".usage-cache.json")
        q.OMC_CACHE5 = os.path.join(self.dir, ".usage-cache-anthropic.json")

    def tearDown(self):
        q.OMC_CACHE, q.OMC_CACHE5, q.time = self.saved
        self.tmp.cleanup()

    def _put(self, path, obj, age=0):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f)
        t = NOW - age
        os.utime(path, (t, t))

    def _ok(self, pct, **extra):
        c = {"timestamp": 1, "data": {"fiveHourPercent": pct, "weeklyPercent": 1}, "error": False}
        c.update(extra)
        return c

    def test_write_both_identical(self):
        os.mkdir(self.dir)
        q._omc_cache_write(OUT)
        with open(q.OMC_CACHE, "rb") as f:
            a = f.read()
        with open(q.OMC_CACHE5, "rb") as f:
            b = f.read()
        self.assertEqual(a, b)
        c = json.loads(a.decode("utf-8"))
        self.assertEqual(c["source"], "anthropic")
        self.assertEqual(c["lastSuccessAt"], OUT["at"] * 1000)
        self.assertEqual(c["data"]["fiveHourPercent"], 42)
        self.assertTrue(c["sidereus"])
        for k in ("rateLimited", "rateLimitBackoffs", "errorReason", "credentialIdentity"):
            self.assertNotIn(k, c)

    def test_no_plugin_dir_no_files(self):
        q._omc_cache_write(OUT)
        self.assertFalse(os.path.exists(self.dir))

    def test_fresher_file_wins(self):
        os.mkdir(self.dir)
        self._put(q.OMC_CACHE, self._ok(30), age=60)
        self._put(q.OMC_CACHE5, self._ok(50, source="anthropic"), age=5)
        self.assertEqual(q._quota_from_omc()["data"]["five_hour"]["pct"], 50)
        self._put(q.OMC_CACHE, self._ok(31), age=1)
        self.assertEqual(q._quota_from_omc()["data"]["five_hour"]["pct"], 31)

    def test_unusable_ignored(self):
        os.mkdir(self.dir)
        self._put(q.OMC_CACHE, self._ok(30), age=60)
        for bad in (self._ok(90, sidereus=True), self._ok(90, error=True),
                    self._ok(90, rateLimited=True), self._ok(90, source="zai")):
            self._put(q.OMC_CACHE5, bad, age=1)
            self.assertEqual(q._quota_from_omc()["data"]["five_hour"]["pct"], 30)
        os.remove(q.OMC_CACHE)
        self.assertIsNone(q._quota_from_omc())

    def test_non_dict_top(self):
        os.mkdir(self.dir)
        self._put(q.OMC_CACHE5, [1, 2])
        self.assertIsNone(q._quota_from_omc())


if __name__ == "__main__":
    unittest.main()
