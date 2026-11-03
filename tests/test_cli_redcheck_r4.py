"""R4: `sidereus redcheck ...` runs the bundled scripts/pl_eval.py in the foreground and returns its exit code."""
import os
import sys
import unittest

from tests.test_cli import CliBase

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RedcheckCli(CliBase):
    def test_runs_bundled_script_and_returns_rc(self):
        c = self.cli
        c._call = lambda argv, env=None: self.called.append(argv) or 3
        args = ["--pipeline", "/p/.claude/pipelines/x.json", "--stage", "Verify", "--repo", "/p", "--help"]
        self.assertEqual(c.main(["redcheck"] + args), 3)   # --help passes through, not the launcher usage
        self.assertEqual(self.called, [[sys.executable, os.path.join(c.ASSET_DIR, "scripts", "pl_eval.py"), "redcheck"] + args])

    def test_missing_script_is_2_and_runs_nothing(self):
        c = self.cli
        c.ASSET_DIR = os.path.join(self.tmp, "no-bundle")
        self.assertEqual(c.main(["redcheck", "--repo", "/p"]), 2)
        self.assertEqual(self.called, [])

    def test_script_is_in_the_wheel_bundle(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("sidereus_setup_t", os.path.join(ROOT, "setup.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        files = m.bundle_files()
        for rel in ("scripts/pl_eval.py", "scripts/evidence_rec.py"):   # pl_eval.py imports evidence_rec from its own folder
            self.assertIn(rel, files)


if __name__ == "__main__":
    unittest.main()
