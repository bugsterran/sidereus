"""Harness «Remove» of one Claude Code hook (sidereus/hook_remove.py, POST /api/hooks/remove).

⚠Every settings file, plugin dir and the backup folder live in a tmp dir: ctxsrc / claude_roots / toolinv / hook_connect patched.
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import load, sidereus
from tests.test_routes_post import post
from tests.test_prefs import ORIGIN

load()
H = sidereus("harness")
HR = sidereus("hook_remove")
HC = sidereus("hook_connect")
CX = sidereus("ctxsrc")
CR = sidereus("claude_roots")
TV = sidereus("toolinv")

# ⚠Odd indentation and an env secret outside `hooks`: both must survive byte-for-byte, the secret masked in the diff.
USER_TEXT = """{
    "model":   "opus",
  "env": {"API_TOKEN": "SECRET-do-not-show"},
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /x/guard.py"
          },
          {
            "type": "command",
            "command": "python3 /x/audit.py"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /x/done.py"
          }
        ]
      }
    ]
  },
      "statusLine": {"type": "command"}
}
"""
DUP = {"type": "command", "command": "python3 /x/dup.py"}


def _w(p, body):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(body if isinstance(body, str) else json.dumps(body, indent=2))


def _b(p):
    with open(p, "rb") as f:
        return f.read()


class HookRemove(unittest.TestCase):
    def setUp(self):
        t = self.tmp = tempfile.mkdtemp(prefix="sidereus-hr-")
        self.addCleanup(shutil.rmtree, t, True)
        self.cd, self.proj = os.path.join(t, "claude"), os.path.join(t, "proj")
        self.us = os.path.join(self.cd, "settings.json")
        self.ul = os.path.join(self.cd, "settings.local.json")
        self.ps = os.path.join(self.proj, ".claude", "settings.json")
        self.pl = os.path.join(self.proj, ".claude", "settings.local.json")
        self.plug = os.path.join(t, "plugins", "browser", "1.0.0")
        self.ph = os.path.join(self.plug, "hooks", "hooks.json")
        self.trash = os.path.join(t, "trash")
        _w(self.us, USER_TEXT)
        _w(self.ul, {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "python3 /x/local.py"}]}]}})
        _w(self.ps, {"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [DUP]}, {"matcher": "Edit", "hooks": [DUP]}]}})
        _w(self.pl, {"other": 1})
        _w(self.ph, {"hooks": {"PreToolUse": [{"matcher": "mcp__browser__.*", "hooks": [{"type": "command", "command": "node b.mjs"}]}]}})
        _w(os.path.join(self.cd, "plugins", "installed_plugins.json"), {"plugins": {"browser@mk": [{"installPath": self.plug}]}})
        _w(os.path.join(t, "cj.json"), {})
        for p in (mock.patch.object(CX, "CLAUDE_DIR", self.cd), mock.patch.object(CX, "CLAUDE_JSON", os.path.join(t, "cj.json")),
                  mock.patch.object(CX, "CLAUDE_PROJECTS", os.path.join(t, "projects")), mock.patch.object(CX, "_git_root", lambda c: ""),
                  mock.patch.object(CR, "accounts", lambda: [{"dir": self.cd, "label": "Main", "primary": True}]),
                  mock.patch.object(TV, "known_projects", lambda: [self.proj]),
                  mock.patch.object(HC, "TRASH_DIR", self.trash),
                  mock.patch.object(H, "_proj_ok", lambda p: p == self.proj), mock.patch.object(H, "tool_uses", lambda d: {}),
                  mock.patch.object(H, "scanning", lambda: False), mock.patch.object(H, "mcp_status", lambda d: {}),
                  mock.patch.object(H, "DATA_DIR", os.path.join(t, "data"))):
            p.start()
            self.addCleanup(p.stop)

    def _rows(self):
        code, b = H.harness(self.proj, 30)
        self.assertEqual(code, 200)
        return [dict(h, ev=e["ev"]) for e in b["events"] for h in e["hooks"]]

    def _rm(self, cmd, src=None):
        return next(h["rm"] for h in self._rows() if h["cmd"] == cmd and (src is None or h["src"] == src))

    def _call(self, body, origin=ORIGIN):
        code, out, _h = post("/api/hooks/remove", body, origin=origin)
        return code, out

    def _remove(self, rm):
        code, pv = self._call({"proj": self.proj, "rm": rm, "dry": True})
        self.assertEqual(code, 200, pv)
        code, out = self._call({"proj": self.proj, "rm": rm, "dry": False, "base": pv["base"]})
        self.assertEqual(code, 200, out)
        return pv, out

    def test_r1_diff_only_that_entry_and_rest_byte_identical(self):
        before = _b(self.us)
        pv, out = self._remove(self._rm("audit.py"))
        self.assertEqual(pv["what"], {"ev": "PreToolUse", "matcher": "Bash", "cmd": "audit.py", "src": "user"})
        minus = [ln for ln in pv["diff"].splitlines() if ln.startswith("-") and not ln.startswith("---")]
        plus = [ln for ln in pv["diff"].splitlines() if ln.startswith("+") and not ln.startswith("+++")]
        self.assertTrue(any("audit.py" in ln for ln in minus))
        self.assertEqual(plus, [])
        self.assertFalse(any("guard.py" in ln or "done.py" in ln for ln in minus))
        self.assertNotIn("SECRET-do-not-show", pv["diff"])
        after = _b(self.us).decode("utf-8")
        old = before.decode("utf-8")
        self.assertTrue(after.startswith(old[:old.index('"hooks"')]))
        self.assertTrue(after.endswith(old[old.rindex("},\n      \"statusLine\""):][1:]))
        d = json.loads(after)
        self.assertEqual([k for k in d], ["model", "env", "hooks", "statusLine"])
        self.assertEqual(d["hooks"]["PreToolUse"][0]["hooks"], [{"type": "command", "command": "python3 /x/guard.py"}])

    def test_r1_crlf_file_keeps_crlf(self):
        for bom in (b"", b"\xef\xbb\xbf"):
            raw = bom + USER_TEXT.replace("\n", "\r\n").encode("utf-8")
            with open(self.us, "wb") as f:
                f.write(raw)
            self._remove(self._rm("audit.py"))
            after = _b(self.us)
            self.assertTrue(after.startswith(bom + b"{\r\n"))
            self.assertEqual(after.count(b"\n"), after.count(b"\r\n"))
            self.assertEqual(json.loads(after[len(bom):])["hooks"]["PreToolUse"][0]["hooks"],
                             [{"type": "command", "command": "python3 /x/guard.py"}])

    def test_r1_backup_taken_before_write(self):
        before = _b(self.us)
        seen = {}
        real = HC.os.replace

        def spy(a, b):
            seen["bak"] = [os.path.join(r, f) for r, _d, fs in os.walk(self.trash) for f in fs]
            return real(a, b)
        with mock.patch.object(HC.os, "replace", spy):
            _pv, out = self._remove(self._rm("done.py"))
        self.assertEqual(len(seen["bak"]), 1)
        self.assertEqual(_b(seen["bak"][0]), before)
        self.assertTrue(out["backup"].endswith(os.path.basename(seen["bak"][0])))

    def test_r1_prune_empty_group_and_event(self):
        self._remove(self._rm("done.py"))
        d = json.loads(_b(self.us))
        self.assertNotIn("Stop", d["hooks"])
        self._remove(self._rm("guard.py"))
        self._remove(self._rm("audit.py"))
        self.assertEqual(json.loads(_b(self.us))["hooks"], {})

    def test_r1_kth_duplicate_and_index_shift(self):
        rms = [h["rm"] for h in self._rows() if h["cmd"] == "dup.py"]
        self.assertEqual(len(rms), 2)
        self.assertNotEqual(rms[0], rms[1])
        # another entry inserted ahead of it after the list loaded: the same rm still names the same entry
        d = json.loads(_b(self.ps))
        d["hooks"]["PreToolUse"].insert(0, {"matcher": "Read", "hooks": [{"type": "command", "command": "x.sh"}]})
        _w(self.ps, d)
        self._remove(rms[1])
        g = json.loads(_b(self.ps))["hooks"]["PreToolUse"]
        self.assertEqual([x["matcher"] for x in g], ["Read", "Edit"])

    def test_r2_plugin_row_named_and_refused(self):
        row = next(h for h in self._rows() if h["src"] == "plugin")
        self.assertEqual(row["rm"], "")
        self.assertEqual(row["plug"], "browser")
        before = _b(self.ph)
        d = json.loads(before)
        key = H.rm_key(self.ph, "PreToolUse", "mcp__browser__.*", d["hooks"]["PreToolUse"][0]["hooks"][0], 0)
        code, out = self._call({"proj": self.proj, "rm": key, "dry": True})
        self.assertEqual((code, out["err"]), (400, HR.HR_E_OUTSIDE))
        self.assertEqual(_b(self.ph), before)

    def test_r3_user_local_refused(self):
        self.assertEqual(self._rm("local.py", "user-local"), "")
        key = H.rm_key(self.ul, "Stop", "", {"type": "command", "command": "python3 /x/local.py"}, 0)
        code, out = self._call({"proj": self.proj, "rm": key, "dry": True})
        self.assertEqual(code, 400)

    def test_r3_no_origin(self):
        before = _b(self.us)
        code, out = self._call({"proj": self.proj, "rm": self._rm("done.py"), "dry": False, "base": "x"}, origin=None)
        self.assertEqual(code, 403)
        self.assertEqual(_b(self.us), before)

    def test_r3_symlink(self):
        real = os.path.join(self.tmp, "real-settings.json")
        shutil.move(self.ps, real)
        os.symlink(real, self.ps)
        rm = self._rm("dup.py")   # the list shows the link's target; removing through the link is refused
        code, out = self._call({"proj": self.proj, "rm": rm, "dry": True})
        self.assertEqual((code, out["err"]), (400, HC.SYMLINK))

    def test_r3_wrong_base_and_edit_between(self):
        rm = self._rm("done.py")
        code, out = self._call({"proj": self.proj, "rm": rm, "dry": False, "base": "0" * 64})
        self.assertEqual(code, 409)
        code, pv = self._call({"proj": self.proj, "rm": rm, "dry": True})
        with open(self.us, "a", encoding="utf-8") as f:
            f.write("\n")
        before = _b(self.us)
        code, out = self._call({"proj": self.proj, "rm": rm, "dry": False, "base": pv["base"]})
        self.assertEqual((code, out["err"]), (409, HR.HR_E_BASE))
        self.assertEqual(_b(self.us), before)

    def test_r3_home_project_never_writes_user_local(self):
        key = H.rm_key(self.ul, "Stop", "", {"type": "command", "command": "python3 /x/local.py"}, 0)
        with mock.patch.object(TV, "known_projects", lambda: [self.tmp]), mock.patch.object(CX, "CLAUDE_DIR", self.cd):
            os.symlink(self.cd, os.path.join(self.tmp, ".claude"))   # proj/.claude resolves to CLAUDE_DIR
            code, out = self._call({"proj": self.tmp, "rm": key, "dry": True})
        self.assertIn(code, (400, 404))
        self.assertNotEqual(code, 200)

    def test_r3_extra_account_not_allowed(self):
        xd = os.path.join(self.tmp, "acct2")
        _w(os.path.join(xd, "settings.json"), {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "z.sh"}]}]}})
        key = H.rm_key(os.path.join(xd, "settings.json"), "Stop", "", {"type": "command", "command": "z.sh"}, 0)
        with mock.patch.object(CR, "accounts", lambda: [{"dir": self.cd}, {"dir": xd}]):
            code, out = self._call({"proj": self.proj, "rm": key, "dry": True})
        self.assertEqual(code, 404)

    def test_r3_symlinked_claude_folder(self):
        real = os.path.join(self.tmp, "real-dot-claude")
        shutil.move(os.path.join(self.proj, ".claude"), real)
        os.symlink(real, os.path.join(self.proj, ".claude"))
        rm = self._rm("dup.py")
        code, out = self._call({"proj": self.proj, "rm": rm, "dry": True})
        self.assertEqual((code, out["err"]), (400, HC.SYMLINK))

    def test_r3_unparsable_allowed_file_is_unsafe(self):
        rm = self._rm("dup.py")
        _w(self.ps, "{not json")
        code, out = self._call({"proj": self.proj, "rm": rm, "dry": True})
        self.assertEqual((code, out["err"]), (500, HR.HR_E_UNSAFE))

    def test_r3_unknown_rm(self):
        code, out = self._call({"proj": self.proj, "rm": "r" + "0" * 16, "dry": True})
        self.assertEqual(code, 404)
        code, out = self._call({"proj": self.proj, "rm": "../etc", "dry": True})
        self.assertEqual(code, 404)

    def test_r4_reply_backup_and_list_refreshed(self):
        rm = self._rm("guard.py")
        _pv, out = self._remove(rm)
        self.assertTrue(out["changed"])
        self.assertTrue(out["backup"])
        self.assertNotIn(rm, [h["rm"] for h in self._rows()])
        self.assertIn("audit.py", [h["cmd"] for h in self._rows()])


if __name__ == "__main__":
    unittest.main()
