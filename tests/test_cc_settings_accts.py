"""Per-account Claude Code keys (cc_settings.cc_set_accts, POST /api/prefs/set key "cc_accounts").

⚠SETTINGS_PATH, TRASH_DIR, prefs.CONFIG_PATH and claude_roots homes point at a temp dir — no live settings file is touched.
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import load, sidereus
from tests.test_routes_post import post
from tests.test_prefs import ORIGIN, get

cs = load()
P = sidereus("prefs")
CC = sidereus("cc_settings")
CR = sidereus("claude_roots")

SETTINGS = {"model": "opus", "env": {"A": "1"}, "autoCompactWindow": 450000, "n": 1.5, "flag": None}


class CcAccts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-cca-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.sp = os.path.join(self.tmp, "settings.json")
        self.cp = os.path.join(self.tmp, "config.local.json")
        self.trash = os.path.join(self.tmp, "trash")
        self.home = os.path.join(self.tmp, "home")
        self.wdir = os.path.join(self.home, ".claude-work")
        os.makedirs(os.path.join(self.wdir, "projects"))
        os.makedirs(os.path.join(self.tmp, "prim", "projects"))
        self.xp = os.path.join(self.wdir, "settings.json")
        for p in (mock.patch.object(CC, "SETTINGS_PATH", self.sp), mock.patch.object(CC, "TRASH_DIR", self.trash),
                  mock.patch.object(P, "CONFIG_PATH", self.cp), mock.patch.object(P, "warn_once", lambda *a, **k: None),
                  mock.patch.object(CC, "_strftime", lambda fmt: "2026-09-29" if fmt == "%Y-%m-%d" else "20260929-120000"),
                  mock.patch.object(CR, "SCAN_HOME", self.home),
                  mock.patch.object(CR, "claude_home", lambda: os.path.join(self.tmp, "prim"))):
            p.start()
            self.addCleanup(p.stop)
        CR.reset()
        self.addCleanup(CR.reset)

    def _put(self, p, text=None):
        with open(p, "w", encoding="utf-8", newline="") as f:   # LF fixture on Windows too
            f.write(text if text is not None else json.dumps(SETTINGS, indent=2) + "\n")
        return self._b(p)

    def _b(self, p):
        with open(p, "rb") as f:
            return f.read()

    def _save(self, accts, dry=False):
        return post("/api/prefs/set", {"key": "cc_accounts", "dry": dry, "accts": accts}, origin=ORIGIN)

    def _hist(self):
        if not os.path.exists(self.cp):
            return None
        with open(self.cp, encoding="utf-8") as f:
            return json.load(f).get("compact_history")

    def test_get_primary_label(self):
        self._put(self.sp)
        self.assertIn("cc_primary_label", get("/api/prefs")[1])

    def test_unchanged_account_untouched(self):
        self._put(self.sp)
        x0 = self._put(self.xp)
        os.utime(self.xp, (1000000000, 1000000000))
        code, out, _ = self._save([{"path": self.sp, "window": 300000}])
        self.assertEqual(code, 200, out)
        self.assertEqual([f["status"] for f in out["files"]], ["written", "same"])
        self.assertEqual(self._b(self.xp), x0)
        self.assertEqual(os.stat(self.xp).st_mtime, 1000000000)
        bdir = os.path.join(self.trash, "20260929-120000")
        self.assertEqual(os.listdir(bdir), ["settings.json"])       # no backup for the unchanged extra

    def test_changed_extra_only_two_values(self):
        p0 = self._put(self.sp)
        x0 = self._put(self.xp)
        code, out, _ = self._save([{"path": self.xp, "auto": False, "window": 200000}])
        self.assertEqual(code, 200, out)
        self.assertEqual(self._b(self.sp), p0)
        self.assertEqual(out["files"][0]["status"], "same")
        row = out["files"][1]
        self.assertEqual((row["status"], row["after"]), ("written", {"auto": False, "window": 200000}))
        a, b = json.loads(x0), json.loads(self._b(self.xp))
        self.assertEqual({k: v for k, v in b.items() if k not in ("autoCompactEnabled", "autoCompactWindow")},
                         {k: v for k, v in a.items() if k != "autoCompactWindow"})
        self.assertEqual(list(b), list(a) + ["autoCompactEnabled"])
        self.assertEqual(self._b(self.xp), x0.replace(b"450000", b"200000").replace(b"null\n}", b"null,\n  \"autoCompactEnabled\": false\n}"))
        with open(row["backup"], "rb") as f:
            self.assertEqual(f.read(), x0)                           # one backup holding the original
        self.assertIsNone(self._hist())                              # extra's window: no history line

    def test_unknown_path_refused(self):
        p0, x0 = self._put(self.sp), self._put(self.xp)
        for bad in (os.path.join(self.tmp, "other.json"), self.xp + "/../settings.json", None):
            code, out, _ = self._save([{"path": self.sp, "window": 300000}, {"path": bad, "window": 300000}])
            self.assertEqual(code, 400, out)
        self.assertEqual((self._b(self.sp), self._b(self.xp)), (p0, x0))
        self.assertFalse(os.path.exists(self.trash))

    def test_invalid_value_refused(self):
        p0 = self._put(self.sp)
        for a in ({"path": self.sp, "window": 10}, {"path": self.sp, "auto": "yes"}):
            self.assertEqual(self._save([a])[0], 400)
        self.assertEqual(self._b(self.sp), p0)

    def test_dry_writes_nothing(self):
        p0, x0 = self._put(self.sp), self._put(self.xp)
        code, out, _ = self._save([{"path": self.sp, "auto": True, "window": 450000}, {"path": self.xp, "window": 300000}], dry=True)
        self.assertEqual(code, 200, out)
        self.assertTrue(out["dry"])
        f0, f1 = out["files"]
        self.assertTrue(f0["primary"])
        self.assertEqual((f0["before"], f0["after"]), ({"auto": True, "window": 450000}, {"auto": True, "window": 450000}))
        self.assertEqual(f0["status"], "change")                     # auto absent -> explicit true is still a byte change
        self.assertEqual((f1["status"], f1["before"]["window"], f1["after"]["window"]), ("change", 450000, 300000))
        self.assertEqual((self._b(self.sp), self._b(self.xp)), (p0, x0))
        self.assertFalse(os.path.exists(self.trash))
        self.assertIsNone(self._hist())

    def test_missing_and_symlink_extra_skipped(self):
        self._put(self.sp)
        code, out, _ = self._save([{"path": self.xp, "window": 300000}])
        self.assertEqual((code, out["files"][1]["status"]), (200, "skipped"))
        self.assertFalse(os.path.exists(self.xp))
        other = os.path.join(self.tmp, "other.json")
        o0 = self._put(other)
        os.symlink(other, self.xp)
        CR.reset()
        code, out, _ = self._save([{"path": self.xp, "window": 300000}])
        self.assertEqual((code, out["files"][1]["status"], out["files"][1]["err"]), (200, "skipped", "symlink"))
        self.assertEqual(self._b(other), o0)

    def test_primary_refusal_writes_nothing(self):
        p0 = self._put(self.sp, '{"autoCompactWindow": 1, "autoCompactWindow": 2}')
        x0 = self._put(self.xp)
        code, _out, _ = self._save([{"path": self.sp, "window": 300000}, {"path": self.xp, "window": 300000}])
        self.assertEqual(code, 400)
        self.assertEqual((self._b(self.sp), self._b(self.xp)), (p0, x0))
        self.assertFalse(os.path.exists(self.trash))

    def test_history_only_on_primary_window_change(self):
        self._put(self.sp)
        self._put(self.xp)
        self._save([{"path": self.sp, "auto": False, "window": 450000}])
        self.assertIsNone(self._hist())                              # primary window unchanged
        code, out, _ = self._save([{"path": self.sp, "window": 300000}, {"path": self.xp, "window": 250000}])
        self.assertEqual(code, 200, out)
        h = self._hist()
        self.assertTrue(h and "300000" in json.dumps(h) and "250000" not in json.dumps(h), h)
        self.assertEqual(os.path.dirname(os.path.dirname(out["files"][1]["backup"])), os.path.dirname(out["files"][0]["backup"]))


if __name__ == "__main__":
    unittest.main()
