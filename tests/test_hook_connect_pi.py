"""«Connect» for pi (sidereus/hook_connect_pi.py): mcp.json mcpServers merge + extensions/sidereus.ts.

⚠PI_FILES, TPL, hook_connect.TRASH_DIR/_which/_home/_python/_asset point at temp values — no real ~/.pi is read or written.
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
HP = sidereus("hook_connect_pi")
_REAL_PYTHON = HC._python

PY = '/opt/my py/bin\\python3'
ASSET = "/opt/side reus"
TPL_TEXT = 'const PY = "<PYTHON>";\nconst CODE = "<MAILBOX_CODE_DIR>";\nexport default function () {}\n'


class HookConnectPi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-hcpi-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")
        self.root = os.path.join(self.home, ".pi", "agent")
        os.makedirs(self.root)
        self.files = {"mcp": os.path.join(self.root, "mcp.json"),
                      "ts": os.path.join(self.root, "extensions", "sidereus.ts")}
        self.tpl = os.path.join(self.tmp, "pi-extension.ts")
        with open(self.tpl, "w", encoding="utf-8") as f:
            f.write(TPL_TEXT)
        self.trash = os.path.join(self.tmp, "trash")
        for p in (mock.patch.object(HP, "PI_FILES", self.files), mock.patch.object(HP, "TPL", self.tpl),
                  mock.patch.object(HC, "TRASH_DIR", self.trash), mock.patch.object(HC, "_asset", lambda: ASSET),
                  mock.patch.object(HC, "_which", lambda n: None), mock.patch.object(HC, "_home", lambda: self.home),
                  mock.patch.object(HC, "_python", lambda: PY), mock.patch.object(HC.config, "IS_WIN", False),
                  mock.patch.object(HC, "_strftime", lambda fmt: "20261110-120000")):
            p.start()
            self.addCleanup(p.stop)

    def _put(self, text):
        with open(self.files["mcp"], "w", encoding="utf-8", newline="") as f:
            f.write(text)

    def _mcp(self):
        with open(self.files["mcp"], encoding="utf-8") as f:
            return f.read()

    def _apply(self):
        code, out = HP.connect({"plat": "pi", "dry": True})
        self.assertEqual(code, 200, out)
        code2, out2 = HP.connect({"plat": "pi", "dry": False, "base": out["base"]})
        self.assertEqual(code2, 200, out2)
        return out, out2

    def _want(self):
        return {"sidereus": {"command": PY, "args": [os.path.join(ASSET, "mcp", "sidereus_mcp.py")]},
                "mailbox": {"command": os.path.join(ASSET, "ext-hooks", "gemini_mailbox_mcp.sh"), "args": ["pi"]}}

    def test_missing_files_created(self):
        self.assertEqual(HP.row()[0]["state"], "missing")
        dry, out = self._apply()
        self.assertEqual(dry["adds"], 3)
        self.assertEqual(json.loads(self._mcp()), {"mcpServers": self._want()})
        with open(self.files["ts"], encoding="utf-8") as f:
            ts = f.read()
        # ⚠placeholders JSON-escaped: a space and a backslash in the path stay one valid string literal
        self.assertIn('const PY = %s;' % json.dumps(PY), ts)
        self.assertIn('const CODE = "/opt/side reus";', ts)
        self.assertIsNone(out["backup"])
        self.assertEqual(HP.row()[0]["state"], "connected")
        self.assertFalse(HP.row()[0]["can"])

    def test_empty_object(self):
        self._put("{}\n")
        self._apply()
        self.assertEqual(json.loads(self._mcp()), {"mcpServers": self._want()})

    def test_user_servers_and_other_keys_kept(self):
        text = ('{\n    "settings": {"x": [1, 2]},\n    "mcpServers": {\n        "mine": {"command": "a", "env": {"K": "secret"}}\n'
                '    },\n    "tail": "  odd  spacing"\n}\n')
        self._put(text)
        dry, _out = self._apply()
        self.assertNotIn("secret", dry["diff"])     # user server env masked in the preview
        self.assertIn("sidereus_mcp.py", dry["diff"])
        new = self._mcp()
        self.assertIn('"settings": {"x": [1, 2]}', new)
        self.assertIn('"tail": "  odd  spacing"', new)
        d = json.loads(new)
        self.assertEqual(list(d), ["settings", "mcpServers", "tail"])
        self.assertEqual(list(d["mcpServers"]), ["mine", "sidereus", "mailbox"])
        self.assertEqual(d["mcpServers"]["mine"], {"command": "a", "env": {"K": "secret"}})
        baks = os.listdir(self.trash)
        self.assertEqual(len(baks), 1)
        with open(os.path.join(self.trash, baks[0], "pi-mcp.json"), encoding="utf-8") as f:
            self.assertEqual(f.read(), text)

    def test_one_line_user_entry_byte_identical(self):
        mine = '"mine": {"command": "a", "args": ["-x"], "env": {"K": "secret"}}'
        for nl in ("\n", "\r\n"):
            text = '{\n  "mcpServers": {\n    %s\n  },\n  "z": 1\n}\n'.replace("\n", nl) % mine
            self._put(text)
            dry = HP._plan_mcp(self.files["mcp"])
            self.assertIsNone(dry["err"])
            new = dry["new_raw"].decode("utf-8")
            self.assertTrue(new.startswith(text.split(mine)[0] + mine + ","), new)
            self.assertTrue(new.endswith(nl + "  }," + nl + '  "z": 1' + nl + "}" + nl))
            self.assertEqual(list(json.loads(new)["mcpServers"]), ["mine", "sidereus", "mailbox"])
            body = [ln for ln in dry["diff"].splitlines()[2:] if not ln.startswith("@@")]
            # ⚠JSON needs a comma after the last user member: that line is the only -/+ pair, and only gains ","
            minus = [ln for ln in body if ln.startswith("-")]
            self.assertEqual(len(minus), 1)
            self.assertIn("+" + minus[0][1:] + ",", body)
            self.assertNotIn("secret", dry["diff"])
            if nl == "\n":
                self.assertTrue(all(ln.startswith("+    ") or ln.startswith("+      ") for ln in body if ln[0] == "+"))
            else:
                self.assertNotIn("\n", new.replace("\r\n", ""))   # no bare LF mixed into a CRLF file

    def test_one_line_object_stays_one_line(self):
        text = '{"mcpServers": {"mine": {"command": "a"}}, "z": 1}\n'
        self._put(text)
        self._apply()
        new = self._mcp()
        self.assertTrue(new.startswith('{"mcpServers": {"mine": {"command": "a"}, "sidereus": '), new)
        self.assertEqual(new.count("\n"), 1)
        self.assertEqual(json.loads(new)["mcpServers"], dict({"mine": {"command": "a"}}, **self._want()))

    def test_folded_names_not_readded(self):
        for name in ("sidereus", "side_reus"):
            self._put(json.dumps({"mcpServers": {name: {"command": "x"}, "Mail-box": {"command": "y"}}}))
            if os.path.exists(self.files["ts"]):
                os.remove(self.files["ts"])
            before = self._mcp()
            dry, _out = self._apply()
            self.assertEqual(dry["adds"], 1)    # only the .ts
            self.assertEqual(self._mcp(), before)

    def test_bad_mcp_refused(self):
        for text in ("[]", "{nope", '{"mcpServers": []}'):
            self._put(text)
            code, out = HP.connect({"plat": "pi", "dry": True})
            self.assertEqual(code, 400)
            self.assertIn("fix it by hand", out["err"])
            self.assertEqual(self._mcp(), text)

    def test_symlink_refused(self):
        real = os.path.join(self.tmp, "real.json")
        with open(real, "w", encoding="utf-8") as f:
            f.write("{}")
        os.symlink(real, self.files["mcp"])
        self.assertEqual(HP.connect({"plat": "pi", "dry": True}), (400, {"ok": False, "err": HC.SYMLINK}))
        self.assertEqual(HP.row()[0]["why"], HC.SYMLINK)
        os.remove(self.files["mcp"])
        ext = os.path.join(self.tmp, "ext")
        os.makedirs(ext)
        os.symlink(ext, os.path.dirname(self.files["ts"]))
        self.assertEqual(HP.connect({"plat": "pi", "dry": True})[0], 400)
        self.assertEqual(os.listdir(ext), [])

    def test_second_write_failure_keeps_first_backup(self):
        os.makedirs(os.path.dirname(self.files["mcp"]), exist_ok=True)
        with open(self.files["mcp"], "w", encoding="utf-8") as f:
            f.write('{"mcpServers": {}}')
        real, calls = HC._write, []

        def fake(plat, p, raw, new_raw):
            calls.append(p)
            return real(plat, p, raw, new_raw) if len(calls) == 1 else (500, {"ok": False, "err": "write failed ({e})"})
        code, out = HP.connect({"plat": "pi", "dry": True})
        with mock.patch.object(HC, "_write", fake):
            code, out = HP.connect({"plat": "pi", "dry": False, "base": out["base"]})
        self.assertEqual(code, 500)
        self.assertTrue(out["backup"] and os.path.exists(out["backup"]))   # mcp.json was written; its undo path is reported
        self.assertEqual(out["backups"], [out["backup"]])

    def test_base_mismatch_409(self):
        self._put("{}")
        code, out = HP.connect({"plat": "pi", "dry": True})
        self.assertEqual(out["base"], hashlib.sha256(b"{}" + b"\0").hexdigest())
        self.assertEqual(HP.connect({"plat": "pi", "dry": False, "base": "x"})[0], 409)
        self._put("{ }")
        self.assertEqual(HP.connect({"plat": "pi", "dry": False, "base": out["base"]})[0], 409)
        self.assertEqual(self._mcp(), "{ }")
        self.assertFalse(os.path.exists(self.files["ts"]))

    def test_differing_ts_partial_and_rewritten(self):
        self._apply()
        with open(self.files["ts"], "w", encoding="utf-8") as f:
            f.write("// old\n")
        r = HP.row()[0]
        self.assertEqual((r["state"], r["can"]), ("partial", True))
        dry, out = self._apply()
        self.assertEqual(dry["adds"], 1)
        self.assertTrue(out["backup"].endswith("pi-sidereus.ts"))
        self.assertEqual(HP.row()[0]["state"], "connected")

    def test_foreign_mailbox_entry_not_connected(self):
        self._apply()
        d = json.loads(self._mcp())
        d["mcpServers"]["mailbox"] = {"command": "uv", "args": ["--directory", "/x", "run", "mailbox-mcp"]}
        self._put(json.dumps(d))
        r = HP.row()[0]
        self.assertEqual((r["state"], r["can"], r["why"]), ("partial", False, HP.FOREIGN_MAILBOX))
        d["mcpServers"]["mailbox"] = {"command": "/a/ext-hooks/gemini_mailbox_mcp.sh", "args": ["gemini"]}
        self._put(json.dumps(d))
        self.assertEqual(HP.row()[0]["why"], HP.FOREIGN_MAILBOX)   # launcher with another platform key
        d["mcpServers"]["mailbox"] = {"command": "/b/ext-hooks/gemini_mailbox_mcp.sh", "args": ["pi"]}
        self._put(json.dumps(d))
        self.assertEqual((HP.row()[0]["state"], HP.row()[0]["why"]), ("connected", ""))

    def test_foreign_mailbox_ignored_on_windows(self):
        with mock.patch.object(HC.config, "IS_WIN", True):
            self._apply()
            d = json.loads(self._mcp())
            d["mcpServers"]["mailbox"] = {"command": "uv"}
            self._put(json.dumps(d))
            self.assertEqual(HP.row()[0]["state"], "connected")

    def test_windows_no_mailbox(self):
        with mock.patch.object(HC.config, "IS_WIN", True):
            self.assertEqual([n for n, _ in HP._servers()], ["sidereus"])   # the plan itself, not only the write
            self._apply()
        self.assertEqual([n for n, _ in HP._servers()], ["sidereus", "mailbox"])   # IS_WIN False on any runner
        self.assertEqual(list(json.loads(self._mcp())["mcpServers"]), ["sidereus"])

    def test_not_installed_no_row(self):
        shutil.rmtree(os.path.join(self.home, ".pi"))
        self.assertEqual(HP.row(), [])
        with mock.patch.object(HC, "_which", lambda n: "/bin/pi" if n == "pi" else None):
            self.assertEqual(HP.row()[0]["state"], "missing")

    def test_no_template(self):
        with mock.patch.object(HP, "TPL", os.path.join(self.tmp, "nope.ts")):
            self.assertEqual(HP.connect({"plat": "pi", "dry": True})[0], 400)
            self.assertEqual(HP.row()[0]["why"], "no ext-hooks")

    def test_python_is_one_absolute_path(self):
        # ⚠the extension spawns PY with no shell: `py -3` or a relative name never renders
        for v in ("py -3", "python3", ""):
            with mock.patch.object(HC, "_python", lambda v=v: v):
                self.assertIsNone(HP._render())
        self.assertIn(json.dumps(PY).encode("utf-8"), HP._render())
        for mac, exe in ((True, "/x/python3"), (False, "/x/python3"), (False, "C:\\Py\\python.exe")):
            with mock.patch.object(HC.config, "IS_MAC", mac), mock.patch.object(HC.sys, "executable", exe), \
                    mock.patch.object(HC.shutil, "which", lambda *a, **k: None):
                self.assertEqual(_REAL_PYTHON(), exe)

    def test_routes(self):
        self.assertEqual(post("/api/hooks/connect", {"plat": "pi", "dry": True})[0], 403)
        code, out = post("/api/hooks/connect", {"plat": "pi", "dry": True}, origin=ORIGIN)[:2]
        self.assertEqual(code, 200)
        self.assertEqual(set(out), {"ok", "diff", "base", "adds"})
        self.assertFalse(os.path.exists(self.files["mcp"]))
        with mock.patch.object(sidereus("routes_get"), "hook_connect_list", lambda: []):
            code, out = get("/api/hooks/connect")
        self.assertEqual(code, 200)
        self.assertEqual([x["plat"] for x in out["plats"]], ["pi"])


if __name__ == "__main__":
    unittest.main()
