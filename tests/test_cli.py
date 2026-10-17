"""sidereus_cli.py: first-run config, single spawn, stop guard, service builders — temp DATA_DIR, nothing executed."""
import importlib.util
import io
import json
import os
import plistlib
import shutil
import sys
import tempfile
import unittest

from tests._fs import assert_mode
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_cli():
    spec = importlib.util.spec_from_file_location("sidereus_cli_t", os.path.join(ROOT, "sidereus_cli.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Resp:
    status = 200
    headers = {}

    def close(self):
        pass


class _Proc:
    pid = 43210


class CliBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-cli-")
        self.cfg = os.path.join(self.tmp, "config.local.json")
        self.env = mock.patch.dict(os.environ, {"MAILBOX_DIR": self.tmp, "MAILBOX_CONFIG": self.cfg, "SIDEREUS_PORT": "",
                                                 "LC_ALL": "en_US.UTF-8"})
        self.env.start()
        self.cli = _load_cli()
        self.cli.mailbox_config._cache = None
        self.up = False          # does the fake /api/state answer?
        self.foreign = 0         # non-zero: a non-Sidereus server on the port answers this HTTP status
        self.ident = None        # X-Sidereus-Instance the fake sends; None = this data dir's id
        self.spawned = []
        self.tabs = []
        self.ran = []
        self.killed = []
        c = self.cli
        c._urlopen = self._fake_urlopen
        c._Popen = self._fake_popen
        c._open_tab = self.tabs.append
        self.called = []
        self.call_env = []
        c._call = lambda argv, env=None: self.called.append(argv) or self.call_env.append(env) or 0
        c._run = lambda argv: self.ran.append(argv) or 1
        c._sleep = lambda s: None
        c._home = lambda p: os.path.join(self.tmp, "home")
        c.pid_alive = lambda pid: True
        c.default_id = lambda: "tester-sidereus"
        self._kill = mock.patch.object(c.os, "kill", lambda pid, sig: self.killed.append(pid))
        self._kill.start()
        self._out = mock.patch("sys.stdout", new=open(os.devnull, "w", encoding="utf-8"))
        self._out.start()

    def tearDown(self):
        sys.stdout.close()
        self._out.stop()
        self._kill.stop()
        self.env.stop()
        self.cli.mailbox_config._cache = None
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fake_urlopen(self, url, timeout=None):
        assert url.startswith("http://127.0.0.1:"), url
        if self.foreign:
            err = OSError("http error")
            err.code = self.foreign      # what urllib's HTTPError carries
            raise err
        if not self.up:
            raise OSError("refused")
        r = _Resp()
        r.headers = {"X-Sidereus-Instance": self.ident if self.ident is not None
                     else self.cli.mailbox_config.instance_id(self.tmp)}
        return r

    def _fake_popen(self, argv, **kw):
        self.spawned.append((argv, kw))
        self.up = True
        return _Proc()


class FirstRun(CliBase):
    def test_first_run_creates_config_no_tab(self):
        self.assertEqual(self.cli.main(["start"]), 0)
        with open(self.cfg, encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertEqual(cfg["self"]["ids"], ["tester-sidereus"])
        self.assertEqual(cfg["self"]["aliases"], ["tester-sidereus"])
        assert_mode(self, self.cfg, 0o600)
        self.assertEqual(len(self.spawned), 1)
        self.assertEqual(self.tabs, [])     # a tab only with --open
        argv, kw = self.spawned[0]
        self.assertIn("--no-open", argv)
        self.assertTrue(kw.get("start_new_session") or kw.get("creationflags"))
        with open(os.path.join(self.tmp, "sidereus.pid"), encoding="utf-8") as f:
            rec = json.load(f)
        self.assertEqual((rec["pid"], rec["port"]), (43210, 8799))

    def test_second_run_no_tab_config_unchanged(self):
        self.cli.main(["start"])
        with open(self.cfg, "rb") as f:
            before = f.read()
        self.up = False
        self.spawned.clear()
        self.tabs.clear()
        self.cli.pid_alive = lambda pid: False   # previous viewer gone
        self.assertEqual(self.cli.main(["start"]), 0)
        with open(self.cfg, "rb") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual(len(self.spawned), 1)
        self.assertEqual(self.tabs, [])

    def test_generated_config_drops_copy_note_and_default_saver_keys(self):
        self.assertTrue(self.cli.ensure_config())
        with open(self.cfg, encoding="utf-8") as f:
            cfg = json.load(f)
        for k in ("_comment", "saver_view_path", "saver_hook_dir", "_saver_view_comment"):
            self.assertNotIn(k, cfg)
        self.assertEqual(self.cli.mailbox_config.load(reload=True)["saver_hook_dir"], "~/.claude/hooks")

    def test_existing_config_never_overwritten(self):
        with open(self.cfg, "w", encoding="utf-8") as f:
            f.write("{}\n")
        self.assertFalse(self.cli.ensure_config())
        with open(self.cfg, encoding="utf-8") as f:
            self.assertEqual(f.read(), "{}\n")


class OpenAndDemo(CliBase):
    def test_open_flag_opens_one_tab(self):
        self.assertEqual(self.cli.main(["start", "--open"]), 0)
        self.assertEqual(self.tabs, ["http://127.0.0.1:8799/"])
        self.up = True
        self.tabs.clear()
        self.assertEqual(self.cli.main(["start", "--open"]), 0)    # already running: still one tab
        self.assertEqual(self.tabs, ["http://127.0.0.1:8799/"])

    def test_demo_runs_foreground_writes_nothing(self):
        self.assertEqual(self.cli.main(["start", "--demo"]), 0)
        self.assertEqual(len(self.called), 1)
        argv = self.called[0]
        self.assertEqual(argv[0], sys.executable)
        self.assertTrue(argv[1].endswith("chat_server.py"))
        self.assertEqual(argv[2:], ["--demo", "--port", "18799", "--no-open"])
        self.assertFalse(os.path.exists(self.cfg))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "sidereus.pid")))
        self.assertEqual((self.spawned, self.tabs), ([], []))

    def test_demo_points_data_dir_at_removed_temp(self):
        # sidereus/config.py mkdirs DATA_DIR at import, so the child must not see the real one.
        seen = []
        def run(argv, env=None):
            seen.append((env["MAILBOX_DIR"], os.path.isdir(env["MAILBOX_DIR"]), "MAILBOX_CONFIG" in env))
            return 0
        self.cli._call = run
        self.assertEqual(self.cli.main(["start", "--demo"]), 0)
        d, existed, has_cfg = seen[0]
        self.assertNotEqual(d, self.tmp)
        self.assertTrue(existed)
        self.assertFalse(has_cfg)
        self.assertFalse(os.path.exists(d))

    def test_missing_config_warning_silent_only_in_demo(self):
        mc = self.cli.mailbox_config
        for argv, want in ((["chat_server.py", "--demo"], False), (["chat_server.py"], True)):
            mc._warned.discard("missing")
            err = io.StringIO()
            with mock.patch.object(sys, "argv", argv), mock.patch("sys.stderr", new=err):
                mc.load(reload=True)
            self.assertEqual("not found" in err.getvalue(), want, argv)
            self.assertFalse(mc.FILE_OK)
        mc._warned.discard("missing")

    def test_run_fg_forwards_sigterm(self):
        import signal as _sig
        import subprocess as _sp
        class P:
            terminated = False
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def terminate(self): P.terminated = True
            def kill(self): pass
            def wait(self):
                _sig.getsignal(_sig.SIGTERM)(_sig.SIGTERM, None)
                return -15
        before = _sig.getsignal(_sig.SIGTERM)
        with mock.patch.object(_sp, "Popen", lambda argv, env=None: P()):
            self.assertEqual(self.cli._run_fg(["x"]), 143)
        self.assertTrue(P.terminated)
        self.assertIs(_sig.getsignal(_sig.SIGTERM), before)

    def test_demo_port_and_open(self):
        self.assertEqual(self.cli.main(["start", "--demo", "--port", "9000", "--open"]), 0)
        self.assertEqual(self.called[0][2:], ["--demo", "--port", "9000"])
        self.assertFalse(os.path.exists(self.cfg))

    def test_demo_ctrl_c_returns_130(self):
        def stop(argv, env=None):
            raise KeyboardInterrupt
        self.cli._call = stop
        self.assertEqual(self.cli.main(["start", "--demo"]), 130)

    def test_demo_with_install_service_rejected(self):
        self.assertEqual(self.cli.main(["start", "--demo", "--install-service"]), 2)
        self.assertEqual((self.called, self.ran, self.spawned), ([], [], []))
        self.assertFalse(os.path.exists(self.cfg))


