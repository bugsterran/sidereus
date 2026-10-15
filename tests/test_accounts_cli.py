"""Orbit CLI (plugins/orbit/scripts/accounts.py): registry, resolve, copy, list, rc block, hook.

Hermetic: HOME and CLAUDE_CONFIG_DIR point into a temp dir per test; LAUNCHER is patched to a temp file.
"""
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "plugins", "orbit", "scripts", "accounts.py")


def _load():
    spec = importlib.util.spec_from_file_location("fa_accounts", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


acc = _load()


class AccountsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(os.path.join(self.home, ".claude"))
        env = {"HOME": self.home, "SHELL": "/bin/zsh"}
        p = mock.patch.dict(os.environ, env)
        p.start()
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.launcher = os.path.join(self.tmp, "launcher.sh")
        with open(self.launcher, "w") as f:
            f.write("claude() { :; }\n")
        lp = mock.patch.object(acc, "LAUNCHER", self.launcher)
        lp.start()
        self.addCleanup(lp.stop)

    def run_cli(self, *argv, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        rc = acc.main(list(argv), io.StringIO(stdin), out, err)
        return rc, out.getvalue(), err.getvalue()

    def reg_text(self):
        with open(os.path.join(self.home, ".claude-accounts")) as f:
            return f.read()

    def write_reg(self, text):
        with open(os.path.join(self.home, ".claude-accounts"), "w") as f:
            f.write(text)

    def mk(self, *parts):
        p = os.path.join(self.home, *parts)
        os.makedirs(p, exist_ok=True)
        return p

    def resolve(self, cwd, account=None, tty=False, answers=None):
        ask_in = io.StringIO(answers) if answers is not None else None
        return acc.resolve(cwd, account, tty, ask_in, io.StringIO() if ask_in else None)

    # ---- registry ------------------------------------------------------------------------------------------
    def test_registry_round_trip_keeps_comments_and_unknown_lines(self):
        self.mk(".claude-work")
        self.mk("src", "acme")
        self.write_reg("# my accounts\naccount default ~/.claude\naccount work ~/.claude-work\nfrobnicate x\n")
        self.assertEqual(self.run_cli("map", os.path.join(self.home, "src", "acme"), "work")[0], 0)
        self.assertEqual(self.run_cli("default", "work")[0], 0)
        self.assertEqual(self.reg_text(), "# my accounts\naccount default ~/.claude\naccount work ~/.claude-work\n"
                                          "frobnicate x\nmap ~/src/acme work\ndefault work\n")
        self.assertEqual(self.run_cli("unmap", os.path.join(self.home, "src", "acme"))[0], 0)
        self.assertNotIn("map ", self.reg_text())
        self.assertIn("# my accounts\n", self.reg_text())

    def test_non_utf8_registry_falls_back_and_is_not_rewritten(self):
        p = os.path.join(self.home, ".claude-accounts")
        with open(p, "wb") as f:
            f.write(b"account work ~/.claude-\xff\n")
        rc, out, _ = self.run_cli("resolve", "--cwd", self.home, "--tty", "0")
        self.assertEqual((rc, out), (0, "default\t-\n"))
        rc, out, _ = self.run_cli("list")
        self.assertEqual(rc, 0)
        self.assertIn("is ignored", out)
        self.assertEqual(self.run_cli("default", "default")[0], 1)
        with open(p, "rb") as f:
            self.assertEqual(f.read(), b"account work ~/.claude-\xff\n")

    def test_unsafe_registry_and_hand_edits_ignored(self):
        work = self.mk(".claude-work")
        self.mk(".claude-ev il")
        self.mk("tab\tdir")
        p = os.path.join(self.home, ".claude-accounts")
        self.write_reg("account $(x) ~/.claude-work\naccount bad ~/tab\tdir\naccount work ~/.claude-work\ndefault work\n")
        self.assertEqual(self.resolve(self.home), ("work", work))
        self.assertEqual([n for n, _ in acc.Registry.load().accounts()], ["default", "work"])
        os.chmod(p, 0o664)                                                  # group-writable: ignored, never rewritten
        self.assertEqual(self.resolve(self.home), ("default", "-"))
        self.assertEqual(self.run_cli("default", "default")[0], 1)
        self.assertIn("is ignored", self.run_cli("list")[1])
        os.chmod(p, 0o644)
        with mock.patch.object(acc.os, "getuid", return_value=os.getuid() + 1):   # someone else's file
            self.assertEqual(self.resolve(self.home), ("default", "-"))
        os.remove(p)
        self.assertEqual(self.run_cli("default", "default")[0], 0)
        self.assertEqual(os.stat(p).st_mode & 0o777, 0o600)                  # new registry is private

    def test_bad_names_refused(self):
        for n in ("accounts", "Work", "-x", "a" * 33, "a b"):
            self.assertEqual(self.run_cli("add", n)[0], 1, n)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".claude-accounts")))

    # ---- resolve -------------------------------------------------------------------------------------------
    def test_resolve_precedence_and_component_boundary(self):
        work, pers = self.mk(".claude-work"), self.mk(".claude-personal")
        acme, acme2 = self.mk("src", "acme"), self.mk("src", "acme2")
        inner = self.mk("src", "acme", "lib")
        self.write_reg("account work ~/.claude-work\naccount personal ~/.claude-personal\n"
                       "map ~/src/acme work\nmap ~/src/acme/lib personal\ndefault personal\n")
        self.assertEqual(self.resolve(acme), ("work", work))
        self.assertEqual(self.resolve(inner), ("personal", pers))            # nearest map wins
        self.assertEqual(self.resolve(acme2), ("personal", pers))            # acme2 is not under acme
        self.assertEqual(self.resolve(acme, "default"), ("default", "-"))    # --account beats map
        rc, _, err = self.run_cli("resolve", "--cwd", acme, "--account", "nope", "--tty", "0")
        self.assertEqual(rc, 2)
        self.assertIn("work", err)
        rc, out, _ = self.run_cli("resolve", "--cwd", acme, "--tty", "0")
        self.assertEqual(out, "work\t%s\n" % work)

    def test_resolve_single_account_and_missing_folder(self):
        self.assertEqual(self.resolve(self.home), ("default", "-"))
        self.write_reg("account gone ~/.claude-gone\nmap ~ gone\ndefault gone\n")   # not a directory: ignored
        self.assertEqual(self.resolve(self.home, tty=True), ("default", "-"))

    def test_prompt_on_tty_and_remember(self):
        work = self.mk(".claude-work")
        proj = self.mk("p")
        self.write_reg("account work ~/.claude-work\n")
        self.assertEqual(self.resolve(proj, tty=True, answers="2\nn\n"), ("work", work))
        self.assertNotIn("map", self.reg_text())
        self.assertEqual(self.resolve(proj, tty=True, answers="2\n"), ("work", work))      # EOF: not remembered
        self.assertNotIn("map", self.reg_text())
        self.assertEqual(self.resolve(proj, tty=True, answers="2\n\n"), ("work", work))   # Enter = yes
        self.assertIn("map ~/p work\n", self.reg_text())
        self.assertEqual(self.resolve(proj, tty=True, answers=""), ("work", work))   # remembered, no prompt
        q = self.mk("q")
        self.assertEqual(self.resolve(q, tty=True, answers="2\ny\n"), ("work", work))
        self.assertIn("map ~/q work\n", self.reg_text())

    def test_non_tty_never_prompts(self):
        self.mk(".claude-work")
        self.write_reg("account work ~/.claude-work\n")
        with mock.patch.object(acc, "prompt", side_effect=AssertionError("prompted")):
            self.assertEqual(self.resolve(self.home), ("default", "-"))
            self.write_reg("account work ~/.claude-work\ndefault work\n")
            self.assertEqual(self.resolve(self.home)[0], "work")

    # ---- add / copy ----------------------------------------------------------------------------------------
    def test_add_copy_skips_credentials_and_copies_mcp_servers_only(self):
        prim = os.path.join(self.home, ".claude")
        for rel, body in ((".credentials.json", "SECRET"), ("settings.json", '{"a": 1}'),
                          ("agents/x.md", "agent"), ("agents/.credentials.json", "SECRET"),
                          ("projects/p/s.jsonl", "conv"), ("history.jsonl", "hist")):
            p = os.path.join(prim, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                f.write(body)
        with open(os.path.join(self.home, ".claude.json"), "w") as f:
            json.dump({"oauthAccount": {"emailAddress": "x@example.com"}, "mcpServers": {"m": {"command": "c"}},
                       "projects": {}}, f)
        rc, out, _ = self.run_cli("add", "work", "--copy", "settings,agents,mcp")
        self.assertEqual(rc, 0)
        self.assertIn("dry run", out)
        self.assertIn("env values (may hold tokens); file mode 0600", out)
        self.assertIn("launcher not installed", out)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".zshrc")))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".claude-work")))
        rc, out, _ = self.run_cli("add", "work", "--copy", "settings,agents,mcp", "--yes")
        self.assertEqual(rc, 0)
        dst = os.path.join(self.home, ".claude-work")
        self.assertEqual(os.stat(dst).st_mode & 0o777, 0o700)
        got = sorted(os.path.relpath(os.path.join(d, f), dst) for d, _, fs in os.walk(dst) for f in fs)
        self.assertEqual(got, [".claude.json", "agents/x.md", "settings.json"])
        with open(os.path.join(dst, ".claude.json")) as f:
            self.assertEqual(json.load(f), {"mcpServers": {"m": {"command": "c"}}})
        self.assertIn("plugins must be installed per account", out)
        self.assertIn("sign in: claude -A work, then /login", out)
        self.assertEqual(self.reg_text(), "account default ~/.claude\naccount work ~/.claude-work\n")

    def test_add_existing_folder_keeps_contents_and_never_overwrites(self):
        d = self.mk(".claude-personal")
        with open(os.path.join(d, "settings.json"), "w") as f:
            f.write("mine")
        with open(os.path.join(self.home, ".claude", "settings.json"), "w") as f:
            f.write("primary")
        self.assertEqual(self.run_cli("add", "personal", "--copy", "settings", "--yes")[0], 0)
        with open(os.path.join(d, "settings.json")) as f:
            self.assertEqual(f.read(), "mine")

    def test_copy_recreates_top_level_symlinks(self):
        prim = os.path.join(self.home, ".claude")
        real_skills = self.mk("dotfiles", "skills")
        with open(os.path.join(real_skills, "s.md"), "w") as f:
            f.write("x")
        os.symlink(real_skills, os.path.join(prim, "skills"))
        os.symlink("/nonexistent/settings.json", os.path.join(prim, "settings.json"))
        rc, out, _ = self.run_cli("add", "work", "--copy", "skills,settings")
        self.assertIn("[link]", out)
        self.assertEqual(self.run_cli("add", "work", "--copy", "skills,settings", "--yes")[0], 0)
        dst = os.path.join(self.home, ".claude-work")
        self.assertEqual(os.readlink(os.path.join(dst, "skills")), real_skills)
        self.assertEqual(os.readlink(os.path.join(dst, "settings.json")), "/nonexistent/settings.json")
        self.assertEqual(os.listdir(real_skills), ["s.md"])                    # target untouched

    def test_control_chars_in_paths_refused_on_write(self):
        self.mk(".claude-work")
        self.write_reg("account work ~/.claude-work\n")
        evil = self.mk("p\ndefault work\naccount x ")
        before = self.reg_text()
        self.assertEqual(self.run_cli("map", evil, "work")[0], 1)
        self.assertEqual(self.run_cli("add", "x", "--dir", os.path.join(self.tmp, "a\nb"), "--yes")[0], 1)
        with mock.patch.object(acc.sys, "stderr", io.StringIO()) as err:
            self.assertEqual(self.resolve(evil, tty=True, answers="2\n\n")[0], "work")   # chosen, not remembered
        self.assertIn("not remembered", err.getvalue())
        self.assertEqual(self.reg_text(), before)

    def test_writes_refused_when_home_not_owned(self):
        self.mk(".claude-work")
        self.write_reg("account work ~/.claude-work\n")
        before = self.reg_text()
        with mock.patch.object(acc.os, "geteuid", return_value=os.geteuid() + 1):
            rc, _, err = self.run_cli("default", "work")
            self.assertEqual(rc, 1)
            self.assertIn("not owned by the current user", err)
            self.assertEqual(self.run_cli("add", "x", "--yes")[0], 1)
            self.assertEqual(self.run_cli("shell", "install", "--yes")[0], 1)
            self.assertEqual(self.run_cli("list")[0], 0)                       # reading still works
        self.assertEqual(self.reg_text(), before)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".zshrc")))

    def test_signed_in_byte_scan(self):
        d = self.mk(".claude-work")
        self.write_reg("account work ~/.claude-work\n")
        p = os.path.join(d, ".claude.json")
        self.assertIs(acc.signed_in(d), False)                                  # no file
        for body, want in (('{"x": "oauthAccount", "y": 1}', False), ('{"oauthAccount" : {}}', True)):
            with open(p, "w") as f:
                f.write(body)
            self.assertIs(acc.signed_in(d), want, body)
        with open(p, "w") as f:
            f.write('{"pad": "' + "a" * 100 + '", "oauthAccount": {"emailAddress": "s"}}')
        with mock.patch.object(acc, "SCAN_CHUNK", 7):                           # key split across chunks
            self.assertIs(acc.signed_in(d), True)
        with mock.patch.object(acc, "SCAN_CHUNK", 7), mock.patch.object(acc, "SCAN_CAP", 20):
            self.assertIsNone(acc.signed_in(d))                                 # too big: unknown
            with mock.patch.dict(os.environ, {"FA_RESOLVE_FIELDS": "3"}):
                out = self.run_cli("resolve", "--cwd", self.home, "--account", "work", "--tty", "0")[1]
            self.assertEqual(out, "work\t%s\t1\n" % d)                        # unknown: no hint

    def test_add_dir_registers_any_folder_and_refuses_wide_or_taken(self):
        d = os.path.join(self.tmp, "elsewhere", "acct-x")
        self.assertEqual(self.run_cli("add", "work", "--dir", d, "--yes")[0], 0)
        self.assertTrue(os.path.isdir(d))
        self.assertIn("account work %s\n" % d, self.reg_text())
        self.assertFalse(os.path.exists(os.path.join(self.home, ".claude-work")))
        before = self.reg_text()
        for bad in ("/", self.home, "~", self.tmp):
            self.assertEqual(self.run_cli("add", "x", "--dir", bad)[0], 1, bad)
        rc, _o, err = self.run_cli("add", "other", "--dir", d)
        self.assertEqual(rc, 1)
        self.assertIn("'work'", err)
        self.assertEqual(self.run_cli("add", "p2", "--dir", os.path.join(self.home, ".claude"))[0], 1)
        self.assertEqual(self.reg_text(), before)
        self.assertEqual(self.run_cli("add", "work", "--dir", d)[0], 0)   # same name + same dir: no-op (shell ready)
        self.assertEqual(self.reg_text(), before)

    def test_first_add_installs_launcher_in_one_step(self):
        rc = os.path.join(self.home, ".zshrc")
        with open(rc, "w") as f:
            f.write("mine\n")
        code, out, _ = self.run_cli("add", "work")
        self.assertEqual(code, 0)
        self.assertIn("dry run", out)
        self.assertIn("launcher not installed: append block in ~/.zshrc", out)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".claude-work")))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".claude-accounts")))
        with open(rc) as f:
            self.assertEqual(f.read(), "mine\n")
        code, out, _ = self.run_cli("add", "work", "--yes")
        self.assertEqual(code, 0)
        self.assertIn("registered work", out)
        self.assertIn("launcher installed in ~/.zshrc", out)
        self.assertTrue(os.path.isdir(os.path.join(self.home, ".claude-work")))
        self.assertTrue(os.path.isfile(acc.stable_py()))
        with open(rc) as f:
            once = f.read()
        self.assertEqual(once.count(acc.BEGIN + "\n"), 1)
        self.assertEqual(once, "mine\n\n" + acc.block_text())               # no labels or paths reach the rc
        with open(rc + ".bak-folder-accounts") as f:
            self.assertEqual(f.read(), "mine\n")
        code, out, _ = self.run_cli("add", "two")                       # launcher ready: dry run without the rc
        self.assertEqual(code, 0)
        self.assertIn("dry run", out)
        self.assertNotIn("shell", out)
        self.assertNotIn("two", self.reg_text())
        code, out, _ = self.run_cli("add", "two", "--yes")
        self.assertNotIn("launcher", out)
        self.assertIn("account two ~/.claude-two\n", self.reg_text())
        code, out, _ = self.run_cli("add", "two", "--shell")             # --shell only adds to the plan
        self.assertIn("dry run", out)
        self.assertIn("shell   reinstall: replace block", out)
        code, out, _ = self.run_cli("add", "two", "--shell", "--yes")    # refresh: same block, idempotent
        self.assertIn("launcher installed", out)
        with open(rc) as f:
            self.assertEqual(f.read(), once)
        custom = os.path.join(self.tmp, "brc")
        self.assertEqual(self.run_cli("add", "three", "--rc", custom, "--yes")[0], 0)
        with open(custom) as f:
            self.assertEqual(f.read().count(acc.BEGIN + "\n"), 1)
        self.assertEqual(self.run_cli("shell", "uninstall", "--yes")[0], 0)  # standalone command still works
        with open(rc) as f:
            self.assertEqual(f.read(), "mine\n")

    def test_resolve_signed_in_field_only_on_request(self):
        work = self.mk(".claude-work")
        self.write_reg("account work ~/.claude-work\ndefault work\n")
        self.assertEqual(self.run_cli("resolve", "--cwd", self.home, "--tty", "0")[1], "work\t%s\n" % work)
        with mock.patch.dict(os.environ, {"FA_RESOLVE_FIELDS": "3"}):
            self.assertEqual(self.run_cli("resolve", "--cwd", self.home, "--tty", "0")[1], "work\t%s\t0\n" % work)
            with open(os.path.join(work, ".claude.json"), "w") as f:
                json.dump({"oauthAccount": {"emailAddress": "secret@example.com"}}, f)
            out = self.run_cli("resolve", "--cwd", self.home, "--tty", "0")[1]
            self.assertEqual(out, "work\t%s\t1\n" % work)
            self.assertEqual(self.run_cli("resolve", "--cwd", self.home, "--account", "default", "--tty", "0")[1],
                             "default\t-\t0\n")
            with open(os.path.join(self.home, ".claude.json"), "w") as f:
                json.dump({"oauthAccount": {}}, f)                     # primary reads ~/.claude.json
            self.assertEqual(self.run_cli("resolve", "--cwd", self.home, "--account", "default", "--tty", "0")[1],
                             "default\t-\t1\n")

    def test_rename_changes_label_everywhere_folder_untouched(self):
        d = self.mk(".claude-work")
        self.mk("p")
        self.mk(".claude-two")
        self.write_reg("# keep\naccount work ~/.claude-work\naccount two ~/.claude-two\n"
                       "map ~/p work\ndefault work\n")
        self.assertEqual(self.run_cli("rename", "work", "job")[0], 0)
        self.assertEqual(self.reg_text(), "# keep\naccount job ~/.claude-work\naccount two ~/.claude-two\n"
                                          "map ~/p job\ndefault job\n")
        self.assertTrue(os.path.isdir(d))
        self.assertEqual(self.resolve(os.path.join(self.home, "p")), ("job", d))
        before = self.reg_text()
        self.assertEqual(self.run_cli("rename", "job", "two")[0], 1)      # taken
        self.assertEqual(self.run_cli("rename", "job", "Bad!")[0], 1)     # name rules
        self.assertEqual(self.run_cli("rename", "job", "accounts")[0], 1)
        self.assertEqual(self.run_cli("rename", "nope", "x")[0], 2)
        self.assertEqual(self.reg_text(), before)

    def test_rename_implicit_primary(self):
        self.mk(".claude-work")
        self.write_reg("account work ~/.claude-work\n")
        self.assertEqual(self.run_cli("rename", "default", "main")[0], 0)
        self.assertEqual(self.reg_text(), "account work ~/.claude-work\naccount main ~/.claude\n")

    def test_remove_keeps_folder_and_drops_maps(self):
        d = self.mk(".claude-work")
        self.mk("p")
        self.write_reg("account work ~/.claude-work\nmap ~/p work\ndefault work\n# keep\n")
        self.assertEqual(self.run_cli("remove", "work")[0], 0)
        self.assertEqual(self.reg_text(), "# keep\n")
        self.assertTrue(os.path.isdir(d))

    # ---- list ----------------------------------------------------------------------------------------------
    def test_list_prints_status_not_values(self):
        d = self.mk(".claude-work")
        self.mk(".claude-found", "projects")
        self.mk(".claude-empty")
        with open(os.path.join(d, ".claude.json"), "w") as f:
            json.dump({"oauthAccount": {"emailAddress": "secret@example.com"}}, f)
        self.write_reg("account work ~/.claude-work\ndefault work\n")
        self.mk("p")
        self.run_cli("map", os.path.join(self.home, "p"), "work")
        rc, out, _ = self.run_cli("list")
        self.assertEqual(rc, 0)
        self.assertIn("default  ~/.claude  [not signed in]", out)
        self.assertIn("* work  ~/.claude-work  [signed in]", out)
        self.assertIn("map ~/p", out)
        self.assertIn("found ~/.claude-found", out)
        self.assertNotIn("empty", out)
        self.assertNotIn("secret", out)

    # ---- rc block ------------------------------------------------------------------------------------------
    def test_rc_install_uninstall_byte_identical(self):
        rc = os.path.join(self.home, ".zshrc")
        for orig in ("", "a", "a\n", "a\n\n", "x\n# >>> folder-accounts >>> not a marker\n"):
            with open(rc, "w") as f:
                f.write(orig)
            for p in (rc + ".bak-folder-accounts",):
                if os.path.exists(p):
                    os.remove(p)
            self.assertEqual(self.run_cli("shell", "install", "--yes")[0], 0)
            with open(rc) as f:
                once = f.read()
            self.assertEqual(once.count(acc.BEGIN + "\n"), 1)
            self.assertIn('export FA_PY="$HOME/.local/share/folder-accounts/accounts.py"', once)
            self.assertIn("claude() { :; }\n", once)
            self.run_cli("shell", "install", "--yes")                       # idempotent
            with open(rc) as f:
                self.assertEqual(f.read(), once)
            with open(rc + ".bak-folder-accounts") as f:
                self.assertEqual(f.read(), orig)
            self.assertEqual(self.run_cli("shell", "uninstall", "--yes")[0], 0)
            with open(rc) as f:
                self.assertEqual(f.read(), orig, repr(orig))
        self.assertTrue(os.path.isfile(os.path.join(self.home, ".local/share/folder-accounts/accounts.py")))

    def test_rc_block_in_middle_and_dry_run(self):
        rc = os.path.join(self.tmp, "custom_rc")
        with open(rc, "w") as f:
            f.write("top\n")
        rcode, out, _ = self.run_cli("shell", "install", "--rc", rc)
        self.assertIn("dry run", out)
        with open(rc) as f:
            self.assertEqual(f.read(), "top\n")
        self.run_cli("shell", "install", "--rc", rc, "--yes")
        with open(rc, "a") as f:
            f.write("bottom\n")
        self.run_cli("shell", "uninstall", "--rc", rc, "--yes")
        with open(rc) as f:
            self.assertEqual(f.read(), "top\n\nbottom\n")

    # ---- hook ----------------------------------------------------------------------------------------------
    def test_hook_match_mismatch_bad_stdin(self):
        work = self.mk(".claude-work")
        proj = self.mk("p")
        self.write_reg("account work ~/.claude-work\nmap ~/p work\n")
        rc, out, _ = self.run_cli("hook-session-start", stdin=json.dumps({"cwd": proj}))
        self.assertEqual(rc, 0)
        obj = json.loads(out)
        self.assertEqual(obj["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("mapped to account work; this session runs as default", obj["systemMessage"])
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": work}):
            self.assertEqual(self.run_cli("hook-session-start", stdin=json.dumps({"cwd": proj}))[:2], (0, ""))
        self.assertEqual(self.run_cli("hook-session-start", stdin=json.dumps({"cwd": self.home}))[:2], (0, ""))
        for bad in ("", "not json", "[1]", '{"cwd": 5}'):
            self.assertEqual(self.run_cli("hook-session-start", stdin=bad)[:2], (0, ""), bad)


if __name__ == "__main__":
    unittest.main()
