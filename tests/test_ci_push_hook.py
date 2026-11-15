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


if __name__ == "__main__":
    unittest.main()
