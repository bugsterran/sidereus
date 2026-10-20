"""hooks/invite_notice.py wake notice vs config `mailbox_watch` — temp data dir. Monitor/watch.sh are never to be started."""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("invite_notice", os.path.join(ROOT, "hooks", "invite_notice.py"))
inv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inv)

_MOD_TMP = tempfile.mkdtemp()
_MOD_SAVED = {}


def setUpModule():
    # ⚠main() records SessionStart pids: keep every test off the live data dir and off `ps`.
    for k in ("SESSPID_DIR", "CLEAR_FILE", "_claude_pid"):
        _MOD_SAVED[k] = getattr(inv, k)
    inv.SESSPID_DIR = os.path.join(_MOD_TMP, "sesspid")
    inv.CLEAR_FILE = os.path.join(_MOD_TMP, "clears.jsonl")
    inv._claude_pid = lambda: 4242


def tearDownModule():
    for k, v in _MOD_SAVED.items():
        setattr(inv, k, v)
    shutil.rmtree(_MOD_TMP, ignore_errors=True)


PROJ = "/w/proj"
ME = "proj-bot"


class InviteNoticeWatch(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self._saved = {k: getattr(inv, k) for k in ("STORE", "ROOMS", "IDENTITY", "SKIP", "SEEN", "CONFIG",
                                                  "CLAUDE_JSON", "ACCT_DIR", "time")}
        inv.STORE = self.d
        inv.ROOMS = os.path.join(self.d, "rooms.json")
        inv.IDENTITY = os.path.join(self.d, "identity.json")
        inv.SKIP = os.path.join(self.d, "identity-skip.json")
        inv.SEEN = os.path.join(self.d, "invite-seen.json")
        inv.CONFIG = os.path.join(self.d, "config.local.json")
        inv.CLAUDE_JSON = os.path.join(self.d, "claude.json")
        inv.ACCT_DIR = os.path.join(self.d, "acct")
        self.write("claude.json", {"mcpServers": {"mailbox": {"command": "uv"}}})
        self.write("identity.json", {PROJ: ME})

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(inv, k, v)
        shutil.rmtree(self.d, ignore_errors=True)

    def write(self, name, data):
        with open(os.path.join(self.d, name), "w", encoding="utf-8") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))

    def run_hook(self, cwd=PROJ, event="SessionStart", source="startup"):
        payload = json.dumps({"hook_event_name": event, "cwd": cwd, "session_id": "s1", "source": source})
        out = io.StringIO()
        old = sys.stdin
        sys.stdin = io.StringIO(payload)
        try:
            with contextlib.redirect_stdout(out):
                inv.main()
        finally:
            sys.stdin = old
        return out.getvalue()

    def assertNoStartOrder(self, out):
        """Never tells the session to start a watcher (Monitor is off by policy)."""
        self.assertNotIn("감시가 꺼져 있습니다", out)
        self.assertNotIn("Monitor 툴로", out)
        self.assertNotIn("with the Monitor tool", out)
        self.assertNotIn("watch.sh <", out)           # old `<WATCH_SH> <id>` launch command
        self.assertNotIn("띄우십시오", out)

    def test_default_is_wake_line(self):
        out = self.run_hook()
        self.assertEqual(out.count("\n"), 1)           # one line
        self.assertIn("mailbox_wake", out)
        self.assertIn("mailbox_inbox", out)
        self.assertIn("do not start Monitor", out)
        self.assertNoStartOrder(out)

    def test_compact_resume_same_line(self):
        for src in ("compact", "resume"):
            out = self.run_hook(source=src)
            self.assertIn("mailbox_wake", out)
            self.assertNoStartOrder(out)

    def test_unregistered_has_wake_line_not_monitor(self):
        out = self.run_hook(cwd="/w/unregistered")
        self.assertIn("no registered mailbox identity", out)
        self.assertIn("mailbox_wake", out)
        self.assertNoStartOrder(out)

    def test_global_off_is_silent(self):
        self.write("config.local.json", {"mailbox_watch": {"mode": "off", "projects": {}}})
        self.assertEqual(self.run_hook(), "")

    def test_project_off_overrides_global_on(self):
        self.write("config.local.json", {"mailbox_watch": {"mode": "on", "projects": {PROJ: "off"}}})
        self.assertEqual(self.run_hook(), "")
        self.assertEqual(inv.watch_mode(PROJ + "/sub"), "off")
        self.assertEqual(inv.watch_mode("/w/project"), "on")      # prefix match is per path segment

    def test_longest_project_prefix_wins(self):
        self.write("config.local.json", {"mailbox_watch": {"mode": "off", "projects": {"/w": "off", PROJ: "on"}}})
        self.assertEqual(inv.watch_mode(PROJ), "on")
        self.assertEqual(inv.watch_mode("/w/other"), "off")

    def test_off_keeps_login_notice_without_watch_line(self):
        self.write("config.local.json", {"mailbox_watch": {"mode": "off"}})
        out = self.run_hook(cwd="/w/unregistered")
        self.assertIn("no registered mailbox identity", out)
        self.assertNotIn("watch.sh", out)
        self.assertNotIn("Monitor", out)

    def test_no_login_prompt_without_mailbox_mcp(self):
        self.write("claude.json", {"mcpServers": {"sidereus": {}}, "projects": {"/w/other": {"mcpServers": {"mailbox": {}}}}})
        self.assertEqual(self.run_hook(cwd="/w/unregistered"), "")
        self.write("claude.json", {"projects": {"/w/unregistered": {"mcpServers": {"mailbox": {}}}}})
        self.assertIn("no registered mailbox identity", self.run_hook(cwd="/w/unregistered"))     # project scope counts

    def test_login_prompt_english_even_in_ko_locale(self):
        with mock.patch.dict(os.environ, {"LANG": "ko_KR.UTF-8"}):   # model-facing text ignores the locale
            out = self.run_hook(cwd="/w/unregistered")
        self.assertIn("no registered mailbox identity", out)
        self.assertNotIn("미등록", out)

    def test_broken_config_means_on(self):
        self.write("config.local.json", "{not json")
        self.assertIn("mailbox_wake", self.run_hook())



