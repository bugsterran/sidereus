"""Orbit shell launcher (plugins/orbit/shell/launcher.sh) under bash and zsh.

Hermetic: tmp HOME, a fake `claude` on PATH that prints env + argv, and a stub accounts.py via $FA_PY.
The real `claude` is never run.
"""
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(ROOT, "plugins", "orbit", "shell", "launcher.sh")
REAL_PY = os.path.join(ROOT, "plugins", "orbit", "scripts", "accounts.py")

FAKE_CLAUDE = """#!/bin/sh
echo "CCD=${CLAUDE_CONFIG_DIR-<unset>}"
for a in "$@"; do echo "ARG=$a"; done
"""

# Stub resolver: logs its argv, unknown account -> exit 2, `work` -> a dir, anything else -> primary.
STUB_PY = """import sys
open(sys.argv[0] + ".log", "a").write(" ".join(sys.argv[1:]) + "\\n")
a = sys.argv[1:]
acc = a[a.index("--account") + 1] if "--account" in a else ""
if acc == "bad":
    sys.stderr.write("unknown account\\n"); sys.exit(2)
if acc == "work":
    print("work\\t/acc/work")
else:
    print("default\\t-")
"""

SHELLS = ["bash"] + (["zsh"] if shutil.which("zsh") else [])


