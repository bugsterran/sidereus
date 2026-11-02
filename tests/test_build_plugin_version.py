"""build_plugin --version-check: plugin/ changes since the last release tag need a VERSION different from the tag's."""
import importlib.util
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "scripts", "build_plugin.py")


def _load():
    spec = importlib.util.spec_from_file_location("build_plugin_tagvc", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TagVersionCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.mod = _load()
        self.mod.ROOT = self.root
        self._git("init", "-q")
        os.makedirs(os.path.join(self.root, "scripts"))
        os.makedirs(os.path.join(self.root, "plugin"))
        self._commit("scripts/build_plugin.py", 'VERSION = "0.1.0"\n', "start")
        self._commit("plugin/hook.py", "a\n", "hook")

    def tearDown(self):
        self.tmp.cleanup()

    def _git(self, *a):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@e", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        subprocess.run(("git", "-C", self.root) + a, check=True, env=env, capture_output=True)

    def _commit(self, rel, text, msg):
        with open(os.path.join(self.root, rel), "w", encoding="utf-8") as f:
            f.write(text)
        self._git("add", rel)
        self._git("commit", "-q", "-m", msg)

    def test_plugin_changed_same_version_fails(self):
        self._git("tag", "v0.1.0")
        self._commit("plugin/hook.py", "b\n", "hook change")
        problem, bad = self.mod.unbumped()
        self.assertIsNone(problem)
        self.assertEqual(len(bad), 1)
        self.assertEqual(self.mod.main(["--version-check"]), 1)

    def test_plugin_changed_bumped_passes(self):
        self._git("tag", "v0.1.0")
        self._commit("plugin/hook.py", "b\n", "hook change")
        self._commit("scripts/build_plugin.py", 'VERSION = "0.2.0"\n', "bump")
        self.assertEqual(self.mod.unbumped(), (None, []))

    def test_plugin_untouched_passes(self):
        self._git("tag", "v0.1.0")
        self._commit("scripts/build_plugin.py", 'VERSION = "0.1.0"\n# note\n', "other edit")
        self.assertEqual(self.mod.unbumped(), (None, []))

    def test_build_script_edit_without_version_change_is_not_a_bump(self):
        self._git("tag", "v0.1.0")
        self._commit("plugin/hook.py", "b\n", "hook change")
        self._commit("scripts/build_plugin.py", 'VERSION = "0.1.0"\n# note\n', "comment only")
        self.assertEqual(len(self.mod.unbumped()[1]), 1)

    def test_head_is_the_tag_compares_with_previous_tag(self):
        self._git("tag", "v0.1.0")
        self._commit("plugin/hook.py", "b\n", "hook change")
        self._git("tag", "v0.2.0")
        self.assertEqual(len(self.mod.unbumped()[1]), 1)

    def test_no_tag_fails(self):
        problem, bad = self.mod.unbumped()
        self.assertIn("no release tag", problem)
        self.assertEqual(self.mod.main(["--version-check"]), 1)


if __name__ == "__main__":
    unittest.main()
