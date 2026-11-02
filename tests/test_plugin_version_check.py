"""build_plugin.unbumped(): plugin/ commits after the last VERSION bump (release audit, --version-check)."""
import importlib.util
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "scripts", "build_plugin.py")


def _load():
    spec = importlib.util.spec_from_file_location("build_plugin_vc", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class VersionCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.mod = _load()
        self.mod.ROOT = self.root
        self._git("init", "-q")
        os.makedirs(os.path.join(self.root, "scripts"))
        os.makedirs(os.path.join(self.root, "plugin"))

    def tearDown(self):
        self.tmp.cleanup()

    def _git(self, *a):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@e", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        subprocess.run(("git", "-C", self.root) + a, check=True, env=env, capture_output=True)

    def _commit(self, rel, text, msg):
        with open(os.path.join(self.root, rel), "w") as f:
            f.write(text)
        self._git("add", rel)
        self._git("commit", "-q", "-m", msg)

    def test_plugin_change_after_bump_is_reported(self):
        self._commit("scripts/build_plugin.py", 'VERSION = "0.1.0"\n', "bump")
        self._commit("plugin/hook.py", "a\n", "hook change")
        self.assertEqual(len(self.mod.unbumped()), 1)

    def test_bump_after_plugin_change_clears_it(self):
        self._commit("scripts/build_plugin.py", 'VERSION = "0.1.0"\n', "bump")
        self._commit("plugin/hook.py", "a\n", "hook change")
        self._commit("scripts/build_plugin.py", 'VERSION = "0.2.0"\n', "bump again")
        self.assertEqual(self.mod.unbumped(), [])

    def test_other_edits_to_build_script_do_not_count_as_bump(self):
        self._commit("scripts/build_plugin.py", 'VERSION = "0.1.0"\n', "bump")
        self._commit("plugin/hook.py", "a\n", "hook change")
        self._commit("scripts/build_plugin.py", 'VERSION = "0.1.0"\n# note\n', "comment only")
        self.assertEqual(len(self.mod.unbumped()), 1)


if __name__ == "__main__":
    unittest.main()
