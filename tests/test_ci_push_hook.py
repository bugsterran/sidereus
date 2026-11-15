"""scripts/ci_push_hook.py: which pushes ask for a CI wait (pure parsing, no git, no network)."""
import importlib.util
import os
import unittest

_P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "ci_push_hook.py")
_spec = importlib.util.spec_from_file_location("ci_push_hook", _P)
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)


class PushedBranch(unittest.TestCase):
    def b(self, cmd):
        return H.pushed_branch(cmd, "dev")

    def test_branch_pushes(self):
        self.assertEqual(self.b("git push"), "dev")
        self.assertEqual(self.b("git push origin"), "dev")
        self.assertEqual(self.b("git push origin dev"), "dev")
        self.assertEqual(self.b("git push -u origin main"), "main")
        self.assertEqual(self.b("git push origin HEAD:dev"), "dev")
        self.assertEqual(self.b("git push origin +refs/heads/x:refs/heads/main"), "main")
        self.assertEqual(self.b("cd /r && git push origin dev && echo ok"), "dev")
        self.assertEqual(self.b("git -C /r push origin dev"), "dev")

    def test_not_a_branch_push(self):
        for cmd in ("git status", "git push --tags", "git push origin v0.18.0",
                    "git push origin refs/tags/v1.0.0", "git push --dry-run origin dev",
                    "git push origin --delete old", "echo git pushed", "gitpush origin dev",
                    'git commit -m "after a branch git push it asks"',
                    "git commit -m 'x\n\nruns git push origin dev'"):
            self.assertIsNone(self.b(cmd), cmd)

    def test_valued_options_and_delete_refspec(self):
        self.assertEqual(self.b("git push -o ci.skip origin dev"), "dev")
        self.assertEqual(self.b("git push --push-option ci.skip origin main"), "main")
        self.assertEqual(self.b("git push --repo origin origin dev"), "dev")
        self.assertIsNone(self.b("git push origin :old"))

    def test_pushed_dir(self):
        d = H.pushed_dir
        self.assertIsNone(d("git push origin dev"))
        self.assertEqual(d("git -C /r push origin dev"), "/r")
        self.assertEqual(d("cd /a && cd /b && git push origin dev"), "/b")
        self.assertEqual(d("cd '/a b' && git push"), "/a b")
        self.assertEqual(d("git push origin dev && cd /later"), None)
        self.assertEqual(d("cd ~/x && git push"), os.path.expanduser("~/x"))


class Main(unittest.TestCase):
    """main() with git stubbed: {(cwd, argv...): stdout}."""
    SHA = "a" * 40

    def run_main(self, cmd, git):
        import io
        import json
        from unittest import mock
        ev = {"tool_input": {"command": cmd}, "tool_response": {}, "cwd": "/repo"}
        out = io.StringIO()
        with mock.patch.object(H, "_git", lambda cwd, *a: git.get((os.path.normpath(cwd),) + a, "")), \
                mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out):
            H.main()
        s = out.getvalue()
        return json.loads(s)["hookSpecificOutput"]["additionalContext"] if s else None

    def test_branch_is_shell_quoted(self):
        b = "a$(id)`x`"
        msg = self.run_main("git push origin '%s'" % b, {("/repo", "rev-parse", "--abbrev-ref", "HEAD"): "dev",
                                                          ("/repo", "rev-parse", "--verify", "--quiet", b + "^{commit}"): self.SHA})
        self.assertIn("ci_wait.sh %s 'a$(id)`x`'`" % self.SHA, msg)

    def test_other_repo_gets_no_hint(self):
        git = {("/repo", "rev-parse", "--show-toplevel"): "/repo", ("/other", "rev-parse", "--show-toplevel"): "/other",
               ("/other", "rev-parse", "--abbrev-ref", "HEAD"): "dev",
               ("/other", "rev-parse", "--verify", "--quiet", "dev^{commit}"): self.SHA}
        self.assertIsNone(self.run_main("cd /other && git push origin dev", git))
        self.assertIsNone(self.run_main("git -C /other push origin dev", git))

    def test_cd_into_this_repo_still_hints(self):
        git = {("/repo", "rev-parse", "--show-toplevel"): "/repo", ("/repo", "rev-parse", "--abbrev-ref", "HEAD"): "dev",
               ("/repo", "rev-parse", "--verify", "--quiet", "dev^{commit}"): self.SHA}
        self.assertIn("ci_wait.sh %s dev`" % self.SHA, self.run_main("cd /repo && git push origin dev", git))


if __name__ == "__main__":
    unittest.main()
