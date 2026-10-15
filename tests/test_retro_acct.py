"""retro(days, acct, key): the account pick redraws only the six OTel cards; All stays byte-identical.

No live files, clock or git: the retro module's inputs are patched, and `_oa_snap` returns a fixed account snapshot.
"""
import unittest
from unittest import mock

from tests._load import sidereus
from tests.test_retro import CACHE, COMMITS, EVS, HEAT, HIST, HOOKS, MODELS, NOW, RANK, TOOLS

R = sidereus("retro")
SNAP = {"t": {"2026-09-20": {"Bash": [3, 1, 30.0, 3, 10.0]}}, "s": {}, "c": {}, "h": {"2026-09-20": {"Stop": [2, 8, 0]}}}
OTEL_KEYS = {"rank", "time", "cache", "heat", "models", "hooks"}


class RetroAcctTests(unittest.TestCase):
    def setUp(self):
        R._retro_cache.clear()
        self.addCleanup(R._retro_cache.clear)
        self.snap_keys = []
        pats = [mock.patch.object(R, "history", return_value=HIST),
                mock.patch.object(R, "_fail_events", return_value=(EVS, 3, 168)),
                mock.patch.object(R, "_retro_commits", return_value=COMMITS),
                mock.patch.object(R, "_otel_tools_summary", return_value=TOOLS),
                mock.patch.object(R, "_otel_tool_rank", side_effect=lambda sd, src=None: RANK if src is None
                                  else {"top": [{"n": "Bash", "calls": 3}], "calls": 3, "time": {"rows": []}}),
                mock.patch.object(R, "_oc_view", side_effect=lambda sd, src=None: CACHE if src is None
                                  else {"days": [], "sessions": []}),
                mock.patch.object(R, "_otel_src_heat", side_effect=lambda a, b, src=None: HEAT if src is None
                                  else {"n": 0}),
                mock.patch.object(R, "_otel_src_models", side_effect=lambda a, b, src=None: MODELS if src is None
                                  else {"n": 0, "rows": []}),
                mock.patch.object(R, "_oh_view", side_effect=lambda sd, src=None: HOOKS if src is None
                                  else {"rows": [], "n": 2, "from": ""}),
                mock.patch.object(R, "_oa_snap", side_effect=lambda k: self.snap_keys.append(k) or (SNAP, int(NOW))),
                mock.patch.object(R.time, "time", return_value=NOW)]
        for p in pats:
            p.start()
            self.addCleanup(p.stop)

    def test_all_body_unchanged_and_has_no_acct_key(self):
        o = R.retro(7)
        self.assertNotIn("acct", o)
        self.assertNotIn("acctSince", o)
        self.assertIs(o["rank"], RANK)
        self.assertIs(R.retro(7, ""), o)

    def test_pick_swaps_only_the_six_otel_keys(self):
        a = R.retro(7)
        p = R.retro(7, "work")
        self.assertEqual(set(p) - set(a), {"acct", "acctSince"})
        changed = {k for k in a if a[k] != p[k]}
        self.assertTrue(changed <= OTEL_KEYS, changed)
        self.assertEqual(p["rank"]["calls"], 3)
        self.assertEqual(p["hooks"]["n"], 2)
        self.assertEqual((p["acct"], p["acctSince"]), ("work", R._rt_day(NOW)))
        self.assertEqual(p["tools"], a["tools"])               # «Tools failing most» stays All
        self.assertIs(a["rank"], RANK)                         # the All body is not mutated by the pick
        self.assertEqual(self.snap_keys, ["work"])

    def test_primary_label_uses_key_empty(self):
        R.retro(7, "me", "")
        self.assertEqual(self.snap_keys, [""])

    def test_cache_keyed_by_account(self):
        p = R.retro(7, "work")
        self.assertIs(R.retro(7, "work"), p)
        self.assertEqual(self.snap_keys, ["work"])
        q = R.retro(7, "other")
        self.assertIsNot(q, p)
        self.assertEqual(set(R._retro_cache), {(7, ""), (7, "work"), (7, "other")})
        R.history.assert_called_once_with(7)                   # one All build feeds every pick


class RouteAcctTests(unittest.TestCase):
    """`_g_retro` accepts only a known label; the primary maps to key ""."""
    G = sidereus("routes_get")

    def _get(self, query):
        out = {}
        h = type("H", (), {"_raw_json": lambda self, code, body: out.update(code=code, body=body)})()
        u = type("U", (), {"query": query})()
        accts = [{"dir": "/c/m", "label": "me", "primary": True}, {"dir": "/c/w", "label": "work", "primary": False}]
        with mock.patch.object(self.G, "claude_accounts", return_value=accts), \
             mock.patch.object(self.G, "retro", return_value={"ok": True}) as r:
            self.G._GetRoutes._g_retro(h, u)
        return r.call_args[0]

    def test_unknown_label_is_all(self):
        self.assertEqual(self._get("days=7&acct=zzz"), ("7",))
        self.assertEqual(self._get("days=7"), ("7",))

    def test_known_labels(self):
        self.assertEqual(self._get("days=30&acct=work"), ("30", "work", "work"))
        self.assertEqual(self._get("days=7&acct=me"), ("7", "me", ""))


if __name__ == "__main__":
    unittest.main()