class ModuleEntry(unittest.TestCase):
    def test_python_m_sidereus_delegates(self):
        before = list(sys.path)
        with mock.patch.object(sys, "path", list(sys.path)):
            cli = _load_cli()
        seen = []
        cli.main = lambda argv=None: seen.append(argv) or 7
        spec = importlib.util.spec_from_file_location("sidereus_main_t", os.path.join(ROOT, "sidereus", "__main__.py"))
        mod = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {"sidereus_cli": cli}), mock.patch.object(sys, "path", list(sys.path)):
            with self.assertRaises(SystemExit) as cm:
                spec.loader.exec_module(mod)
        self.assertEqual(cm.exception.code, 7)
        self.assertEqual(seen, [None])
        self.assertEqual(sys.path, before)


class SpawnGuard(CliBase):
    def test_port_answering_no_spawn_no_tab(self):
        self.up = True
        self.assertEqual(self.cli.main(["start", "--port", "8811"]), 0)
        self.assertEqual(self.spawned, [])
        self.assertEqual(self.tabs, [])

    def test_other_sidereus_on_port_is_not_already_running(self):
        self.up = True
        self.ident = "0123456789abcdef"      # another data dir's viewer
        buf = io.StringIO()
        with mock.patch("sys.stdout", new=buf):
            self.assertEqual(self.cli.main(["start", "--port", "8811"]), 1)
        self.assertIn("another Sidereus", buf.getvalue())
        self.assertNotIn("Already running", buf.getvalue())
        self.assertEqual((self.spawned, self.tabs), ([], []))
        with open(self.cfg, encoding="utf-8") as f:
            self.assertEqual(json.load(f).get("port"), 8799)   # 8811 not saved

    def test_no_header_ours_only_with_live_record(self):
        self.up = True
        self.ident = ""                      # an older viewer without the header
        self.assertEqual(self.cli.main(["start", "--port", "8811"]), 1)
        with open(os.path.join(self.tmp, "sidereus.pid"), "w", encoding="utf-8") as f:
            json.dump({"pid": 999, "port": 8811, "started": 1}, f)
        self.assertEqual(self.cli.main(["start", "--port", "8811"]), 0)
        self.assertEqual(self.spawned, [])

    def test_recorded_live_pid_is_waited_not_respawned(self):
        with open(self.cfg, "w", encoding="utf-8") as f:
            f.write("{}\n")
        with open(os.path.join(self.tmp, "sidereus.pid"), "w", encoding="utf-8") as f:
            json.dump({"pid": 999, "port": 8799, "started": 1}, f)
        calls = []

        def slow(url, timeout=None):
            calls.append(url)
            if len(calls) < 3:
                raise OSError("booting")
            return _Resp()
        self.cli._urlopen = slow
        self.assertEqual(self.cli.main(["start"]), 0)
        self.assertEqual(self.spawned, [])

    def test_bad_port_rejected(self):
        for bad in (["x"], ["70000"], ["80"], []):
            buf = io.StringIO()
            with mock.patch("sys.stdout", new=buf):
                self.assertEqual(self.cli.main(["start", "--port"] + bad), 2)
            self.assertEqual(buf.getvalue().strip().count("\n"), 0)
            self.assertIn("1024–65535", buf.getvalue())
        self.assertEqual(self.spawned, [])

    def test_help_exits_zero(self):
        for argv in (["--help"], ["-h"], ["help"], ["start", "--help"]):
            self.assertEqual(self.cli.main(argv), 0)
        self.assertEqual(self.spawned, [])
        self.assertEqual(self.cli.main(["bogus"]), 2)