SID = "0123abcd-ef45-6789"


class AcctRecord(unittest.TestCase):
    """SessionStart records sid -> config dir (metadata only) under ACCT_DIR."""
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self._saved = (inv.ACCT_DIR, inv.time, os.environ.get("CLAUDE_CONFIG_DIR"))
        inv.ACCT_DIR = os.path.join(self.d, "acct")
        os.environ["CLAUDE_CONFIG_DIR"] = "/x/cfg-a"

    def tearDown(self):
        inv.ACCT_DIR, inv.time, env = self._saved
        if env is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = env
        shutil.rmtree(self.d, ignore_errors=True)

    def read(self, sid=SID):
        with open(os.path.join(inv.ACCT_DIR, sid), encoding="utf-8") as f:
            return f.read()

    def test_session_start_writes(self):
        inv.record_acct("SessionStart", SID)
        self.assertEqual(self.read(), os.path.abspath("/x/cfg-a") + "\n")
        self.assertEqual(os.listdir(inv.ACCT_DIR), [SID])          # no tmp left

    def test_prompt_submit_does_not_write(self):
        inv.record_acct("UserPromptSubmit", SID)
        self.assertFalse(os.path.exists(inv.ACCT_DIR))

    def test_bad_sid_does_not_write(self):
        for sid in ("s1", "../../etc/x", "a/bcdefghij", "", None, "x" * 65):
            inv.record_acct("SessionStart", sid)
        self.assertFalse(os.path.exists(inv.ACCT_DIR) and os.listdir(inv.ACCT_DIR))

    def test_changed_env_rewrites(self):
        inv.record_acct("SessionStart", SID)
        os.environ["CLAUDE_CONFIG_DIR"] = "/x/cfg-b"
        inv.record_acct("SessionStart", SID)
        self.assertEqual(self.read(), os.path.abspath("/x/cfg-b") + "\n")

    def test_default_is_home_claude(self):
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        inv.record_acct("SessionStart", SID)
        self.assertEqual(self.read(), os.path.abspath(os.path.expanduser("~/.claude")) + "\n")

    def test_prune_old_records(self):
        os.makedirs(inv.ACCT_DIR)
        old = os.path.join(inv.ACCT_DIR, "old-session-1")
        with open(old, "w", encoding="utf-8") as f:
            f.write("/x\n")
        os.utime(old, (1000.0, 1000.0))
        now = 1000.0 + inv.ACCT_KEEP_S + 10

        class T:
            @staticmethod
            def time():
                return now
        inv.time = T
        inv.record_acct("SessionStart", SID)
        self.assertEqual(sorted(os.listdir(inv.ACCT_DIR)), [SID])

    def test_write_error_silent(self):
        with open(os.path.join(self.d, "acct"), "w", encoding="utf-8") as f:      # a file where the dir should be
            f.write("")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            inv.record_acct("SessionStart", SID)
        self.assertEqual(out.getvalue(), "")

    def test_main_records_without_output(self):
        payload = json.dumps({"hook_event_name": "SessionStart", "cwd": "/w/none", "session_id": SID})
        saved = {k: getattr(inv, k) for k in ("IDENTITY", "CLAUDE_JSON", "ROOMS", "SKIP", "CONFIG", "SEEN")}
        for k in saved:
            setattr(inv, k, os.path.join(self.d, k + ".json"))
        out, old = io.StringIO(), sys.stdin
        sys.stdin = io.StringIO(payload)
        try:
            with contextlib.redirect_stdout(out):
                inv.main()
        finally:
            sys.stdin = old
            for k, v in saved.items():
                setattr(inv, k, v)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(self.read(), os.path.abspath("/x/cfg-a") + "\n")



