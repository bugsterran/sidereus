"""Settings › Diagnostics (sidereus/hook_diag.py, hook_fields.py, GET /api/diag): hook overlaps, silent plugin hooks,
plugin versions, CLAUDE.md shadowing AGENTS.md.

⚠Every home, account dir, project and docs path points at a temp dir; scripts are fixtures and are never executed.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tests._load import load, sidereus, ROOT
from tests.test_prefs import get

cs = load()
HD = sidereus("hook_diag")
HF = sidereus("hook_fields")
CR = sidereus("claude_roots")
CX = sidereus("ctxsrc")
TI = sidereus("toolinv")
P = sidereus("prefs")
F = sidereus("features")
FIX = os.path.join(ROOT, "tests", "fixtures", "hookdiag", "scripts")
SENT = "SENTINEL_SCRIPT_BODY"
DOC = "| Script | Event |\n|---|---|\n| `mailbox_stop.py` | `Stop` |\n| `pl_mark.py` | `PreToolUse` |\n"


def _w(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj))


def _hk(ev, cmd, matcher=""):
    return {ev: [{"matcher": matcher, "hooks": [{"type": "command", "command": cmd}]}]}


class HookDiag(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-hd-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        t = self.tmp
        self.prim, self.home, self.sh = os.path.join(t, "prim"), os.path.join(t, "home"), os.path.join(t, "sidhooks")
        self.proj = os.path.join(t, "proj")
        os.makedirs(os.path.join(self.prim, "projects"))
        os.makedirs(self.home)
        os.makedirs(self.proj)
        _w(os.path.join(self.sh, "mailbox_stop.py"), "print('x')\n")
        _w(os.path.join(t, "HOOKS.md"), DOC)
        self.plug = os.path.join(self.prim, "plugins", "cache", "mk", "omx", "5.6.2")
        shutil.copytree(FIX, os.path.join(self.plug, "scripts"))
        os.makedirs(os.path.join(self.prim, "plugins", "cache", "mk", "omx", "3.7.2", "hooks"))   # stale cache dir
        _w(os.path.join(self.prim, "plugins", "cache", "mk", "omx", "3.7.2", "hooks", "hooks.json"),
           {"hooks": _hk("Stop", "node ${CLAUDE_PLUGIN_ROOT}/scripts/msg_only.mjs")})
        root = "node \"${CLAUDE_PLUGIN_ROOT}\"/scripts/"
        hooks = {}
        hooks.update(_hk("Stop", root + "run.cjs \"${CLAUDE_PLUGIN_ROOT}\"/scripts/msg_only.mjs"))
        hooks.update(_hk("SessionStart", "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/hso.py"))
        hooks.update(_hk("UserPromptSubmit", root + "mixed.mjs", "*"))
        _w(os.path.join(self.plug, "hooks", "hooks.json"), {"description": "d", "hooks": hooks})
        _w(os.path.join(self.prim, "plugins", "installed_plugins.json"),
           {"version": 2, "plugins": {"omx@mk": [{"installPath": self.plug, "version": "5.6.2"}]}})
        _w(os.path.join(self.prim, "settings.json"),
           {"hooks": _hk("Stop", "python3 " + os.path.join(self.sh, "mailbox_stop.py")), "env": {"TOKEN": SENT}})
        _w(os.path.join(self.proj, ".claude", "settings.json"), {"hooks": _hk("Stop", "bash ./guard.sh --x", "")})
        for p in (mock.patch.object(CR, "SCAN_HOME", self.home), mock.patch.object(CR, "claude_home", lambda: self.prim),
                  mock.patch.object(P, "CONFIG_PATH", os.path.join(t, "config.local.json")),
                  mock.patch.object(CX, "CLAUDE_DIR", self.prim), mock.patch.object(CX, "CLAUDE_JSON", os.path.join(t, "cj.json")),
                  mock.patch.object(TI, "known_projects", lambda: [self.proj]),
                  mock.patch.object(HD, "DX_HOOK_DIRS", (self.sh,)), mock.patch.object(HD, "DX_HOOKS_DOC", os.path.join(t, "HOOKS.md")),
                  mock.patch.dict(HD._DIAG_CACHE, {"t": 0.0, "v": None}), mock.patch.dict(HD._DX_NAMES, {"key": None, "v": frozenset()})):
            p.start()
            self.addCleanup(p.stop)
        CR.reset()
        self.addCleanup(CR.reset)
        HF._HF_CACHE.clear()

    def _diag(self):
        HD._DIAG_CACHE["v"] = None
        code, out = HD.diag()
        self.assertEqual(code, 200)
        return out

    def test_R1_overlap_per_event(self):
        out = self._diag()
        self.assertEqual(out["sidereus"], {"Stop": ["mailbox_stop.py"]})
        ov = {(o["src"], o["cmd"]) for o in out["overlaps"]}
        self.assertEqual(ov, {("plugin", "msg_only.mjs"), ("project", "guard.sh")})   # wrapper shows the inner script
        pl = [o for o in out["overlaps"] if o["src"] == "plugin"][0]
        self.assertEqual((pl["event"], pl["name"], pl["matcher"]), ("Stop", "omx", ""))
        self.assertFalse(any(o["event"] != "Stop" for o in out["overlaps"]))   # only events a Sidereus hook handles

    def test_R2_shadow_path(self):
        _w(os.path.join(self.proj, "AGENTS.md"), "rules\n")
        _w(os.path.join(self.proj, "CLAUDE.md"), "other " + SENT + "\n")
        self.assertEqual(self._diag()["shadow"], [{"proj": self.proj, "claude": "CLAUDE.md", "agents": "AGENTS.md"}])

    def test_R2_symlink_or_import_not_flagged(self):
        _w(os.path.join(self.proj, "AGENTS.md"), "rules\n")
        os.symlink("AGENTS.md", os.path.join(self.proj, "CLAUDE.md"))
        self.assertEqual(self._diag()["shadow"], [])
        os.unlink(os.path.join(self.proj, "CLAUDE.md"))
        _w(os.path.join(self.proj, "CLAUDE.md"), "# x\n@AGENTS.md\n")
        self.assertEqual(self._diag()["shadow"], [])
        os.unlink(os.path.join(self.proj, "AGENTS.md"))
        self.assertEqual(self._diag()["shadow"], [])

    def _j(self, name, ev):
        return HF.judge(os.path.realpath(os.path.join(FIX, name)), ev)

    def test_R3_contract_fixtures(self):
        self.assertEqual(self._j("msg_only.mjs", "Stop"), ("silent", ["message"]))
        self.assertEqual(self._j("hso.py", "SessionStart"), ("ok", []))
        self.assertEqual(self._j("mixed.mjs", "UserPromptSubmit"), ("partial", ["message"]))
        self.assertEqual(self._j("perm.mjs", "PermissionRequest"), ("ok", []))
        self.assertEqual(self._j("exit2.py", "Stop"), ("ok", ["message"]))
        self.assertEqual(self._j("state_write.mjs", "Stop"), ("ok", []))   # a state-file JSON.stringify is not output
        self.assertEqual(self._j("hso.py", "NoSuchEvent")[0], "unknown")
        b = os.path.join(self.tmp, "bin")
        with open(b, "wb") as f:
            f.write(b"\xcf\xfa\xed\xfe" + b"\0" * 64)
        self.assertEqual(HF.judge(b, "Stop")[0], "unknown")
        # run.cjs wrapper: the inner script is the one scanned
        cmd = 'node "${CLAUDE_PLUGIN_ROOT}"/scripts/run.cjs "${CLAUDE_PLUGIN_ROOT}"/scripts/msg_only.mjs'
        p = HF.resolve(cmd, self.plug, (self.plug,), self.home)
        self.assertEqual(os.path.basename(p), "msg_only.mjs")
        self.assertEqual(HF.resolve(cmd, self.plug, (self.home,), self.home), "")   # outside the roots
        out = self._diag()
        self.assertEqual(sorted((s["event"], s["verdict"], s["unread"][0]) for s in out["silent"]),
                         [("Stop", "silent", "message"), ("UserPromptSubmit", "partial", "message")])

    def test_R3_never_executes(self):
        def boom(*a, **k):
            raise AssertionError("executed")
        with mock.patch.object(subprocess, "Popen", boom), mock.patch.object(os, "system", boom):
            self.assertTrue(self._diag()["ok"])
        for m in (HD, HF):
            self.assertNotIn("subprocess", vars(m))

    def test_R4_version_from_installed_plugins(self):
        pl = self._diag()["plugins"]
        self.assertEqual(len(pl), 1)   # the stale 3.7.2 cache dir is not a plugin
        self.assertEqual({k: pl[0][k] for k in ("name", "market", "version", "on", "known", "checked")},
                         {"name": "omx", "market": "mk", "version": "5.6.2", "on": True, "known": True, "checked": True})

    def test_metadata_only(self):
        _w(os.path.join(self.proj, "AGENTS.md"), "rules\n")
        _w(os.path.join(self.proj, "CLAUDE.md"), SENT + "\n")
        self.assertNotIn(SENT, json.dumps(self._diag()))

    def test_metadata_only_inline_commands(self):
        hooks = {"Stop": [{"matcher": "", "hooks": [{"type": "command", "command": c} for c in (
            'node -e "if(/x/.test(cmd)){console.error(\'%s\')}"' % SENT,
            'bash -c "jq -r .x | grep %s"' % SENT,
            'if [ -f %s ]; then echo hi; fi' % SENT,
            'python3 -c "print(\'%s\')"' % SENT)]}]}
        _w(os.path.join(self.proj, ".claude", "settings.json"), {"hooks": hooks})
        out = self._diag()
        self.assertNotIn(SENT, json.dumps(out))
        cmds = sorted(o["cmd"] for o in out["overlaps"] if o["src"] == "project")
        self.assertEqual(cmds, ["inline node", "inline python", "inline shell", "inline shell"])

    def test_oversize_json_skipped_and_matcher_capped(self):
        _w(os.path.join(self.proj, ".claude", "settings.json"),
           {"hooks": _hk("Stop", "bash ./guard.sh", "x" * 300 + "\x01|y"), "pad": "p" * (HD.DX_JSON_MAX + 1)})
        self.assertNotIn("guard.sh", {o["cmd"] for o in self._diag()["overlaps"]})   # oversize: skipped, no crash
        _w(os.path.join(self.proj, ".claude", "settings.json"), {"hooks": _hk("Stop", "bash ./guard.sh", "Edit|" + "x" * 300 + "\x01")})
        m = [o["matcher"] for o in self._diag()["overlaps"] if o["cmd"] == "guard.sh"][0]
        self.assertEqual((len(m), m[:5], "\x01" in m), (HD.DX_NAME_MAX, "Edit|", False))

    def test_route_and_feature_off_404(self):
        code, out = get("/api/diag")
        self.assertEqual((code, out["ok"]), (200, True))
        with mock.patch.object(F, "_TOGGLES", {"diag": False}):
            self.assertEqual(get("/api/diag"), (404, {"error": "feature off"}))


if __name__ == "__main__":
    unittest.main()