class WindowsSpawn(CliBase):
    def test_windows_hidden_console_and_utf8(self):
        self.cli.IS_WIN = True
        self.cli.spawn(8799)
        _argv, kw = self.spawned[0]
        self.assertEqual(kw["creationflags"], 0x08000000 | 0x00000200)   # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        self.assertFalse(kw["creationflags"] & 0x8)                      # never DETACHED_PROCESS
        self.assertEqual(kw["env"]["PYTHONUTF8"], "1")
        self.assertNotIn("start_new_session", kw)
        self.assertTrue(kw["close_fds"])

    def test_posix_spawn_unchanged(self):
        self.cli.IS_WIN = False
        self.cli.spawn(8799)
        _argv, kw = self.spawned[0]
        self.assertTrue(kw["start_new_session"])
        self.assertNotIn("creationflags", kw)
        self.assertNotIn("env", kw)

    def test_sidereus_cmd_launcher(self):
        with open(os.path.join(ROOT, "sidereus.cmd"), encoding="utf-8") as f:
            txt = f.read()
        self.assertIn('"%~dp0sidereus_cli.py" %*', txt)
        self.assertTrue(txt.lower().startswith("@echo off"))


class PortConfig(CliBase):
    def _cfg_port(self):
        with open(self.cfg, encoding="utf-8") as f:
            return json.load(f).get("port")

    def test_start_port_is_saved_after_it_answers(self):
        self.assertEqual(self.cli.main(["start", "--port", "9123"]), 0)
        self.assertEqual(self._cfg_port(), 9123)
        argv, _kw = self.spawned[0]
        self.assertEqual(argv[-2:], ["--port", "9123"])   # not saved yet at spawn time
        self.assertEqual(self.tabs, [])

    def test_start_port_not_saved_when_it_never_answers(self):
        self.cli._Popen = lambda argv, **kw: self.spawned.append(argv) or _Proc()
        self.cli.pid_alive = lambda pid: False
        tick = iter(range(0, 1000, 5))
        self.cli._now = lambda: next(tick)       # fake clock: the wait times out at once
        self.assertEqual(self.cli.main(["start", "--port", "9123"]), 1)
        self.assertEqual(self._cfg_port(), 8799)    # the example default, not 9123

    def test_foreign_server_on_port_is_an_error(self):
        self.foreign = 404       # e.g. `python3 -m http.server 8799`
        buf = io.StringIO()
        with mock.patch("sys.stdout", new=buf):
            self.assertEqual(self.cli.main(["start", "--port", "9123"]), 1)
        self.assertIn("isn't Sidereus", buf.getvalue())
        self.assertEqual((self.spawned, self.tabs), ([], []))
        self.assertEqual(self._cfg_port(), 8799)    # the example default, not 9123
        self.assertEqual(self.cli.main(["start", "--port", "9123", "--install-service"]), 1)

    def test_start_without_flag_uses_config_port(self):
        with open(self.cfg, "w", encoding="utf-8") as f:
            json.dump({"_comment": "x", "port": 9124}, f)
        self.assertEqual(self.cli.main(["start"]), 0)
        with open(os.path.join(self.tmp, "sidereus.pid"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["port"], 9124)
        with open(self.cfg, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"_comment": "x", "port": 9124})   # untouched

    def test_save_port_keeps_other_keys_and_skips_broken_file(self):
        with open(self.cfg, "w", encoding="utf-8") as f:
            json.dump({"self": {"ids": ["a"]}, "zzz": 1}, f)
        self.assertTrue(self.cli.save_port(9125))
        with open(self.cfg, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"self": {"ids": ["a"]}, "zzz": 1, "port": 9125})
        with open(self.cfg, "w", encoding="utf-8") as f:
            f.write("{broken")
        self.assertFalse(self.cli.save_port(9126))
        with open(self.cfg, encoding="utf-8") as f:
            self.assertEqual(f.read(), "{broken")

    def test_install_service_plist_follows_config(self):
        self.cli.IS_MAC, self.cli.IS_WIN = True, False
        self.cli.wait_up = lambda port: 200   # nothing really starts
        self.cli.main(["start", "--port", "9127", "--install-service"])
        self.assertEqual(self._cfg_port(), 9127)
        path = self.cli.mac_plist_path(self.cli.mac_label())
        with open(path, "rb") as f:
            args = plistlib.load(f)["ProgramArguments"]
        self.assertEqual(args[-1], "--no-open")   # no baked-in --port: a later «포트» change applies after a restart
        self.assertEqual(self.cli.server_argv("py", 9000)[-2:], ["--port", "9000"])   # differs from config -> flag

    def test_env_overrides_config(self):
        with open(self.cfg, "w", encoding="utf-8") as f:
            json.dump({"port": 9128}, f)
        with mock.patch.dict(os.environ, {"SIDEREUS_PORT": "9129"}):
            self.assertEqual(self.cli.configured_port(), 9129)
        self.assertEqual(self.cli.configured_port(), 9128)


