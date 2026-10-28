"""«Preferences» Claude Code keys (sidereus/cc_settings.py): only autoCompactEnabled / autoCompactWindow of settings.json.

⚠SETTINGS_PATH, TRASH_DIR and prefs.CONFIG_PATH point at a temp dir — the live ~/.claude/settings.json and
config.local.json are never read or written.
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._fs import assert_mode
from tests._load import load, sidereus
from tests.test_routes_post import post, EVIL
from tests.test_prefs import ORIGIN, get

cs = load()
P = sidereus("prefs")
CC = sidereus("cc_settings")

SETTINGS = {
    "model": "opus", "env": {"A": "1", "한글": "값"}, "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "x.py"}]}]},
    "autoCompactWindow": 450000, "permissions": {"allow": ["Bash(ls:*)"], "deny": []}, "n": 1.5, "flag": None,
}


class CcSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-cc-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.sp = os.path.join(self.tmp, "settings.json")
        self.cp = os.path.join(self.tmp, "config.local.json")
        self.trash = os.path.join(self.tmp, "trash")
        for p in (mock.patch.object(CC, "SETTINGS_PATH", self.sp), mock.patch.object(CC, "TRASH_DIR", self.trash),
                  mock.patch.object(P, "CONFIG_PATH", self.cp), mock.patch.object(P, "warn_once", lambda *a, **k: None),
                  mock.patch.object(CC, "_strftime", lambda fmt: "2026-09-29" if fmt == "%Y-%m-%d" else "20260929-120000"),
                  # _targets() reads claude_roots.accounts(): keep its primary and scan home in tmp (no live ~/.claude stat)
                  mock.patch.object(sidereus("claude_roots"), "SCAN_HOME", os.path.join(self.tmp, "no-home")),
                  mock.patch.object(sidereus("claude_roots"), "claude_home", lambda: os.path.join(self.tmp, "prim"))):
            p.start()
            self.addCleanup(p.stop)
        sidereus("claude_roots").reset()
        self.addCleanup(sidereus("claude_roots").reset)

    def _put(self, obj=None, text=None, mode=0o600):
        with open(self.sp, "w", encoding="utf-8", newline="") as f:   # exact bytes: no CRLF on Windows
            f.write(text if text is not None else json.dumps(obj if obj is not None else SETTINGS, ensure_ascii=False, indent=2) + "\n")
        os.chmod(self.sp, mode)

    def _bytes(self):
        with open(self.sp, "rb") as f:
            return f.read()

    def _cfg(self):
        with open(self.cp, encoding="utf-8") as f:
            return json.load(f)

    def test_get_reports_claude_src(self):
        self._put()
        code, out = get("/api/prefs")
        self.assertEqual(code, 200)
        self.assertEqual(out["cc_path"], self.sp)
        self.assertEqual(out["keys"]["cc_compact_window"]["value"], 450000)
        self.assertEqual(out["keys"]["cc_compact_window"]["src"], "claude")
        self.assertEqual(out["keys"]["cc_auto_compact"]["value"], True)   # absent key = Claude Code default

    def test_only_one_key_changes(self):
        self._put(mode=0o640)
        before = json.loads(self._bytes())
        code, out, _ = post("/api/prefs/set", {"key": "cc_auto_compact", "value": False}, origin=ORIGIN)
        self.assertEqual((code, out["ok"], out["value"]), (200, True, False))
        after = json.loads(self._bytes())
        self.assertIs(after["autoCompactEnabled"], False)
        self.assertEqual([k for k in after if k != "autoCompactEnabled"], list(before))
        for k in before:
            self.assertEqual(json.dumps(after[k], ensure_ascii=False).encode(), json.dumps(before[k], ensure_ascii=False).encode(), k)
        assert_mode(self, self.sp, 0o640)
        self.assertFalse([f for f in os.listdir(self.tmp) if ".sidereus-tmp." in f])
        self.assertFalse(os.path.exists(self.cp))                         # enabled toggle does not touch compact_history

    @unittest.skipIf(os.name == "nt", "symlinks need admin on Windows")
    def test_symlinked_primary_stays_a_link(self):
        real = os.path.join(self.tmp, "dotfiles-settings.json")
        with open(real, "w", encoding="utf-8") as f:
            json.dump(SETTINGS, f, indent=2)
        os.symlink(real, self.sp)
        code, out, _ = post("/api/prefs/set", {"key": "cc_auto_compact", "value": False}, origin=ORIGIN)
        self.assertEqual((code, out["ok"]), (200, True))
        self.assertTrue(os.path.islink(self.sp))                          # link kept, target rewritten
        with open(real, encoding="utf-8") as f:
            self.assertIs(json.load(f)["autoCompactEnabled"], False)
        self.assertFalse([f for f in os.listdir(self.tmp) if ".sidereus-tmp." in f])

    def test_indent2_file_changes_one_line(self):
        self._put()
        old = self._bytes().decode("utf-8").splitlines()
        post("/api/prefs/set", {"key": "cc_compact_window", "value": 300000}, origin=ORIGIN)
        new = self._bytes().decode("utf-8").splitlines()
        self.assertEqual([(a, b) for a, b in zip(old, new) if a != b], [('  "autoCompactWindow": 450000,', '  "autoCompactWindow": 300000,')])

    def _set_exact(self, text, key, value, want):
        """Write text, set key, assert the file is exactly want (every byte outside the value unchanged)."""
        self._put(text=text)
        code, out, _ = post("/api/prefs/set", {"key": key, "value": value}, origin=ORIGIN)
        self.assertEqual(code, 200, out)
        self.assertEqual(self._bytes().decode("utf-8"), want)

    def test_hand_formatted_bytes_kept(self):
        t4 = ('{\n    "model": "opus",\n    "env": {"A": "1", "한글": "값 ✓"},\n    "autoCompactWindow": 450000,\n'
              '    "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "x.py"}]}]}\n}\n')
        self._set_exact(t4, "cc_compact_window", 300000, t4.replace("450000", "300000"))
        self._set_exact(t4, "cc_auto_compact", False, t4.replace('"x.py"}]}]}\n}', '"x.py"}]}]},\n    "autoCompactEnabled": false\n}'))
        one = '{"permissions":{"allow":["Bash(ls:*)"]},"autoCompactEnabled" :  true ,"n":1.50}'
        self._set_exact(one, "cc_auto_compact", False, one.replace("true", "false"))
        self._set_exact(one, "cc_compact_window", 200000, one[:-1] + ',"autoCompactWindow":200000}')
        tab = '{\n\t"\\u00e9": "\\u00e9",\n\t"autoCompactWindow": 450000\n}'      # escaped non-ASCII stays escaped
        self._set_exact(tab, "cc_compact_window", 600000, tab.replace("450000", "600000"))
        self._set_exact("{ }", "cc_auto_compact", False, '{"autoCompactEnabled": false }')

    def test_duplicate_key_refused(self):
        text = '{"autoCompactWindow": 450000, "autoCompactWindow": 300000}'
        self._put(text=text)
        code, out, _ = post("/api/prefs/set", {"key": "cc_compact_window", "value": 200000}, origin=ORIGIN)
        self.assertEqual((code, out["ok"]), (400, False))
        self.assertEqual(self._bytes().decode("utf-8"), text)
        self.assertFalse(os.path.exists(self.trash))

    def test_backup_written(self):
        self._put()
        orig = self._bytes()
        code, out, _ = post("/api/prefs/set", {"key": "cc_compact_window", "value": 200000}, origin=ORIGIN)
        self.assertEqual(code, 200)
        bak = os.path.join(self.trash, "20260929-120000", "settings.json")
        self.assertEqual(out["backup"], bak)
        with open(bak, "rb") as f:
            self.assertEqual(f.read(), orig)
        post("/api/prefs/set", {"key": "cc_compact_window", "value": 250000}, origin=ORIGIN)
        self.assertTrue(os.path.exists(os.path.join(self.trash, "20260929-120000-2", "settings.json")))

    def test_origin_required(self):
        self._put()
        orig = self._bytes()
        for origin in (None, EVIL):
            code, _out, _ = post("/api/prefs/set", {"key": "cc_auto_compact", "value": False}, origin=origin)
            self.assertEqual(code, 403)
        self.assertEqual(self._bytes(), orig)
        self.assertFalse(os.path.exists(self.trash))

    def test_range_refused_and_type(self):
        self._put()
        orig = self._bytes()
        for v in (10, 49_999, 1_000_001, 99_999_999):     # ⚠refused, not clamped
            code, out, _ = post("/api/prefs/set", {"key": "cc_compact_window", "value": v}, origin=ORIGIN)
            self.assertEqual((code, out["ok"]), (400, False), v)
            self.assertIn("50000", out["err"])
            self.assertIn("1000000", out["err"])
        self.assertEqual(self._bytes(), orig)
        self.assertFalse(os.path.exists(self.trash))
        for v in (50_000, 1_000_000):
            code, out, _ = post("/api/prefs/set", {"key": "cc_compact_window", "value": v}, origin=ORIGIN)
            self.assertEqual((code, out["value"]), (200, v))
        for body in ({"key": "cc_compact_window", "value": "300000"}, {"key": "cc_compact_window", "value": True},
                     {"key": "cc_auto_compact", "value": 1}, {"key": "cc_auto_compact", "reset": True},
                     {"key": "autoCompactWindow", "value": 300000}, {"key": "model", "value": "x"}):
            code, out, _ = post("/api/prefs/set", body, origin=ORIGIN)
            self.assertEqual(code, 400, body)

    def test_unparsable_refused_untouched(self):
        for text in ('{"autoCompactWindow": 450000,', "[1, 2]"):
            self._put(text=text)
            code, out, _ = post("/api/prefs/set", {"key": "cc_compact_window", "value": 300000}, origin=ORIGIN)
            self.assertEqual((code, out["ok"]), (400, False))
            self.assertEqual(self._bytes().decode("utf-8"), text)
        self.assertFalse(os.path.exists(self.trash))
        os.remove(self.sp)
        code, _out, _ = post("/api/prefs/set", {"key": "cc_auto_compact", "value": False}, origin=ORIGIN)
        self.assertEqual(code, 400)
        self.assertFalse(os.path.exists(self.sp))

    def test_changed_during_write_refused(self):
        self._put()
        real = CC._backup

        def race(p):
            with open(p, "a", encoding="utf-8") as f:
                f.write(" ")
            return real(p)
        with mock.patch.object(CC, "_backup", race):
            code, _out, _ = post("/api/prefs/set", {"key": "cc_compact_window", "value": 300000}, origin=ORIGIN)
        self.assertEqual(code, 409)
        self.assertEqual(json.loads(self._bytes())["autoCompactWindow"], 450000)

    def test_compact_history_append_and_replace(self):
        self._put()
        with open(self.cp, "w", encoding="utf-8") as f:
            json.dump({"x": 1, "compact_history": [["2026-09-03", 300000], ["2026-09-22", 450000]]}, f)
        post("/api/prefs/set", {"key": "cc_compact_window", "value": 300000}, origin=ORIGIN)
        self.assertEqual(self._cfg()["compact_history"], [["2026-09-03", 300000], ["2026-09-22", 450000], ["2026-09-29", 300000]])
        post("/api/prefs/set", {"key": "cc_compact_window", "value": 600000}, origin=ORIGIN)
        self.assertEqual(self._cfg()["compact_history"], [["2026-09-03", 300000], ["2026-09-22", 450000], ["2026-09-29", 600000]])
        self.assertEqual(self._cfg()["x"], 1)
        post("/api/prefs/set", {"key": "cc_compact_window", "value": 600000}, origin=ORIGIN)   # unchanged value: no new row
        self.assertEqual(len(self._cfg()["compact_history"]), 3)

    def test_bom_settings_read_and_saved_byte_exact(self):
        body = json.dumps(SETTINGS, ensure_ascii=False, indent=2) + "\n"
        with open(self.sp, "wb") as f:
            f.write(b"\xef\xbb\xbf" + body.encode("utf-8"))
        with open(self.cp, "wb") as f:     # BOM config.local.json: history append must not report it unreadable
            f.write(b"\xef\xbb\xbf" + json.dumps({"x": 1}).encode("utf-8"))
        code, out = get("/api/prefs")
        self.assertNotIn("cc_err", out)
        self.assertEqual(out["keys"]["cc_compact_window"]["value"], 450000)
        code, out, _ = post("/api/prefs/set", {"key": "cc_compact_window", "value": 50000}, origin=ORIGIN)
        self.assertEqual((code, out["ok"]), (200, True))
        self.assertNotIn("hist_err", out)
        want = b"\xef\xbb\xbf" + body.replace('"autoCompactWindow": 450000', '"autoCompactWindow": 50000').encode("utf-8")
        self.assertEqual(self._bytes(), want)
        self.assertEqual(self._cfg_sig()["compact_history"], [["2026-09-29", 50000]])

    def _cfg_sig(self):
        with open(self.cp, encoding="utf-8-sig") as f:
            return json.load(f)

    def test_compact_history_empty_and_out_of_order(self):
        self._put()
        post("/api/prefs/set", {"key": "cc_compact_window", "value": 300000}, origin=ORIGIN)
        self.assertEqual(self._cfg()["compact_history"], [["2026-09-29", 300000]])
        self.assertIsNone(P.compact_hist_append("2026-09-10", 200000))
        self.assertEqual(self._cfg()["compact_history"], [["2026-09-10", 200000], ["2026-09-29", 300000]])


class OtelPort(CcSettings):
    """«포트» save with otel:true rewrites only the port of env.OTEL_EXPORTER_OTLP_ENDPOINT (user approval 10-01)."""
    def setUp(self):
        super().setUp()
        p = mock.patch.dict(os.environ, {"SIDEREUS_PORT": ""})
        p.start()
        self.addCleanup(p.stop)

    def _settings(self, url):
        s = json.loads(json.dumps(SETTINGS))
        s["env"]["OTEL_EXPORTER_OTLP_ENDPOINT"] = url
        return s

    def test_get_exposes_endpoint(self):
        self._put(self._settings("http://127.0.0.1:8799"))
        self.assertEqual(get("/api/prefs")[1]["otel"], {"value": "http://127.0.0.1:8799", "ok": True})
        self._put(self._settings("https://otel.example.com:4318"))
        self.assertFalse(get("/api/prefs")[1]["otel"]["ok"])

    def test_port_save_moves_only_that_value(self):
        self._put(self._settings("http://127.0.0.1:8799"))
        before = self._bytes()
        code, out, _ = post("/api/prefs/set", {"key": "port", "value": 8811, "otel": True}, origin=ORIGIN)
        self.assertEqual(code, 200, out)
        self.assertTrue(out["otel"]["ok"], out)
        self.assertEqual(self._bytes(), before.replace(b'"http://127.0.0.1:8799"', b'"http://127.0.0.1:8811"'))
        self.assertTrue(os.path.exists(out["otel"]["backup"]))
        self.assertEqual(self._cfg()["port"], 8811)

    def test_without_otel_flag_file_untouched(self):
        self._put(self._settings("http://127.0.0.1:8799"))
        before = self._bytes()
        code, out, _ = post("/api/prefs/set", {"key": "port", "value": 8811}, origin=ORIGIN)
        self.assertEqual(code, 200, out)
        self.assertNotIn("otel", out)
        self.assertEqual(self._bytes(), before)

    def test_hand_set_endpoint_refused(self):
        self._put(self._settings("https://otel.example.com:4318"))
        before = self._bytes()
        code, out, _ = post("/api/prefs/set", {"key": "port", "value": 8811, "otel": True}, origin=ORIGIN)
        self.assertEqual(code, 200, out)
        self.assertFalse(out["otel"]["ok"])
        self.assertEqual(self._bytes(), before)

    def test_foreign_origin_refused(self):
        self._put(self._settings("http://127.0.0.1:8799"))
        before = self._bytes()
        code, _out, _ = post("/api/prefs/set", {"key": "port", "value": 8811, "otel": True}, origin=EVIL)
        self.assertNotEqual(code, 200)
        self.assertEqual(self._bytes(), before)


CR = sidereus("claude_roots")


class CcAccounts(OtelPort):
    """A save writes every account's settings.json; tmp SCAN_HOME with one extra account `.claude-work`."""

    def setUp(self):
        super().setUp()
        self.home = os.path.join(self.tmp, "home")
        self.wdir = os.path.join(self.home, ".claude-work")
        os.makedirs(os.path.join(self.wdir, "projects"))
        os.makedirs(os.path.join(self.tmp, "prim", "projects"))
        self.xp = os.path.join(self.wdir, "settings.json")
        for p in (mock.patch.object(CR, "SCAN_HOME", self.home), mock.patch.object(CR, "claude_home", lambda: os.path.join(self.tmp, "prim"))):
            p.start()
            self.addCleanup(p.stop)
        CR.reset()
        self.addCleanup(CR.reset)

    def _putx(self, text=None):
        with open(self.xp, "w", encoding="utf-8") as f:
            f.write(text if text is not None else json.dumps(SETTINGS, ensure_ascii=False, indent=4) + "\n")

    def _xbytes(self):
        with open(self.xp, "rb") as f:
            return f.read()

    def _set(self, v=300000):
        return post("/api/prefs/set", {"key": "cc_compact_window", "value": v}, origin=ORIGIN)

    def test_both_files_change_one_value(self):
        self._put()
        self._putx()
        b0, x0 = self._bytes(), self._xbytes()
        code, out, _ = self._set()
        self.assertEqual(code, 200, out)
        self.assertEqual(self._bytes(), b0.replace(b"450000", b"300000"))
        self.assertEqual(self._xbytes(), x0.replace(b"450000", b"300000"))
        self.assertEqual([f["status"] for f in out["files"]], ["written", "written"])
        self.assertEqual(out["backup"], out["files"][0]["backup"])
        d = os.path.join(self.trash, "20260929-120000")
        self.assertEqual(out["files"][1]["backup"], os.path.join(d, "work", "settings.json"))
        with open(os.path.join(d, "work", "settings.json"), "rb") as f:
            self.assertEqual(f.read(), x0)
        self.assertTrue(os.path.exists(os.path.join(d, "settings.json")))

    def test_extra_missing_skipped_not_created(self):
        self._put()
        code, out, _ = self._set()
        self.assertEqual(code, 200, out)
        self.assertEqual(out["files"][1]["status"], "skipped")
        self.assertFalse(os.path.exists(self.xp))

    def test_extra_invalid_skipped_untouched(self):
        self._put()
        self._putx("{bad")
        code, out, _ = self._set()
        self.assertEqual((code, out["files"][1]["status"]), (200, "skipped"))
        self.assertEqual(self._xbytes(), b"{bad")
        self.assertEqual(json.loads(self._bytes())["autoCompactWindow"], 300000)

    def test_primary_error_writes_nothing(self):
        self._put(text="{bad")
        self._putx()
        x0 = self._xbytes()
        code, _out, _ = self._set()
        self.assertEqual(code, 400)
        self.assertEqual(self._xbytes(), x0)

    def test_extra_conflict_failed_primary_written(self):
        self._put()
        self._putx()
        x0 = self._xbytes()
        real = CC._write_raw

        def wr(p, raw, new_raw, label=None, into=None):
            if p == self.xp:
                return 409, {"ok": False, "err": "settings.json changed while writing — try again"}
            return real(p, raw, new_raw, label, into)
        with mock.patch.object(CC, "_write_raw", wr):
            code, out, _ = self._set()
        self.assertEqual(code, 200, out)
        self.assertEqual(out["files"][1]["status"], "failed")
        self.assertIn("changed while writing", out["files"][1]["err"])
        self.assertEqual(json.loads(self._bytes())["autoCompactWindow"], 300000)
        self.assertEqual(self._xbytes(), x0)

    def test_symlink_extra_skipped(self):
        self._put()
        other = os.path.join(self.tmp, "other.json")
        with open(other, "w", encoding="utf-8") as f:
            f.write(json.dumps(SETTINGS))
        with open(other, "rb") as f:
            o0 = f.read()
        os.symlink(other, self.xp)
        code, out, _ = self._set()
        self.assertEqual(code, 200, out)
        self.assertEqual(out["files"][1], {"label": "work", "path": self.xp, "status": "skipped", "err": "symlink"})
        with open(other, "rb") as f:
            self.assertEqual(f.read(), o0)

    def test_get_cc_accts_shape(self):
        self._put()
        self._putx(json.dumps({"autoCompactEnabled": False}))
        out = get("/api/prefs")[1]
        self.assertEqual(out["cc_accts"], [{"label": "work", "path": self.xp, "auto": False, "window": None, "err": None}])

    def test_single_root_has_no_accts_or_files(self):
        shutil.rmtree(self.wdir)
        CR.reset()
        self._put()
        self.assertNotIn("cc_accts", get("/api/prefs")[1])
        code, out, _ = self._set()
        self.assertEqual(code, 200)
        self.assertNotIn("files", out)

    def test_port_save_leaves_extra_untouched(self):
        self._put(self._settings("http://127.0.0.1:8799"))
        self._putx(json.dumps(self._settings("http://127.0.0.1:8799")))
        x0 = self._xbytes()
        code, out, _ = post("/api/prefs/set", {"key": "port", "value": 8811, "otel": True}, origin=ORIGIN)
        self.assertEqual(code, 200, out)
        self.assertTrue(out["otel"]["ok"], out)
        self.assertEqual(self._xbytes(), x0)


if __name__ == "__main__":
    unittest.main()
