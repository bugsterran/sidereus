"""Account in use for the modal burndown and the saver cap: burn.burn_use, the `use`/`cap` route fields,
saver_cap's non-primary fallback and the page's burnUse/burnDraw/burnAcctCur/burnIdle. Accounts, logs, prefs and clock are faked."""
import json
import os
import shutil
import subprocess
import unittest
from unittest import mock
from urllib.parse import urlparse

from tests._load import js_fn, load, sidereus
from tests._node import node_e
from tests.test_saver_quota_js import i18n, jconst

load()
bu = sidereus("burn")
rg = sidereus("routes_get")
sc = sidereus("saver_cap")
cr = sidereus("claude_roots")
up = sidereus("ui_prefs")

NOW = 1_000_000.0
ONE = [{"dir": "/p", "label": "me", "primary": True}]
TWO = ONE + [{"dir": "/w", "label": "work", "primary": False}]


class BurnUse(unittest.TestCase):
    def use(self, accts=TWO, prim=(), ring=None, prefs=None):
        """prim: [(t, h5, reset)] quota-log rows; ring: {label: (reset5, last t)}."""
        with mock.patch.object(cr, "accounts", lambda: [dict(a) for a in accts]), \
             mock.patch.object(up, "load", lambda: prefs), \
             mock.patch.object(bu, "_qburn_pts", lambda: list(prim)), \
             mock.patch.object(bu, "ring_last", lambda: dict(ring or {})):
            return bu.burn_use(NOW)

    def test_r4_single_account_is_primary(self):
        u = self.use(accts=ONE, prim=[(NOW - 60, 10.0, NOW + 3600)], ring={"work": (NOW + 3600, NOW - 1)})
        self.assertEqual(u, {"label": "me", "primary": True, "src": "primary"})

    def test_r2_only_other_live(self):
        u = self.use(prim=[(NOW - 60, 4.0, NOW - 10)], ring={"work": (NOW + 3600, NOW - 600)})
        self.assertEqual(u, {"label": "work", "primary": False, "src": "live"})

    def test_r2_newest_live_sample_wins(self):
        p = [(NOW - 300, 10.0, NOW + 3600)]
        self.assertEqual(self.use(prim=p, ring={"work": (NOW + 3600, NOW - 100)})["label"], "work")
        self.assertTrue(self.use(prim=p, ring={"work": (NOW + 3600, NOW - 900)})["primary"])
        self.assertTrue(self.use(prim=p, ring={"work": (NOW + 3600, NOW - 300)})["primary"])   # tie -> primary

    def test_r2_none_live_or_stale_ring(self):
        self.assertTrue(self.use(prim=[(NOW - 60, 4.0, NOW - 10)], ring={"work": (NOW - 5, NOW - 60)})["primary"])
        self.assertTrue(self.use(ring={"gone": (NOW + 3600, NOW - 1)})["primary"])   # label not an account

    def test_explicit_main_wins(self):
        p = [(NOW - 10, 10.0, NOW + 3600)]
        self.assertEqual(self.use(prim=p, prefs={"mbMainAcct": "work"}), {"label": "work", "primary": False, "src": "main"})
        self.assertTrue(self.use(prim=p, prefs={"mbMainAcct": "nope"})["primary"])
        self.assertTrue(self.use(accts=ONE, prim=p, prefs={"mbMainAcct": "work"})["primary"])


class _H:
    def __init__(self):
        self.code, self.out = None, None

    def _raw_json(self, code, out, cache=True):
        self.code, self.out = code, out


class Route(unittest.TestCase):
    def get(self, use, q="", peek=True):
        seen, calls = [], []
        prim, work = {"ok": False, "why": "stale"}, {"ok": True, "acct": "work", "cur": {"now_pct": 12.0}}
        self.calls = calls
        with mock.patch.object(rg, "burn_use", lambda: dict(use)), \
             mock.patch.object(rg, "quota_burn", lambda: calls.append(1) or prim), \
             mock.patch.object(rg, "quota_burn_peek", lambda: prim if peek else None), \
             mock.patch.object(rg, "quota_burn_acct", lambda lab: work), \
             mock.patch.object(rg, "claude_accounts", lambda: [dict(a) for a in TWO]), \
             mock.patch.object(rg, "_acct_of_dir", lambda d: next((a for a in TWO if a["dir"] == d), None)), \
             mock.patch.object(rg, "saver_cap", lambda now, b: seen.append(b) or {"n": 0}):
            h = _H()
            rg._GetRoutes._g_quota_burn(h, urlparse("/api/quota/burn" + q))
        return h.out, seen[0]

    def test_r1_r3_cap_and_use_follow_live_account(self):
        u = {"label": "work", "primary": False, "src": "live"}
        out, capb = self.get(u)
        self.assertEqual((out["why"], out["use"]), ("stale", u))   # no-dir body stays the primary's (hook unchanged)
        self.assertEqual(capb["acct"], "work")
        out, capb = self.get(u, "?dir=/w")
        self.assertEqual((out["acct"], capb["acct"]), ("work", "work"))

    def test_r4_primary_in_use(self):
        u = {"label": "me", "primary": True, "src": "primary"}
        out, capb = self.get(u)
        self.assertEqual(capb.get("why"), "stale")
        out, capb = self.get(u, "?dir=/w")
        self.assertEqual((out["acct"], capb.get("why"), self.calls), ("work", "stale", []))   # cache only, no scan
        out, capb = self.get(u, "?dir=/w", peek=False)
        self.assertEqual((capb["acct"], self.calls), ("work", []))   # cold primary cache: cap from the asked body


