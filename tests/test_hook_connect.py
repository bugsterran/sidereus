"""«Connect» CLI hooks (sidereus/hook_connect.py, GET/POST /api/hooks/connect).

⚠HC_FILES, TRASH_DIR, _which, _home and _python point at temp values — no real ~/.cursor, ~/.codex, ~/.copilot or Gemini file is read or written.
"""
import hashlib
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
HC = sidereus("hook_connect")
DEMO = sidereus("demo")

PY = "/usr/bin/python3"
ASSET = "/opt/sidereus"


def _sub(cmd, py=PY, asset=ASSET, sep="/"):
    def q(s):
        return '"%s"' % s if " " in s else s
    out = []
    for tok in cmd.split(" "):
        if tok == "<PYTHON>":
            out.append(q(py))
        elif tok.startswith("<MAILBOX_CODE_DIR>"):
            out.append(q(asset + tok[len("<MAILBOX_CODE_DIR>"):].replace("/", sep)))
        else:
            out.append(tok)
    return " ".join(out)


def _example(plat, **kw):
    with open(os.path.join(HC.config.ASSET_DIR, "ext-hooks", HC._TPL[plat]), encoding="utf-8") as f:
        hooks = json.load(f)["hooks"]
    out = {}
    for ev, lst in hooks.items():
        if plat == "copilot":
            out[ev] = [dict(e, bash=_sub(e["bash"], **kw), powershell=_sub(e["powershell"], **kw)) for e in lst]
        elif plat == "cursor":
            out[ev] = [dict(e, command=_sub(e["command"], **kw)) for e in lst]
        else:
            out[ev] = [dict(g, hooks=[dict(e, command=_sub(e["command"], **kw)) for e in g["hooks"]]) for g in lst]
    return out


