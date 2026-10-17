"""burn.quota_burn_acct + `GET /api/quota/burn?dir=`: per-account burn body. Accounts, rows and clock are faked."""
import json
import os
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlparse

from tests._load import sidereus, load

load()
bu = sidereus("burn")
rg = sidereus("routes_get")

NOW = 1_000_000.0
TMP = tempfile.mkdtemp(prefix="sidereus-burnacct-")
PRIM, WORK = os.path.join(TMP, "prim"), os.path.join(TMP, "work")
ACCTS = [{"dir": PRIM, "label": "personal", "primary": True}, {"dir": WORK, "label": "work", "primary": False}]
USE_P = {"label": "personal", "primary": True, "src": "primary"}


def row(pts=None, err=None, pct=30.0):
    fh = {"pct": pct, "resets_at": "x", "leftSec": 7200}
    if pts is not None:
        fh["pts"] = pts
    return {"label": "work", "age": 5, "err": err, "five_hour": fh,
            "seven_day": {"pct": 12.0, "resets_at": "y", "leftSec": 400000}}


class _H:
    def __init__(self):
        self.code, self.out = None, None

    def _raw_json(self, code, out, cache=True):
        self.code, self.out = code, out


class BurnAcct(unittest.TestCase):
    def setUp(self):
        os.makedirs(PRIM, exist_ok=True)
        os.makedirs(WORK, exist_ok=True)
        bu._qb_acct.clear()
        self.addCleanup(bu._qb_acct.clear)
        for obj, name, val in ((bu.time, "time", lambda: NOW), (rg, "claude_accounts", lambda: [dict(a) for a in ACCTS]),
                               (rg, "saver_cap", lambda now, out: {"n": 1}),
                               (rg, "burn_use", lambda: dict(USE_P))):
            p = mock.patch.object(obj, name, val)
            p.start()
            self.addCleanup(p.stop)

    def rows(self, rs):
        p = mock.patch.object(bu, "quota_accounts", lambda: rs)
        p.start()
        self.addCleanup(p.stop)

    def get(self, q=""):
        h = _H()
        with mock.patch.object(rg, "quota_burn", lambda: {"ok": True, "primary": 1}):
            rg._GetRoutes._g_quota_burn(h, urlparse("/api/quota/burn" + ("?" + q if q else "")))
        return h

    def test_no_dir_is_primary(self):
        h = self.get()
        self.assertEqual((h.code, h.out), (200, {"ok": True, "primary": 1, "use": USE_P, "cap": {"n": 1}}))

    def test_primary_dir_same_body(self):
        self.assertEqual(json.dumps(self.get("dir=" + PRIM).out), json.dumps(self.get().out))

    def test_unknown_or_traversal_refused(self):
        for d in (os.path.join(TMP, "nope"), WORK + "/../prim/..", "../", "a\x00b"):
            h = self.get("dir=" + d.replace("\x00", "%00"))
            self.assertEqual((h.code, h.out), (400, {"ok": False}), d)

    def test_non_primary_measured(self):
        self.rows([row(pts=[[int(NOW - 1800), 20.0], [int(NOW - 600), 30.0]])])
        h = self.get("dir=" + WORK + "/")
        b = h.out
        self.assertEqual((h.code, b["ok"], b["acct"]), (200, True, "work"))
        self.assertEqual((b["cur"]["now_pct"], b["cur"]["left"], b["cur"]["rate_src"]), (30.0, 7200, "pts"))
        self.assertGreater(b["cur"]["rate_pph"], 0)
        self.assertEqual(b["wk"], {"now_pct": 12.0, "left": 400000})
        self.assertNotIn(WORK, json.dumps(b))     # metadata only: no dir in the body

    def test_one_point_not_measured(self):
        self.rows([row(pts=[[int(NOW - 600), 30.0]])])
        c = bu.quota_burn_acct("work")
        self.assertEqual((c["ok"], c["cur"]["rate_pph"], c["cur"]["rate_src"]), (True, None, "not measured"))
        self.assertIsNone(c["proj"]["over_at"])
        self.assertEqual((c["proj"]["pct"], c["proj"]["over_in"]), (None, None))

    def test_proj_pct_matches_primary_formula(self):
        pts = [[int(NOW - 1800), 20.0], [int(NOW - 600), 30.0]]
        self.rows([row(pts=pts)])
        p = bu.quota_burn_acct("work")["proj"]
        r, raw, _oa, n = bu._qb_forecast(NOW, [(float(t), h) for t, h in pts], 30.0, 7200.0)
        self.assertTrue(r > 0 and n >= 2)
        self.assertEqual(p["pct"], round(min(100.0, max(0.0, raw)), 1))
        if raw <= 100:
            self.assertEqual((p["over_at"], p["over_in"]), (None, None))

    def test_over_before_reset(self):
        self.rows([row(pts=[[int(NOW - 1800), 50.0], [int(NOW - 600), 90.0]], pct=90.0)])
        p = bu.quota_burn_acct("work")["proj"]
        self.assertEqual(p["pct"], 100.0)
        self.assertTrue(NOW < p["over_at"] < NOW + 7200)
        self.assertEqual(p["over_in"], int(p["over_at"] - NOW))

    def test_full_at_rate_zero(self):
        self.rows([row(pts=[[int(NOW - 1800), 100.0], [int(NOW - 600), 100.0]], pct=100.0)])
        c = bu.quota_burn_acct("work")
        self.assertEqual(c["cur"]["rate_pph"], 0.0)
        self.assertEqual((c["proj"]["over_at"], c["proj"]["over_in"]), (int(NOW - 600), 0))

    def test_full_with_few_pts(self):
        for pts, at in (([[int(NOW - 600), 100.0]], int(NOW - 600)), ([], int(NOW))):
            bu._qb_acct.clear()
            self.rows([row(pts=pts, pct=100.0)])
            c = bu.quota_burn_acct("work")
            self.assertEqual((c["proj"]["over_at"], c["proj"]["over_in"], c["proj"]["pct"]), (at, 0, None))
            self.assertIsNone(c["cur"]["rate_pph"])

    def test_errored_or_missing_row(self):
        self.rows([row(err="HTTPError 429")])
        self.assertEqual(bu.quota_burn_acct("work"), {"ok": False, "why": "not measured"})
        bu._qb_acct.clear()
        self.rows([])
        self.assertEqual(bu.quota_burn_acct("work"), {"ok": False, "why": "not measured"})

    def test_est_from_own_plan_row(self):
        bh = sidereus("burn_hist")
        tab = {"u1": {"h5_per_pct": 9, "h5_n": 1},                    # plan-less legacy row: never picked
               "u1|claude_pro": {"h5_per_pct": None, "wk_per_pct": None},
               "u1|claude_max": {"h5_per_pct": 1000, "h5_n": 22, "wk_per_pct": 5000, "wk_n": 99}}
        for obj, name, val in ((bh, "_hist_get", lambda now: tab), (bh, "_plan_code", lambda: "claude_pro"),
                               (bu.claude_roots, "accounts", lambda: [dict(a) for a in ACCTS])):
            p = mock.patch.object(obj, name, val)
            p.start()
            self.addCleanup(p.stop)
        conf = os.path.join(WORK, ".claude.json")
        self.addCleanup(lambda: os.path.exists(conf) and os.remove(conf))
        self.rows([row(pts=[[int(NOW - 600), 30.0]])])
        self.assertIsNone(bu.quota_burn_acct("work")["est"])      # no .claude.json: no est, as before
        with open(conf, "w", encoding="utf-8") as f:
            json.dump({"oauthAccount": {"accountUuid": "u1", "organizationType": "claude_max"}}, f)
        bu._qb_acct.clear()
        e = bu.quota_burn_acct("work")["est"]
        self.assertEqual((e["h5_per_pct"], e["h5_n"], e["h5_left"]), (1000, 22, 70000))
        self.assertEqual((e["wk_per_pct"], e["wk_left"], e["wk_used"]), (5000, 440000, 60000))
        with open(conf, "w", encoding="utf-8") as f:
            json.dump({"oauthAccount": {"accountUuid": "u1"}}, f)   # plan unknown: no plan-less fallback
        bu._qb_acct.clear()
        self.assertIsNone(bu.quota_burn_acct("work")["est"])


if __name__ == "__main__":
    unittest.main()