class Stop(CliBase):
    def _pidfile(self, pid=555, port=8799):
        with open(os.path.join(self.tmp, "sidereus.pid"), "w", encoding="utf-8") as f:
            json.dump({"pid": pid, "port": port, "started": 1}, f)

    def test_no_pid_file_is_noop(self):
        self.up = True
        self.assertEqual(self.cli.main(["stop"]), 0)
        self.assertEqual(self.killed, [])

    def test_kills_only_recorded_live_answering_pid(self):
        self._pidfile()
        self.up = True
        self.cli._sleep = lambda s: setattr(self, "up", False)
        self.assertEqual(self.cli.main(["stop"]), 0)
        self.assertEqual(self.killed, [555])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "sidereus.pid")))

    def test_dead_pid_not_killed(self):
        self._pidfile()
        self.up = True
        self.cli.pid_alive = lambda pid: False
        self.cli.main(["stop"])
        self.assertEqual(self.killed, [])

    def test_service_owned_left_alone(self):
        self._pidfile()
        self.up = True
        self.cli.service_installed = lambda: True
        self.cli.main(["stop"])
        self.assertEqual(self.killed, [])
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "sidereus.pid")))

    def test_status_writes_nothing(self):
        before = sorted(os.listdir(self.tmp))
        self.assertEqual(self.cli.main(["status"]), 0)
        self.assertEqual(sorted(os.listdir(self.tmp)), before)

    def _probed_ports(self, argv):
        seen = []
        self.cli.answering = lambda port: seen.append(port) or 0
        self.cli.main(argv)
        return seen

    def test_status_uses_recorded_port_without_flag(self):
        self._pidfile(port=9123)
        self.assertEqual(self._probed_ports(["status"]), [9123])
        self.assertEqual(self._probed_ports(["status", "--port", "9200"]), [9200])   # explicit flag wins

    def test_status_default_port_without_record(self):
        self.assertEqual(self._probed_ports(["status"]), [8799])

    def _status_out(self):
        buf = io.StringIO()
        with mock.patch("sys.stdout", new=buf):
            self.assertEqual(self.cli.main(["status"]), 0)
        return buf.getvalue()

    def test_status_dead_recorded_pid(self):
        self._pidfile()
        self.cli.pid_alive = lambda pid: False
        self.assertIn("555 (port 8799) (not running)", self._status_out())

    def test_status_unowned_answer_without_record(self):
        self.up = True
        self.assertIn("something answers on 8799 (no run record)", self._status_out())
        self.foreign = 404
        self.assertIn("isn't Sidereus", self._status_out())

    def _busy(self):
        import socket
        err = OSError("timed out")
        err.reason = socket.timeout("timed out")      # urllib wraps a connect/read timeout in URLError.reason
        clock = [0.0]
        self.cli._now = lambda: clock.__setitem__(0, clock[0] + 1) or clock[0]

        def slow(url, timeout=None):
            raise err
        self.cli._urlopen = slow

    def test_answering_timeout_is_busy_not_down(self):
        self._busy()
        self.assertEqual(self.cli.answering(8799), self.cli.BUSY)
        self.cli._urlopen = self._fake_urlopen
        self.assertEqual(self.cli.answering(8799), 0)          # refused stays «down»

    def test_stop_busy_live_pid_keeps_record(self):
        self._pidfile()
        self._busy()
        self.assertEqual(self.cli.main(["stop"]), 1)
        self.assertEqual(self.killed, [555])                    # a slow server is still ours to stop
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "sidereus.pid")))

    def test_start_busy_port_no_spawn_no_timeout_claim(self):
        self._busy()
        buf = io.StringIO()
        with mock.patch("sys.stdout", new=buf):
            self.assertEqual(self.cli.main(["start"]), 1)
        self.assertEqual(self.spawned, [])
        self.assertIn("busy", buf.getvalue())
        self.assertNotIn("No answer within", buf.getvalue())

    def test_stop_ignores_foreign_answer(self):
        self._pidfile()
        self.foreign = 404
        self.cli.main(["stop"])
        self.assertEqual(self.killed, [])

    def test_stop_uses_recorded_port(self):
        self._pidfile(port=9123)
        self.assertEqual(self._probed_ports(["stop"]), [9123])