class ClearRecord(unittest.TestCase):
    """SessionStart writes sesspid/<pid> = sid; source "clear" appends {at, pid, old, new}."""
    OLD = "aaaaaaaa-1111-2222-3333-444444444444"
    NEW = "bbbbbbbb-1111-2222-3333-444444444444"

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self._saved = {k: getattr(inv, k) for k in ("SESSPID_DIR", "CLEAR_FILE", "_claude_pid", "CLEAR_MAX_BYTES",
                                                   "CLEAR_KEEP")}
        inv.SESSPID_DIR = os.path.join(self.d, "sesspid")
        inv.CLEAR_FILE = os.path.join(self.d, "clears.jsonl")
        inv._claude_pid = lambda: 777

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(inv, k, v)
        shutil.rmtree(self.d, ignore_errors=True)

    def pidfile(self):
        with open(os.path.join(inv.SESSPID_DIR, "777"), encoding="utf-8") as f:
            return f.read()

    def clears(self):
        if not os.path.exists(inv.CLEAR_FILE):
            return []
        with open(inv.CLEAR_FILE, encoding="utf-8") as f:
            return [json.loads(x) for x in f]

    def test_startup_writes_sesspid(self):
        inv.record_clear("SessionStart", "startup", self.OLD)
        self.assertEqual(self.pidfile(), self.OLD + "\n")
        self.assertEqual(self.clears(), [])

    def test_clear_appends_pair(self):
        inv.record_clear("SessionStart", "startup", self.OLD)
        inv.record_clear("SessionStart", "clear", self.NEW)
        c = self.clears()
        self.assertEqual(len(c), 1)
        self.assertEqual((c[0]["pid"], c[0]["old"], c[0]["new"]), ("777", self.OLD, self.NEW))
        self.assertEqual(sorted(c[0]), ["at", "new", "old", "pid"])
        self.assertEqual(self.pidfile(), self.NEW + "\n")

    def test_compact_appends_nothing(self):
        inv.record_clear("SessionStart", "startup", self.OLD)
        inv.record_clear("SessionStart", "compact", self.NEW)
        self.assertEqual(self.clears(), [])

    def test_bad_sid_ignored(self):
        inv.record_clear("SessionStart", "startup", self.OLD)
        inv.record_clear("SessionStart", "clear", "../../etc")
        inv.record_clear("SessionStart", "clear", None)
        self.assertEqual(self.clears(), [])
        self.assertEqual(self.pidfile(), self.OLD + "\n")

    def test_clear_without_prior_record_appends_nothing(self):
        inv.record_clear("SessionStart", "clear", self.NEW)
        self.assertEqual(self.clears(), [])
        self.assertEqual(self.pidfile(), self.NEW + "\n")

    def test_prompt_submit_does_nothing(self):
        inv.record_clear("UserPromptSubmit", "clear", self.NEW)
        self.assertFalse(os.path.exists(inv.SESSPID_DIR))

    def test_cap_prunes(self):
        inv.CLEAR_MAX_BYTES, inv.CLEAR_KEEP = 400, 3
        for i in range(10):
            inv.record_clear("SessionStart", "clear", "sid-%08d" % i)
        c = self.clears()
        self.assertLessEqual(len(c), 3 + 3)
        self.assertEqual(c[-1]["new"], "sid-00000009")

    def test_error_silent(self):
        with open(os.path.join(self.d, "sesspid"), "w", encoding="utf-8") as f:     # a file where the dir should be
            f.write("")
        inv.record_clear("SessionStart", "startup", self.OLD)

    def test_shell_parent_skipped(self):
        inv._claude_pid = _MOD_SAVED["_claude_pid"]
        r = type("R", (), {"stdout": " 555 /bin/zsh\n"})()
        # pin the POSIX branch so the ps path is tested on every OS
        with mock.patch.object(inv.sys, "platform", "darwin"), mock.patch.object(inv.subprocess, "run", return_value=r), \
                mock.patch.object(inv.os, "getppid", return_value=900):
            self.assertEqual(inv._claude_pid(), 555)
        r.stdout = " 555 claude\n"
        with mock.patch.object(inv.sys, "platform", "darwin"), mock.patch.object(inv.subprocess, "run", return_value=r), \
                mock.patch.object(inv.os, "getppid", return_value=900):
            self.assertEqual(inv._claude_pid(), 900)

    def test_win32_returns_parent_without_ps(self):
        inv._claude_pid = _MOD_SAVED["_claude_pid"]
        with mock.patch.object(inv.sys, "platform", "win32"), mock.patch.object(inv.os, "getppid", return_value=900), \
                mock.patch.object(inv.subprocess, "run", side_effect=AssertionError("ps spawned on win32")):
            self.assertEqual(inv._claude_pid(), 900)


if __name__ == "__main__":
    unittest.main()
