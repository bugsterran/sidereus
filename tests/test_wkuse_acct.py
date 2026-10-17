"""Tokens «Period totals» account pick: usage_index._uidx_projects(nd, acct) · burn_usage per-account slots · /api/wkuse acct.

acct="" stays the exact all-accounts path; a pick keeps only files whose account (acct_of, primary -> its label)
matches, lives in its own slot outside `_wkuse_by`/`_wkuse_loop`, and adds no live share. Everything is stubbed.
"""
import json
import os
import threading
import time as _rt
import types
import unittest
from unittest import mock
from urllib.parse import urlparse

from tests._load import sidereus

ui = sidereus("usage_index")
bu = sidereus("burn_usage")
rg = sidereus("routes_get")

NOW = 1_790_000_000.0
H0 = str(int(NOW // 3600) * 3600)
ACCTS = [{"dir": "/h/.claude", "label": "me", "primary": True}, {"dir": "/h/.claude-work", "label": "work", "primary": False}]
FILES = {
    "/p/-a/s1.jsonl": {"sl": "-a", "h": {H0: {"claude-opus-5": [1, 2, 3, 4]}}},
    "/p/-a/s2.jsonl": {"sl": "-a", "h": {H0: {"claude-opus-5": [10, 20, 30, 40]}}},
    "/p/-b/s2/subagents/agent-x.jsonl": {"sl": "-b", "h": {H0: {"claude-sonnet-5": [100, 0, 0, 0]}}},
    "/p/-b/s3.jsonl": {"sl": "-b", "h": {H0: {"claude-sonnet-5": [1000, 0, 0, 0]}}},
}
FILES = {k.replace("/", os.sep): v for k, v in FILES.items()}   # glob gives os.sep paths; sub_sess_dir splits on it
WORK_SIDS = {"s2"}


class _Stop(BaseException):
    pass


def _clock():
    return types.SimpleNamespace(time=lambda: NOW, localtime=_rt.gmtime, strftime=_rt.strftime,
                                 sleep=lambda s: (_ for _ in ()).throw(_Stop()))


def _tot(P):
    return sum(d["totalTokens"] for rows in P.values() for d in rows)


class UidxAcct(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def acct_of(sid, fp):
            self.calls.append(sid)
            return ("work", "/h/.claude-work") if sid in WORK_SIDS else ("", "")
        for name, val in (("_uidx", {"files": json.loads(json.dumps(FILES)), "at": NOW, "loaded": True}),
                          ("_uidx_refresh", lambda max_age=30: (0, 0)), ("time", _clock()),
                          ("acct_of", acct_of), ("accounts", lambda: [dict(a) for a in ACCTS])):
            p = mock.patch.object(ui, name, val)
            p.start()
            self.addCleanup(p.stop)

    def test_all_unchanged(self):
        a = json.dumps(ui._uidx_projects(7), sort_keys=True)
        self.assertEqual(a, json.dumps(ui._uidx_projects(7, ""), sort_keys=True))
        self.assertEqual(self.calls, [])                       # no account lookup on the all path
        self.assertEqual(_tot(json.loads(a)), 1210)

    def test_work_only_work_files(self):
        P = ui._uidx_projects(7, "work")
        self.assertEqual(_tot(P), 100 + 100)                   # s2 main + its subagent (sid from the session dir)
        self.assertEqual(sorted(self.calls), ["s1", "s2", "s3"])

    def test_one_lookup_per_sid_within_period(self):
        ui._uidx["files"]["/p/-c/old.jsonl"] = {"sl": "-c", "h": {str(int(H0) - 40 * 86400): {"x": [5, 0, 0, 0]}}}
        ui._uidx_projects(7, "work")
        self.assertEqual(sorted(self.calls), ["s1", "s2", "s3"])   # s2's subagent reuses s2; "old" is outside 7 days

    def test_primary_label_is_acct_of_empty(self):
        self.assertEqual(_tot(ui._uidx_projects(7, "me")), 10 + 1000)
        self.assertEqual(_tot(ui._uidx_projects(7, "nobody")), 0)


class WkuseAcct(unittest.TestCase):
    def setUp(self):
        for name, val in (("_wkuse_by", {}), ("_wkuse_acct", {}), ("time", _clock()), ("agentcost", lambda: {}),
                          ("_usage", {"live": [(NOW - 50, 1000, 0.1)], "spark": [], "liveby": []}),
                          ("_wkuse_busy_days", set()), ("_WK_NAMES", {}), ("_slug_name", lambda sl: "N" + sl),
                          ("USAGE_LOCAL", True)):
            p = mock.patch.object(bu, name, val)
            p.start()
            self.addCleanup(p.stop)

    def test_live_add_zero_under_pick(self):
        bu._wk_slot(7)["at"] = NOW - 100
        bu._wk_slot(7, "work")["at"] = NOW - 100
        a, w = bu.wkuse(7), bu.wkuse(7, "work")
        self.assertEqual((a["liveAdd"], a["acct"]), (1000, ""))
        self.assertEqual((w["liveAdd"], w["acct"]), (0, "work"))

    def test_fetch_writes_acct_slot_only(self):
        seen = []

        def fake_uidx(nd, acct=""):
            seen.append((nd, acct))
            return {"-a": [{"date": "2026-09-21", "totalTokens": 7, "totalCost": 0.5}]}
        with mock.patch.object(bu, "_uidx_projects", fake_uidx):
            bu._wkuse_fetch(7, "work")
        self.assertEqual(seen, [(7, "work")])
        self.assertEqual(bu._wkuse_by, {})
        self.assertEqual(bu._wkuse_acct[(7, "work")]["total"], 7)

    def test_ccusage_path_refuses_pick(self):
        with mock.patch.object(bu, "USAGE_LOCAL", False), \
                mock.patch.object(bu, "subprocess", None):    # ⚠would raise if ccusage were run
            bu._wkuse_fetch(7, "work")
        self.assertEqual(bu._wkuse_acct[(7, "work")]["err"], bu.WK_ACCT_ERR)

    def test_busy_key_per_account(self):
        st = types.SimpleNamespace(Thread=lambda target, daemon: types.SimpleNamespace(start=lambda: None),
                                   Lock=threading.Lock)
        with mock.patch.object(bu, "threading", st):
            self.assertEqual([bu.wkuse_refresh(7), bu.wkuse_refresh(7, "work"), bu.wkuse_refresh(7, "work")],
                             [True, True, False])

    def test_loop_never_refreshes_acct_slots(self):
        bu._wk_slot(7, "work")["at"] = NOW - 99999
        got = []
        with mock.patch.object(bu, "_wkuse_fetch", lambda *a: got.append(a)):
            with self.assertRaises(_Stop):
                bu._wkuse_loop()
        self.assertEqual(got, [(7,)])                          # only the default all-accounts period

    def test_stale(self):
        self.assertTrue(bu.wk_stale(7, "work"))
        bu._wk_slot(7, "work")["at"] = NOW - 10
        self.assertFalse(bu.wk_stale(7, "work"))
        bu._wk_slot(7, "work")["at"] = NOW - bu.WK_EVERY[7]
        self.assertTrue(bu.wk_stale(7, "work"))


class _H:
    def __init__(self):
        self.out = None

    def _raw_json(self, code, out, cache=True):
        self.out = out


class RouteAcct(unittest.TestCase):
    def get(self, q):
        calls = []
        h = _H()
        with mock.patch.object(rg, "claude_accounts", lambda: [dict(a) for a in ACCTS]), \
                mock.patch.object(rg, "wkuse", lambda d, acct="": {"range": d, "acct": acct}), \
                mock.patch.object(rg, "wkuse_refresh", lambda d, acct="": calls.append((d, acct))), \
                mock.patch.object(rg, "wk_stale", lambda d, acct="": True), \
                mock.patch.object(rg, "_wk_slot", lambda d: {"at": 1.0}):
            rg._GetRoutes._g_wkuse(h, urlparse("/api/wkuse?" + q))
        return h.out["acct"], calls

    def test_unknown_maps_to_all(self):
        self.assertEqual(self.get("range=7&acct=zzz"), ("", []))
        self.assertEqual(self.get("range=7&acct="), ("", []))

    def test_known_label_kept_and_refreshed_when_stale(self):
        self.assertEqual(self.get("range=30&acct=work"), ("work", [(30, "work")]))
        self.assertEqual(self.get("range=7&acct=me"), ("me", [(7, "me")]))


if __name__ == "__main__":
    unittest.main()