class HookConnect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-hc-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")
        self.files = {"cursor": os.path.join(self.home, ".cursor", "hooks.json"),
                      "codex": os.path.join(self.home, ".codex", "hooks.json"),
                      "gemini": os.path.join(self.home, ".gemini", "settings.json"),
                      "copilot": os.path.join(self.home, ".copilot", "hooks", "sidereus.json")}
        for plat, p in self.files.items():
            # ⚠copilot: only the home exists, hooks/ is left out so a write proves makedirs
            os.makedirs(os.path.dirname(os.path.dirname(p)) if plat == "copilot" else os.path.dirname(p))
        self.trash = os.path.join(self.tmp, "trash")
        self.tpl_dir = os.path.join(HC.config.ASSET_DIR, "ext-hooks")     # the repo's own templates (code, not user data)
        for p in (mock.patch.object(HC, "HC_FILES", self.files), mock.patch.object(HC, "TRASH_DIR", self.trash),
                  mock.patch.object(HC, "TPL_DIR", self.tpl_dir), mock.patch.object(HC, "_asset", lambda: ASSET),
                  mock.patch.object(HC, "_which", lambda n: None), mock.patch.object(HC, "_home", lambda: self.home),
                  mock.patch.object(HC, "_python", lambda: PY), mock.patch.object(HC, "_now", lambda: 1000.0),
                  mock.patch.object(HC, "_strftime", lambda fmt: "20261024-120000")):
            p.start()
            self.addCleanup(p.stop)
        HC._MEMO.clear()
        self.addCleanup(HC._MEMO.clear)

    def _put(self, plat, obj, indent=2):
        text = obj if isinstance(obj, str) else json.dumps(obj, indent=indent) + "\n"
        with open(self.files[plat], "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return text.encode("utf-8")

    def _raw(self, plat):
        with open(self.files[plat], "rb") as f:
            return f.read()

    def _apply(self, plat):
        code, dry = HC.connect({"plat": plat, "dry": True})
        self.assertEqual(code, 200, dry)
        code, out = HC.connect({"plat": plat, "dry": False, "base": dry["base"]})
        self.assertEqual(code, 200, out)
        return dry, out

    def test_cursor_merges_after_user_entries(self):
        user = {"version": 1, "hooks": {"stop": [{"command": "say done"}], "afterFileEdit": [{"command": "fmt"}]}}
        self._put("cursor", user)
        dry, out = self._apply("cursor")
        self.assertTrue(out["changed"])
        self.assertGreater(dry["adds"], 0)
        d = json.loads(self._raw("cursor"))
        self.assertEqual(d["hooks"]["stop"][0], {"command": "say done"})
        self.assertEqual(d["hooks"]["afterFileEdit"], [{"command": "fmt"}])
        self.assertEqual(list(d["hooks"])[:2], ["stop", "afterFileEdit"])
        ex = _example("cursor")
        self.assertEqual(d["hooks"]["stop"][1:], ex["stop"])
        self.assertEqual(d["hooks"]["preToolUse"], ex["preToolUse"])
        self.assertTrue(os.path.isfile(out["backup"]))
        self.assertTrue(out["backup"].endswith("cursor-hooks.json"))
        with open(out["backup"], "rb") as f:
            self.assertEqual(f.read(), json.dumps(user, indent=2).encode() + b"\n")
        # second apply: nothing to add, no write
        code, again = HC.connect({"plat": "cursor", "dry": True})
        self.assertEqual(again["adds"], 0)
        before = self._raw("cursor")
        code, out2 = HC.connect({"plat": "cursor", "dry": False, "base": again["base"]})
        self.assertEqual((code, out2), (200, {"ok": True, "changed": False}))
        self.assertEqual(self._raw("cursor"), before)

    def test_codex_new_group_keeps_user_groups(self):
        user = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "notify"}]}],
                          "PreToolUse": [{"matcher": "Bash", "hooks": [
                              {"type": "command", "command": "/x/python3 /old/place/ext-hooks/ext_hook.py --platform codex"}]}]},
                "other": [1, 2]}
        self._put("codex", user)
        _dry, out = self._apply("codex")
        self.assertEqual(out["approve"], "/hooks")
        d = json.loads(self._raw("codex"))
        self.assertEqual(d["other"], [1, 2])
        self.assertEqual(list(d)[0], "hooks")
        self.assertEqual(d["hooks"]["Stop"][0], user["hooks"]["Stop"][0])
        self.assertEqual(len(d["hooks"]["Stop"]), 2)
        pre = d["hooks"]["PreToolUse"]
        self.assertEqual(pre[0], user["hooks"]["PreToolUse"][0])     # existing group untouched
        cmds = [e["command"] for e in pre[1]["hooks"]]
        self.assertFalse(any("ext_hook.py" in c for c in cmds))      # already present in another group
        self.assertTrue(any("pl_mark.py" in c for c in cmds))
        self.assertNotIn("description", d)
        self.assertEqual(HC._state("codex", self.files["codex"]), ("connected", ""))

    def test_gemini_matcher_and_hooks_config(self):
        user = {"hooksConfig": {"enabled": False, "x": 1}, "mcpServers": {"m": {"command": "c", "env": {"K": "secret"}}},
                "hooks": {"BeforeTool": [{"matcher": "run_shell_command", "hooks": [
                    {"type": "command", "command": "py /a/ext-hooks/ext_hook.py --platform gemini"}]}]}}
        self._put("gemini", user)
        code, dry = HC.connect({"plat": "gemini", "dry": True})
        self.assertNotIn("secret", dry["diff"])
        self.assertEqual(HC._mask('  "theme": "dark", "env": {"K": "s\\"x"}},', False), '  "theme": "…", "env": {"K": "…"}},')
        _dry, out = self._apply("gemini")
        d = json.loads(self._raw("gemini"))
        self.assertEqual(d["hooksConfig"], {"enabled": True, "x": 1})
        self.assertEqual(d["mcpServers"], user["mcpServers"])
        bt = d["hooks"]["BeforeTool"]
        self.assertEqual(bt[0], user["hooks"]["BeforeTool"][0])
        # ext_hook under matcher run_shell_command does not count for matcher ".*"
        self.assertEqual(bt[1]["matcher"], ".*")
        self.assertNotIn("approve", out)
        self.assertEqual(HC._state("gemini", self.files["gemini"]), ("connected", ""))

    def test_gemini_missing_file_refused(self):
        os.makedirs(os.path.join(self.home, ".gemini"), exist_ok=True)
        code, out = HC.connect({"plat": "gemini", "dry": True})
        self.assertEqual(code, 400)
        self.assertFalse(os.path.exists(self.files["gemini"]))

    def test_new_file_equals_example(self):
        for plat, top in (("cursor", {"version": 1}), ("codex", {}), ("copilot", {"version": 1})):
            self._apply(plat)
            self.assertEqual(json.loads(self._raw(plat)), dict(top, hooks=_example(plat)))

    def test_windows_quoting(self):
        win_py, win_asset = r"C:\Program Files\Python\python.exe", r"C:\Users\A B\sidereus"
        with mock.patch.object(HC, "_python", lambda: win_py), mock.patch.object(HC, "_asset", lambda: win_asset):
            got = HC._subst("<PYTHON> <MAILBOX_CODE_DIR>/ext-hooks/ext_hook.py --platform codex")
            self._apply("codex")
        self.assertEqual(got, '"C:\\Program Files\\Python\\python.exe" "C:\\Users\\A B\\sidereus\\ext-hooks\\ext_hook.py" --platform codex')
        self.assertEqual(HC._key(got), ("ext_hook.py", "--platform codex"))
        self.assertEqual(json.loads(self._raw("codex")), {"hooks": _example("codex", py=win_py, asset=win_asset, sep="\\")})

    def test_symlink_refused(self):
        real = os.path.join(self.tmp, "dotfiles-hooks.json")
        with open(real, "w", encoding="utf-8") as f:
            f.write('{"version": 1, "hooks": {}}\n')
        os.symlink(real, self.files["cursor"])
        with mock.patch.object(HC, "_read", side_effect=AssertionError("read for the diff")):
            code, out = HC.connect({"plat": "cursor", "dry": True})
        self.assertEqual((code, out["err"]), (400, HC.SYMLINK))
        code, out = HC.connect({"plat": "cursor", "dry": False, "base": ""})
        self.assertEqual((code, out["err"]), (400, HC.SYMLINK))
        self.assertTrue(os.path.islink(self.files["cursor"]))
        with mock.patch.object(HC, "_which", lambda n: "/bin/" + n if n == "cursor-agent" else None):
            row = [r for r in HC.listing() if r["plat"] == "cursor"][0]
        self.assertEqual((row["can"], row["why"]), (False, HC.SYMLINK))

    def test_wait_variant_counts(self):
        for flag in ("--wait", "--wake"):    # opt-in variants of the shipped turn-end entry: no churn on «Connect»
            ex = _example("codex")
            for e in ex["Stop"][0]["hooks"]:
                if "gemini_mail_stop.py" in e["command"]:
                    e["command"] += " " + flag
            self._put("codex", {"hooks": ex})
            self.assertEqual(HC._state("codex", self.files["codex"]), ("connected", ""), flag)
            code, dry = HC.connect({"plat": "codex", "dry": True})
            self.assertEqual(dry["adds"], 0, flag)
        self.assertNotEqual(HC._key("py /a/gemini_mail_stop.py --platform codex --wait"),
                            HC._key("py /a/gemini_mail_stop.py --wake"))

    def test_partial_is_not_connected(self):
        ex = _example("cursor")
        ex["stop"] = []
        self._put("cursor", {"version": 1, "hooks": ex})
        self.assertEqual(HC._state("cursor", self.files["cursor"])[0], "partial")
        self._put("cursor", {"version": 1, "hooks": _example("cursor")})
        self.assertEqual(HC._state("cursor", self.files["cursor"])[0], "connected")

    def test_bad_base_409_unchanged(self):
        raw = self._put("cursor", {"version": 1, "hooks": {}})
        code, out = HC.connect({"plat": "cursor", "dry": False, "base": "0" * 64})
        self.assertEqual(code, 409)
        self.assertEqual(self._raw("cursor"), raw)
        self.assertFalse(os.path.exists(self.trash))

    def test_changed_mid_write_409_unchanged(self):
        self._put("cursor", {"version": 1, "hooks": {}})
        code, dry = HC.connect({"plat": "cursor", "dry": True})
        real = HC._backup
        other = b'{"version": 1, "hooks": {"stop": []}}\n'

        def bak(p, plat):
            dst = real(p, plat)
            with open(p, "wb") as f:      # the CLI rewrites the file between backup and replace
                f.write(other)
            return dst
        with mock.patch.object(HC, "_backup", bak):
            code, out = HC.connect({"plat": "cursor", "dry": False, "base": dry["base"]})
        self.assertEqual(code, 409)
        self.assertEqual(self._raw("cursor"), other)
        self.assertEqual([n for n in os.listdir(os.path.dirname(self.files["cursor"])) if "tmp" in n], [])

    def test_invalid_refused(self):
        for text in ("{not json", '{"hooks": []}\n', "[1]\n", '{"hooks": {"stop": {}}}\n'):
            raw = self._put("cursor", text)
            code, out = HC.connect({"plat": "cursor", "dry": True})
            self.assertEqual(code, 400, text)
            self.assertFalse(out["ok"])
            self.assertEqual(self._raw("cursor"), raw)
        self.assertEqual(HC._state("cursor", self.files["cursor"])[0], "unreadable")

    def test_other_bytes_unchanged(self):
        text = '{\n    "version": 1,\n    "x": "\u00e9",  "hooks": {}, "z": [1,2]\n}\n'
        self._put("cursor", text)
        self._apply("cursor")
        new = self._raw("cursor").decode("utf-8")
        self.assertTrue(new.startswith('{\n    "version": 1,\n    "x": "\u00e9",  "hooks": {'))
        self.assertTrue(new.endswith(', "z": [1,2]\n}\n'))

    def test_crlf_file_keeps_crlf(self):
        self._put("cursor", '{\r\n  "version": 1,\r\n  "hooks": {"stop": [{"command": "say done"}]}\r\n}\r\n')
        self._apply("cursor")
        new = self._raw("cursor")
        self.assertEqual(new.count(b"\n"), new.count(b"\r\n"))
        self.assertEqual(json.loads(new)["hooks"]["stop"][0], {"command": "say done"})
        empty = HC._splice('{\r\n}\r\n', [("hooks", {"a": [1]})])[0]
        self.assertEqual(empty.count("\n"), empty.count("\r\n"))

    def test_base_is_sha(self):
        raw = self._put("cursor", {"version": 1, "hooks": {}})
        code, dry = HC.connect({"plat": "cursor", "dry": True})
        self.assertEqual(dry["base"], hashlib.sha256(raw).hexdigest())
        code, dry = HC.connect({"plat": "codex", "dry": True})
        self.assertEqual(dry["base"], "")

    def test_listing(self):
        for d in (".cursor", ".codex", ".gemini", ".copilot"):
            shutil.rmtree(os.path.join(self.home, d))
        self.assertEqual(HC.listing(), [])      # nothing on PATH, no config dir: nothing installed
        for plat, p in self.files.items():
            os.makedirs(os.path.dirname(os.path.dirname(p)) if plat == "copilot" else os.path.dirname(p))
        HC._MEMO.clear()
        with mock.patch.object(HC, "_which", lambda n: "/bin/" + n if n == "cursor-agent" else None):
            self._put("codex", {"hooks": _example("codex")})
            rows = HC.listing()
        by = {r["plat"]: r for r in rows}
        self.assertEqual(by["cursor"]["state"], "missing")
        self.assertTrue(by["cursor"]["can"])
        self.assertEqual(by["cursor"]["file"], os.path.join("~", ".cursor", "hooks.json"))
        self.assertEqual(by["codex"]["state"], "connected")
        self.assertEqual(by["codex"]["approve"], "/hooks")
        self.assertEqual(by["gemini"]["state"], "missing")
        self.assertFalse(by["gemini"]["can"])
        self.assertEqual((by["copilot"]["state"], by["copilot"]["can"], by["copilot"]["approve"]), ("missing", True, ""))
        self.assertEqual(by["copilot"]["file"], os.path.join("~", ".copilot", "hooks", "sidereus.json"))
        self.assertEqual(set(by["codex"]), {"plat", "name", "state", "file", "can", "why", "approve"})

    def test_r4_copilot_missing_file_dry_diff_and_apply(self):
        self.assertFalse(os.path.exists(os.path.dirname(self.files["copilot"])))
        code, dry = HC.connect({"plat": "copilot", "dry": True})
        self.assertEqual(code, 200, dry)
        self.assertEqual(dry["base"], "")
        self.assertIn("+++ " + os.path.join("~", ".copilot", "hooks", "sidereus.json"), dry["diff"])
        self.assertIn('"PermissionRequest"', dry["diff"])
        self.assertFalse(os.path.exists(self.files["copilot"]))      # dry writes nothing
        code, out = HC.connect({"plat": "copilot", "dry": False, "base": dry["base"]})
        self.assertEqual(code, 200, out)
        self.assertNotIn("approve", out)
        self.assertIsNone(out["backup"])
        d = json.loads(self._raw("copilot"))
        self.assertEqual(d, {"version": 1, "hooks": _example("copilot")})
        self.assertFalse(any(k[0].islower() for k in d["hooks"]))     # ⚠camelCase too would fire every event twice
        self.assertEqual(d["hooks"]["Stop"][0]["bash"], PY + " " + ASSET + "/ext-hooks/ext_hook.py --platform copilot")
        self.assertEqual(HC._state("copilot", self.files["copilot"]), ("connected", ""))

    def test_r4_copilot_keeps_user_entry_first(self):
        os.makedirs(os.path.dirname(self.files["copilot"]))
        user = {"version": 1, "hooks": {"Stop": [{"type": "command", "bash": "say done", "powershell": "echo done"}],
                                        "Notification": [{"type": "command", "bash": "beep"}]}}
        self._put("copilot", user)
        _dry, out = self._apply("copilot")
        d = json.loads(self._raw("copilot"))
        self.assertEqual(d["hooks"]["Stop"][0], user["hooks"]["Stop"][0])
        self.assertEqual(d["hooks"]["Stop"][1:], _example("copilot")["Stop"])
        self.assertEqual(d["hooks"]["Notification"], user["hooks"]["Notification"])
        self.assertEqual(list(d["hooks"])[:2], ["Stop", "Notification"])
        code, again = HC.connect({"plat": "copilot", "dry": True})
        self.assertEqual(again["adds"], 0)

    def test_r4_copilot_symlink_400(self):
        os.makedirs(os.path.dirname(self.files["copilot"]))
        real = os.path.join(self.tmp, "dotfiles-copilot.json")
        with open(real, "w", encoding="utf-8") as f:
            f.write('{"version": 1, "hooks": {}}\n')
        os.symlink(real, self.files["copilot"])
        code, out = HC.connect({"plat": "copilot", "dry": True})
        self.assertEqual((code, out["err"]), (400, HC.SYMLINK))
        code, out = HC.connect({"plat": "copilot", "dry": False, "base": ""})
        self.assertEqual((code, out["err"]), (400, HC.SYMLINK))
        self.assertTrue(os.path.islink(self.files["copilot"]))
        with open(real, encoding="utf-8") as f:
            self.assertEqual(f.read(), '{"version": 1, "hooks": {}}\n')

    def test_r4_copilot_symlinked_hooks_dir_400(self):
        elsewhere = os.path.join(self.tmp, "elsewhere")
        os.makedirs(elsewhere)
        os.symlink(elsewhere, os.path.dirname(self.files["copilot"]))
        code, out = HC.connect({"plat": "copilot", "dry": True})
        self.assertEqual((code, out["err"]), (400, HC.SYMLINK))
        code, out = HC._write("copilot", self.files["copilot"], None, b"{}")
        self.assertEqual((code, out["err"]), (400, HC.SYMLINK))
        self.assertEqual(os.listdir(elsewhere), [])
        shutil.rmtree(os.path.dirname(self.files["cursor"]))
        os.symlink(elsewhere, os.path.dirname(self.files["cursor"]))
        code, out = HC.connect({"plat": "cursor", "dry": True})
        self.assertEqual((code, out["err"]), (400, HC.SYMLINK))

    def test_r4_copilot_relative_home_ignored(self):
        with mock.patch.object(HC, "HC_FILES", None):
            with mock.patch.dict(os.environ, {"COPILOT_HOME": "rel/copilot"}):
                self.assertEqual(HC._files()["copilot"], os.path.join(self.home, ".copilot", "hooks", "sidereus.json"))
            absd = os.path.join(self.tmp, "cph")
            with mock.patch.dict(os.environ, {"COPILOT_HOME": absd}):
                self.assertEqual(HC._files()["copilot"], os.path.join(absd, "hooks", "sidereus.json"))

    def test_r4_copilot_base_mismatch_409(self):
        os.makedirs(os.path.dirname(self.files["copilot"]))
        raw = self._put("copilot", {"version": 1, "hooks": {}})
        code, out = HC.connect({"plat": "copilot", "dry": False, "base": "0" * 64})
        self.assertEqual(code, 409)
        self.assertEqual(self._raw("copilot"), raw)
        self.assertFalse(os.path.exists(self.trash))

    def test_r4_copilot_backup_in_trash(self):
        os.makedirs(os.path.dirname(self.files["copilot"]))
        raw = self._put("copilot", {"version": 1, "hooks": {"Stop": [{"type": "command", "bash": "say done"}]}})
        _dry, out = self._apply("copilot")
        self.assertTrue(out["backup"].startswith(self.trash + os.sep))
        self.assertTrue(out["backup"].endswith("copilot-sidereus.json"))
        with open(out["backup"], "rb") as f:
            self.assertEqual(f.read(), raw)

    def test_r4_copilot_windows_subst(self):
        win_py, win_asset = r"C:\Program Files\Python\python.exe", r"C:\Users\A B\sidereus"
        with mock.patch.object(HC, "_python", lambda: win_py), mock.patch.object(HC, "_asset", lambda: win_asset):
            self._apply("copilot")
        d = json.loads(self._raw("copilot"))
        ps = d["hooks"]["PreToolUse"][0]["powershell"]
        self.assertEqual(ps, '& "C:\\Program Files\\Python\\python.exe" "C:\\Users\\A B\\sidereus\\ext-hooks\\ext_hook.py" --platform copilot')
        self.assertEqual(HC._key(ps), ("ext_hook.py", "--platform copilot"))
        self.assertEqual(d, {"version": 1, "hooks": _example("copilot", py=win_py, asset=win_asset, sep="\\")})

    def test_bare_agent_needs_cursor_dir(self):
        shutil.rmtree(os.path.dirname(self.files["cursor"]))
        with mock.patch.object(HC, "_which", lambda n: "/bin/agent" if n == "agent" else None):
            self.assertFalse(HC._installed("cursor", self.files["cursor"]))
            os.makedirs(os.path.dirname(self.files["cursor"]))
            self.assertTrue(HC._installed("cursor", self.files["cursor"]))

    def test_no_template_cannot_connect(self):
        with mock.patch.object(HC, "_template", lambda plat: None):
            code, out = HC.connect({"plat": "cursor", "dry": True})
            self.assertEqual((code, out["err"]), (400, "no ext-hooks"))
            rows = HC.listing()
        self.assertTrue(all(not r["can"] and r["why"] for r in rows if r["state"] != "connected"))

    def test_routes(self):
        code, out = post("/api/hooks/connect", {"plat": "cursor", "dry": True})[:2]
        self.assertEqual(code, 403)
        code, out = post("/api/hooks/connect", {"plat": "cursor", "dry": False, "base": ""})[:2]
        self.assertEqual(code, 403)
        self.assertFalse(os.path.exists(self.files["cursor"]))
        code, out = post("/api/hooks/connect", {"plat": "cursor", "dry": True}, origin=ORIGIN)[:2]
        self.assertEqual(code, 200)
        self.assertEqual(set(out), {"ok", "diff", "base", "adds"})
        code, out = post("/api/hooks/connect", {"plat": "../x", "dry": True}, origin=ORIGIN)[:2]
        self.assertEqual(code, 400)
        code, out = get("/api/hooks/connect")
        self.assertEqual(code, 200)
        self.assertEqual(out["ok"], True)
        self.assertIsInstance(out["plats"], list)

    def test_demo_empty(self):
        w = DEMO.World()
        code, out = DEMO.respond(w, "/api/hooks/connect", None)
        self.assertEqual(code, 200)
        self.assertEqual(out.get("plats") or [], [])


if __name__ == "__main__":
    unittest.main()