class Locale(CliBase):
    def _usage(self, env):
        buf = io.StringIO()
        clear = {k: "" for k in ("LC_ALL", "LC_MESSAGES", "LANG")}
        clear.update(env)
        with mock.patch.dict(os.environ, clear), mock.patch("sys.stdout", new=buf):
            self.cli.main([])
        return buf.getvalue()

    def test_korean_locale(self):
        self.assertTrue(self._usage({"LANG": "ko_KR.UTF-8"}).startswith("사용법"))
        self.assertTrue(self._usage({"LC_ALL": "ko_KR.UTF-8", "LANG": "en_US.UTF-8"}).startswith("사용법"))

    def test_english_otherwise(self):
        self.assertTrue(self._usage({"LANG": "en_US.UTF-8"}).startswith("usage"))
        self.assertTrue(self._usage({}).startswith("usage"))
        self.assertTrue(self._usage({"LC_MESSAGES": "C", "LANG": "ko_KR.UTF-8"}).startswith("usage"))

    def test_every_message_has_both_languages(self):
        for key, pair in self.cli.MSG.items():
            self.assertEqual(len(pair), 2, key)
            self.assertEqual(pair[0].count("%"), pair[1].count("%"), key)


class ServiceBuilders(CliBase):
    def test_plist_text(self):
        txt = self.cli.build_plist("io.sidereus.viewer", 8799, "/d", code="/c")
        d = plistlib.loads(txt.encode("utf-8"))
        self.assertEqual(d["Label"], "io.sidereus.viewer")
        self.assertEqual(d["ProgramArguments"], ["/usr/bin/python3", os.path.join("/c", "chat_server.py"), "--no-open"])
        self.assertTrue(d["RunAtLoad"] and d["KeepAlive"])
        self.assertEqual(d["StandardErrorPath"], "/d/viewer.err")
        self.assertEqual(d["WorkingDirectory"], "/c")
        self.assertIn("--port", plistlib.loads(self.cli.build_plist("x", 9000, "/d").encode())["ProgramArguments"])

    def test_schtasks_argv(self):
        argv = self.cli.schtasks_argv(r"C:\Py\pythonw.exe", 8799, code=r"C:\sidereus")
        self.assertEqual(argv[:7], ["schtasks", "/Create", "/SC", "ONLOGON", "/TN", "Sidereus", "/TR"])
        self.assertTrue(argv[7].startswith('"C:\\Py\\pythonw.exe" "C:\\sidereus'))
        self.assertTrue(argv[7].endswith("chat_server.py\" --no-open"))
        self.assertEqual(self.ran, [])
        self.assertEqual(self.spawned, [])


if __name__ == "__main__":
    unittest.main()
