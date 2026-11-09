"""A non-primary root signed in to the primary's own account is the primary's 5h window: quota_roots.same_labels,
state._accts `same`, burn.burn_use, burn.quota_burn_acct and the page's mainAcctOk. Accounts, uuids and clock are faked."""
import json
import os
import shutil
import subprocess
import unittest
from unittest import mock

from tests._load import js_fn, load, sidereus
from tests._node import node_e

load()
qr = sidereus("quota_roots")
bu = sidereus("burn")
st = sidereus("state")
cr = sidereus("claude_roots")
up = sidereus("ui_prefs")

NOW = 1_000_000.0
ACCTS = [{"dir": "/p", "label": "me", "primary": True}, {"dir": "/m", "label": "myacct", "primary": False},
         {"dir": "/w", "label": "work", "primary": False}]
UIDS = {"/p": "U1", "/m": "U1", "/w": "U2"}


class SameAcct(unittest.TestCase):
    def setUp(self):
        for obj, name, val in ((cr, "accounts", lambda: [dict(a) for a in ACCTS]),
                               (st, "claude_accounts", lambda: [dict(a) for a in ACCTS]),
                               (qr, "_root_uuid", lambda d: UIDS.get(d)),
                               (qr, "_cc_account", lambda: "U1")):
            p = mock.patch.object(obj, name, val)
            p.start()
            self.addCleanup(p.stop)

    def test_same_labels(self):
        self.assertEqual(qr.same_labels(), {"myacct"})
        with mock.patch.object(qr, "_cc_account", lambda: None):   # unknown primary is not «same»
            self.assertEqual(qr.same_labels(), set())
        with mock.patch.object(qr, "_root_uuid", lambda d: None if d == "/m" else UIDS.get(d)):   # unknown extra uuid
            self.assertEqual(qr.same_labels(), set())

    def test_agent_brief_same_is_primary(self):
        ab = sidereus("agent_brief")
        q = {"age": 3, "five_hour": {"pct": 55.0, "resets_at": "x", "leftSec": 7000}, "seven_day": {}}
        with mock.patch.object(ab, "claude_accounts", lambda: [dict(a) for a in ACCTS]), \
             mock.patch.object(ab, "same_labels", qr.same_labels), \
             mock.patch.object(ab, "quota", lambda: q), mock.patch.object(ab, "quota_accounts", lambda: []), \
             mock.patch.object(ab, "quota_burn", lambda: {"cur": {"used_local": 9}, "proj": {"over_at": 2000}}), \
             mock.patch.object(ab, "quota_burn_acct", lambda lab: {"ok": False, "why": "not measured"}), \
             mock.patch.object(ab, "_saver_view", lambda: {}), mock.patch.object(ab, "_saver_views", lambda: {}), \
             mock.patch.object(ab, "_saver_state", lambda p, l: {}):
            out = ab.brief_quota(now=1001, acct="myacct")
        self.assertEqual((out["ok"], out["acct"], out["fiveHour"]["pct"], out["used5Tok"]), (True, "me", 55.0, 9))
        self.assertNotIn("err", out)

    def test_accts_marks_same(self):
        a = {r["label"]: r for r in st._accts()}
        self.assertTrue(a["myacct"]["same"])
        self.assertNotIn("same", a["work"])
        self.assertNotIn("same", a["me"])

    def test_burn_use_ignores_same_main(self):
        with mock.patch.object(up, "load", lambda: {"mbMainAcct": "myacct"}), \
             mock.patch.object(bu, "_qburn_pts", lambda: []), \
             mock.patch.object(bu, "ring_last", lambda: {"myacct": (NOW + 3600, NOW - 1)}):
            self.assertEqual(bu.burn_use(NOW), {"label": "me", "primary": True, "src": "primary"})
        with mock.patch.object(up, "load", lambda: {"mbMainAcct": "work"}):
            self.assertEqual(bu.burn_use(NOW)["src"], "main")

    def test_acct_body_is_primary(self):
        prim = {"ok": True, "cur": {"now_pct": 40.0}}
        bu._qb_acct.clear()
        self.addCleanup(bu._qb_acct.clear)
        with mock.patch.object(bu, "quota_accounts", lambda: []), mock.patch.object(bu, "quota_burn", lambda: prim):
            self.assertEqual(bu.quota_burn_acct("myacct"), prim)
            self.assertEqual(bu.quota_burn_acct("work"), {"ok": False, "why": "not measured"})


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Page(unittest.TestCase):
    def test_main_acct_ok_rejects_same(self):
        src = ("let ACCTS = [{label: 'me', primary: true}, {label: 'myacct', same: true}, {label: 'work'}];\n"
               + js_fn("acctList") + "\n" + js_fn("mainAcctOk") + "\n"
               + "process.stdout.write(JSON.stringify([mainAcctOk('myacct'), mainAcctOk('work'), mainAcctOk('me')]));")
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        self.assertEqual(json.loads(r.stdout), ["", "work", ""])


if __name__ == "__main__":
    unittest.main()