# ⚠Windows "bash" on PATH can resolve to WSL; the launcher is POSIX-shell only.
@unittest.skipUnless(os.name == "posix", "POSIX shell launcher")
class LauncherTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.home = os.path.join(self.tmp, "home")
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.home)
        os.makedirs(self.bin)
        fake = os.path.join(self.bin, "claude")
        with open(fake, "w", encoding="utf-8") as f:
            f.write(FAKE_CLAUDE)
        os.chmod(fake, 0o755)
        self.stub = os.path.join(self.tmp, "accounts.py")
        with open(self.stub, "w", encoding="utf-8") as f:
            f.write(STUB_PY)
        with open(os.path.join(self.home, ".claude-accounts"), "w", encoding="utf-8") as f:
            f.write("account default ~/.claude\naccount work ~/.claude-work\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_sh(self, sh, cmd, fa_py=None, extra=None):
        env = {"HOME": self.home, "PATH": self.bin + ":/usr/bin:/bin", "FA_PY": fa_py or self.stub}
        env.update(extra or {})
        argv = [sh, "-f", "-c"] if sh == "zsh" else [sh, "--norc", "--noprofile", "-c"]
        p = subprocess.run(argv + ['. "$0"; ' + cmd, LAUNCHER], env=env, cwd=self.home,
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True, timeout=20, encoding="utf-8")
        return p.returncode, p.stdout.splitlines(), p.stderr

    def stub_log(self):
        try:
            with open(self.stub + ".log", encoding="utf-8") as f:
                return f.read().splitlines()
        except OSError:
            return []

    def test_account_flag_stripped_and_print_is_non_tty(self):
        for sh in SHELLS:
            with self.subTest(sh=sh):
                rc, out, err = self.run_sh(sh, "claude -A work -p 'hello world' --x")
                self.assertEqual(rc, 0, err)
                self.assertEqual(out, ["CCD=/acc/work", "ARG=-p", "ARG=hello world", "ARG=--x"])
                self.assertIn("work", err)
                self.assertTrue(self.stub_log()[-1].endswith("--account work --tty 0"), self.stub_log())

    def test_account_equals_form(self):
        for sh in SHELLS:
            with self.subTest(sh=sh):
                rc, out, _ = self.run_sh(sh, "claude --account=work")
                self.assertEqual((rc, out), (0, ["CCD=/acc/work"]))

    def test_default_account_unsets_config_dir(self):
        for sh in SHELLS:
            with self.subTest(sh=sh):
                rc, out, _ = self.run_sh(sh, "claude -A default x", extra={"CLAUDE_CONFIG_DIR": "/stale"})
                self.assertEqual((rc, out), (0, ["CCD=<unset>", "ARG=x"]))

    def test_no_tty_stdin_gives_tty_0(self):
        for sh in SHELLS:
            with self.subTest(sh=sh):
                self.run_sh(sh, "claude")
                self.assertTrue(self.stub_log()[-1].endswith("--tty 0"))

    def test_explicit_env_wins_without_flag(self):
        for sh in SHELLS:
            with self.subTest(sh=sh):
                rc, out, _ = self.run_sh(sh, "claude a b", extra={"CLAUDE_CONFIG_DIR": "/mine"})
                self.assertEqual((rc, out), (0, ["CCD=/mine", "ARG=a", "ARG=b"]))
        self.assertEqual(self.stub_log(), [])

    def test_missing_fa_py_falls_through(self):
        for sh in SHELLS:
            with self.subTest(sh=sh):
                rc, out, _ = self.run_sh(sh, "claude q", fa_py=os.path.join(self.tmp, "nope.py"))
                self.assertEqual((rc, out), (0, ["CCD=<unset>", "ARG=q"]))

    def test_missing_registry_falls_through(self):
        os.remove(os.path.join(self.home, ".claude-accounts"))
        for sh in SHELLS:
            with self.subTest(sh=sh):
                rc, out, _ = self.run_sh(sh, "claude q")
                self.assertEqual((rc, out), (0, ["CCD=<unset>", "ARG=q"]))
        self.assertEqual(self.stub_log(), [])

    def test_unknown_account_stops(self):
        for sh in SHELLS:
            with self.subTest(sh=sh):
                rc, out, _ = self.run_sh(sh, "claude -A bad")
                self.assertEqual((rc, out), (2, []))

    def test_resolver_failure_still_starts_claude(self):
        bodies = {"exit1": "import sys; sys.exit(1)\n", "garbage": "print('no tab here')\n"}
        for label, body in bodies.items():
            with open(self.stub, "w", encoding="utf-8") as f:
                f.write(body)
            for sh in SHELLS:
                with self.subTest(sh=sh, stub=label):
                    rc, out, _ = self.run_sh(sh, "claude -p x")
                    self.assertEqual((rc, out), (0, ["CCD=<unset>", "ARG=-p", "ARG=x"]))

    def test_dangling_flag_does_not_loop(self):
        for sh in SHELLS:
            with self.subTest(sh=sh):
                rc, out, _ = self.run_sh(sh, "claude -A")
                self.assertEqual((rc, out), (2, []))

    def test_double_dash_passes_rest(self):
        for sh in SHELLS:
            with self.subTest(sh=sh):
                rc, out, _ = self.run_sh(sh, "claude -A work -- -A x")
                self.assertEqual(out, ["CCD=/acc/work", "ARG=--", "ARG=-A", "ARG=x"])

    def test_signed_in_field(self):
        # 3 fields when asked via env; 2 fields (older accounts.py) still parse; dir never takes the flag.
        for body, hint in (("print('work\\t/acc/work\\t0')", True), ("print('work\\t/acc/work\\t1')", False),
                           ("print('work\\t/acc/work')", False),
                           ("import os; print('work\\t/acc/work\\t' + os.environ.get('FA_RESOLVE_FIELDS', '-'))", False)):
            with open(self.stub, "w", encoding="utf-8") as f:
                f.write(body + "\n")
            for sh in SHELLS:
                with self.subTest(sh=sh, stub=body):
                    rc, out, err = self.run_sh(sh, "claude x")
                    self.assertEqual((rc, out), (0, ["CCD=/acc/work", "ARG=x"]), err)
                    self.assertEqual("not signed in yet: type /login" in err, hint, err)
                    self.assertIn("→ work", err)

    @unittest.skipUnless(os.path.isfile(REAL_PY), "accounts.py not built yet")
    def test_real_resolver(self):
        os.makedirs(os.path.join(self.home, ".claude"))
        os.makedirs(os.path.join(self.home, ".claude-work"))
        for sh in SHELLS:
            with self.subTest(sh=sh):
                rc, out, err = self.run_sh(sh, "claude -A work -p x", fa_py=REAL_PY)
                self.assertEqual(rc, 0, err)
                self.assertTrue(out[0].startswith("CCD=") and out[0].endswith(".claude-work"), out)
                self.assertEqual(out[1:], ["ARG=-p", "ARG=x"])
                self.assertIn("→ work (not signed in yet: type /login)", err)
                rc, out, err = self.run_sh(sh, "claude -A default", fa_py=REAL_PY,
                                           extra={"CLAUDE_CONFIG_DIR": "/stale"})
                self.assertEqual((rc, out), (0, ["CCD=<unset>"]), err)


if __name__ == "__main__":
    unittest.main()