class CapFallback(unittest.TestCase):
    def cap(self, b):
        with mock.patch.object(sc, "_per_tpm", lambda now: (1_000_000.0, "meas")), \
             mock.patch.object(sc, "sessions_snapshot", lambda *a, **k: []):
            return sc.cap(NOW, b)

    def test_non_primary_uses_history_left(self):
        c = self.cap({"ok": True, "acct": "work", "cur": {"left": 6000}, "est": {"h5_left": 300_000_000, "wk_left": 200_000_000}})
        self.assertEqual((c["avail_tpm"], c["conf"]), (1_600_000, "low"))   # 200M / 100 min * 0.8

    def test_primary_without_head_unchanged(self):
        self.assertIsNone(self.cap({"ok": True, "cur": {"left": 6000}, "est": {"h5_left": 3e8}})["avail_tpm"])


class AcctBody(unittest.TestCase):
    def test_curve_fields(self):
        fh = {"pct": 30.0, "leftSec": 7200, "pts": [[int(NOW - 1800), 20.0], [int(NOW - 600), 30.0]]}
        row = {"label": "work", "age": 5, "err": None, "five_hour": fh}
        bu._qb_acct.clear()
        self.addCleanup(bu._qb_acct.clear)
        with mock.patch.object(bu, "quota_accounts", lambda: [row]), mock.patch.object(bu.time, "time", lambda: NOW), \
             mock.patch.object(bu, "_qb_acct_key", lambda lab: None):
            b = bu.quota_burn_acct("work")
        self.assertEqual((b["cur"]["pts"], b["cur"]["age"]), (fh["pts"], 5))
        self.assertIsNotNone(b["proj"]["raw"])
        for k in ("start", "reset", "elapsed"):
            self.assertNotIn(k, b["cur"])


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Page(unittest.TestCase):
    def test_r1_r3_draw_follows_use(self):
        fns = ("acctList", "mainAcct", "mainAcctOk", "burnMainDir", "burnUse", "burnDraw", "burnAcctCur", "burnIdle")
        src = ("var document = {getElementById: () => null};\n"
               "let ACCTS = [], STORE = {}, BURNM = null, BURNM_DIR = '', BURN = {ok: false, why: 'stale', use: {label: 'me', primary: true}};\n"
               "const UIS = {getItem: k => k in STORE ? STORE[k] : null};\n"
               + i18n() + "\n" + jconst("esc") + "\n" + "\n".join(js_fn(f) for f in fns) + "\nconst R = {};\nLANG = 'en';\n"
               + r"""
R.one = [burnUse(), burnDraw() === BURN];
ACCTS = [{label: 'me', primary: true, dir: '/p'}, {label: 'w<b>', dir: '/w'}];
BURN.use = {label: 'w<b>', primary: false};
R.loading = [burnUse(), burnDraw()];
BURNM_DIR = '/w'; BURNM = {ok: true, at: 10000, acct: 'w<b>', cur: {now_pct: 12, left: 3600, pts: [[8000, 10], [9000, 12]]}};
const d = burnDraw();
R.drawn = [d.cur.reset, d.cur.start, d.cur.elapsed, d.cur.pts.length, BURNM.cur.reset === undefined];
R.idle = burnIdle(burnUse().label);
STORE.mbMainAcct = 'w<b>'; BURN.use = {label: 'me', primary: true};
R.main = burnUse();
""" + "\nprocess.stdout.write(JSON.stringify(R));")
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"))
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        R = json.loads(r.stdout)
        self.assertEqual(R["one"], [{"label": "", "dir": ""}, True])
        self.assertEqual(R["loading"], [{"label": "w<b>", "dir": "/w"}, None])
        self.assertEqual(R["drawn"], [13600, 13600 - 18000, 10000 - (13600 - 18000), 2, True])
        self.assertIn("w&lt;b&gt;", R["idle"])
        self.assertNotIn("<b>", R["idle"])
        self.assertEqual(R["main"], {"label": "w<b>", "dir": "/w"})


if __name__ == "__main__":
    unittest.main()
