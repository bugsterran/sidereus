"""Primary OMC cache is ignored when another account writes it through a shared `plugins` dir (sidereus/quota.py).

Roots, account uuids, clock and cache paths are patched on `quota`/`quota_roots`/`claude_roots`. Temp dirs only.
"""
import json
import os
import shutil
import tempfile
import types
import unittest

from tests import _load

q = _load.sidereus("quota")
qr = _load.sidereus("quota_roots")
cr = _load.sidereus("claude_roots")

NOW = 1800000000.0


class OmcSharedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.prim = os.path.join(self.tmp, ".claude")
        self.omc = os.path.join(self.prim, "plugins", "oh-my-claudecode")
        os.makedirs(self.omc)
        self.roots = [{"dir": self.prim, "label": "main", "primary": True}]
        self.saved = {}
        self._patch(q, OMC_CACHE=os.path.join(self.omc, ".usage-cache.json"),
                    OMC_CACHE5=os.path.join(self.omc, ".usage-cache-anthropic.json"),
                    time=types.SimpleNamespace(time=lambda: NOW), _cc_account=lambda: "uuid-prim",
                    _omc_trust={"at": 0.0, "foreign": None}, warn_once=lambda *a, **k: None)
        self._patch(qr, _uuid_cache={})
        self._patch(cr, accounts=lambda: [dict(r) for r in self.roots])
        with open(q.OMC_CACHE5, "w", encoding="utf-8") as f:
            json.dump({"timestamp": 1, "data": {"fiveHourPercent": 55, "weeklyPercent": 9}, "error": False}, f)
        os.utime(q.OMC_CACHE5, (NOW - 5, NOW - 5))

    def tearDown(self):
        for (m, k), v in self.saved.items():
            setattr(m, k, v)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _patch(self, mod, **kw):
        for k, v in kw.items():
            self.saved.setdefault((mod, k), getattr(mod, k))
            setattr(mod, k, v)

    def _other(self, uuid, shared):
        d = os.path.join(self.tmp, ".claude-work")
        os.makedirs(d)
        if shared:
            os.symlink(os.path.join(self.prim, "plugins"), os.path.join(d, "plugins"))
        else:
            os.makedirs(os.path.join(d, "plugins", "oh-my-claudecode"))
        with open(os.path.join(d, ".claude.json"), "w", encoding="utf-8") as f:
            json.dump({"oauthAccount": {"accountUuid": uuid}}, f)
        self.roots.append({"dir": d, "label": "work", "primary": False})

    def test_shared_plugins_other_account_ignored(self):
        self._other("uuid-other", shared=True)
        self.assertIsNone(q._quota_from_omc())
        self.assertEqual(q._omc_trust["foreign"], "work")

    def test_shared_foreign_warns_once_across_rechecks(self):
        calls = []
        self._patch(q, warn_once=lambda *a, **k: calls.append(a[0]))
        self._other("uuid-other", shared=True)
        for _ in range(3):
            q._omc_trust["at"] = 0.0          # expire the TTL so each call re-checks
            self.assertEqual(q._omc_shared_foreign(), "work")
        self.assertEqual(calls, ["omc-shared-foreign"])

    def test_shared_plugins_same_account_used(self):
        self._other("uuid-prim", shared=True)
        self.assertEqual(q._quota_from_omc()["data"]["five_hour"]["pct"], 55)

    def test_separate_plugins_used(self):
        self._other("uuid-other", shared=False)
        self.assertEqual(q._quota_from_omc()["data"]["five_hour"]["pct"], 55)

    def _written(self):
        os.remove(q.OMC_CACHE5)
        q._omc_cache_write({"five_hour": {"pct": 12, "resets_at": "r"}, "at": 1})
        return os.path.exists(q.OMC_CACHE5)

    def test_shared_foreign_no_write(self):
        self._other("uuid-other", shared=True)
        self.assertFalse(self._written())

    def test_shared_same_account_writes(self):
        self._other("uuid-prim", shared=True)
        self.assertTrue(self._written())

    def test_separate_plugins_writes(self):
        self._other("uuid-other", shared=False)
        self.assertTrue(self._written())

    def test_single_root_used(self):
        self.assertEqual(q._quota_from_omc()["data"]["five_hour"]["pct"], 55)


if __name__ == "__main__":
    unittest.main()
