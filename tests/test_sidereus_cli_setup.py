"""sidereus_cli.py setup-claude: prints real paths, writes no file (open-for-write and os.replace must not be called)."""
import builtins
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("sidereus_cli_setup_t", os.path.join(ROOT, "sidereus_cli.py"))
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class SetupClaude(unittest.TestCase):
    def run_cli(self, *args):
        real_open = builtins.open
        writes = []

        def guarded_open(file, mode="r", *a, **k):
            if any(c in mode for c in "wax+"):
                writes.append(file)
            return real_open(file, mode, *a, **k)
        out = io.StringIO()
        with mock.patch("builtins.open", guarded_open), \
                mock.patch.object(cli.os, "replace") as rep, \
                mock.patch.dict(os.environ, {"LANG": "en_US.UTF-8"}), \
                contextlib.redirect_stdout(out):
            rc = cli.main(["setup-claude"] + list(args))
        self.assertEqual(writes, [])
        rep.assert_not_called()
        return rc, out.getvalue()

    def test_prints_real_paths(self):
        rc, out = self.run_cli()
        self.assertEqual(rc, 0)
        self.assertIn("claude mcp add --scope user sidereus -- ", out)
        self.assertIn(os.path.join(cli.CODE_DIR, "mcp", "sidereus_mcp.py"), out)
        self.assertIn("claude mcp add --scope user mailbox", out)
        block = json.loads(out[out.index("{"):])
        hooks = block["hooks"]
        with open(os.path.join(ROOT, "plugin", "hooks", "hooks.json"), encoding="utf-8") as f:
            plug = json.load(f)["hooks"]
        # same events, matchers, timeouts and scripts as the plugin (mailbox_wake was missing from a hand-kept list)
        self.assertEqual(sorted(hooks), sorted(plug))
        for ev, groups in plug.items():
            self.assertEqual([g.get("matcher") for g in hooks[ev]], [g.get("matcher") for g in groups])
            for g, pg in zip(hooks[ev], groups):
                for h, ph in zip(g["hooks"], pg["hooks"]):
                    name = ph["command"].split("/hooks/")[-1].rstrip('"')   # last path: the launcher comes first
                    path = os.path.join(cli.CODE_DIR, "hooks", name)
                    self.assertTrue(h["command"].endswith(path), h["command"])
                    self.assertTrue(os.path.isfile(path), path)
                    self.assertNotIn("CLAUDE_PLUGIN_ROOT", h["command"])
                    self.assertEqual({k: v for k, v in h.items() if k != "command"},
                                     {k: v for k, v in ph.items() if k != "command"})
        wake = [h for g in hooks["Stop"] for h in g["hooks"] if h["command"].endswith("mailbox_wake.py")]
        self.assertEqual(len(wake), 1)
        self.assertTrue(wake[0].get("asyncRewake"))

    def test_mailbox_mcp_dir_filled(self):
        d = tempfile.mkdtemp()
        try:
            rc, out = self.run_cli("--mailbox-mcp", d)
        finally:
            os.rmdir(d)
        self.assertEqual(rc, 0)
        self.assertIn("uv --directory %s run mailbox-mcp" % os.path.abspath(d), out)
        self.assertNotIn("<path-to-mailbox-mcp>", out)

    def test_windows_always_double_quotes(self):
        with mock.patch.object(cli, "IS_WIN", True):
            for p in (r"C:\a&b\x.py", r"C:\R(1)\x.py", r"C:\p%x%!\x.py", r"C:\plain\x.py", r"C:\a b\x.py"):
                self.assertEqual(cli._shq(p), '"%s"' % p)
        with mock.patch.object(cli, "IS_WIN", False):
            self.assertEqual(cli._shq("/a/b.py"), "/a/b.py")

    def test_bad_mailbox_dir_is_usage_error(self):
        rc, out = self.run_cli("--mailbox-mcp", os.path.join(os.devnull, "nope"))
        self.assertEqual(rc, 2)


class SetupPython(unittest.TestCase):
    """setup_python: the documented /usr/bin/python3 only when it runs the same interpreter (probe faked, no subprocess)."""
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.exe = os.path.join(self.d, "python3")
        self.other = os.path.join(self.d, "python3.14")
        for p in (self.exe, self.other):
            with open(p, "w", encoding="utf-8"):
                pass
        self.doc = os.path.join(self.d, "doc-python3")
        with open(self.doc, "w", encoding="utf-8"):
            pass

    def tearDown(self):
        for p in (self.exe, self.other, self.doc):
            os.remove(p)
        os.rmdir(self.d)

    def pick(self, probed, exe=None, win=False):
        with mock.patch.object(cli, "IS_MAC", not win):
            return cli.setup_python(exe or self.exe, probe=lambda p: probed, doc=self.doc)

    def test_same_interpreter_prints_documented_path(self):
        self.assertEqual(self.pick(self.exe), self.doc)

    def test_other_interpreter_keeps_sys_executable(self):
        self.assertEqual(self.pick(self.other), self.exe)

    def test_probe_failure_keeps_sys_executable(self):
        self.assertEqual(self.pick(""), self.exe)

    def test_missing_documented_python(self):
        with mock.patch.object(cli, "IS_MAC", True):
            self.assertEqual(cli.setup_python(self.exe, probe=lambda p: self.exe, doc=os.path.join(self.d, "absent")),
                             self.exe)

    def test_non_mac_untouched(self):
        self.assertEqual(self.pick(self.exe, win=True), self.exe)


if __name__ == "__main__":
    unittest.main()
