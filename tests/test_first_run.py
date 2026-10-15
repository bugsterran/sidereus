"""First-run defaults: UI language follows the browser when nothing is saved (web/js/05-i18n.js langPick),
Gemini root honours GEMINI_CLI_HOME like the Gemini CLI (sidereus/plat_gemini.py root). No live files, no clock."""
import json
import os
import shutil
import subprocess
import unittest
from unittest import mock

from tests._load import sidereus
from tests.test_saver_quota_js import jconst
from tests._node import node_e


@unittest.skipUnless(shutil.which("node"), "node not installed")
class LangPick(unittest.TestCase):
    def test_saved_wins_else_browser(self):
        cases = [(None, "en-US"), (None, "en"), (None, "EN-gb"), (None, "ko-KR"), (None, "ja"), (None, ""),
                 (None, None), ("ko", "en-US"), ("en", "ko-KR"), ("junk", "en-US"), ("junk", "fr")]
        src = jconst("langPick") + "\nprocess.stdout.write(JSON.stringify(%s.map(c => langPick(c[0], c[1]))));" % json.dumps(cases)
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), ["en", "en", "en", "ko", "ko", "ko", "ko", "ko", "en", "en", "ko"])


class GeminiRoot(unittest.TestCase):
    def setUp(self):
        self.g = sidereus("plat_gemini")

    def test_env_override(self):
        with mock.patch.dict(os.environ, {"GEMINI_CLI_HOME": "/x/home"}):
            self.assertEqual(self.g.root(), os.path.join("/x/home", ".gemini"))

    def test_default_is_account_home(self):
        env = {k: v for k, v in os.environ.items() if k != "GEMINI_CLI_HOME"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.dict(self.g.root.__globals__, {"_real_home": lambda: "/acct"}):
            self.assertEqual(self.g.root(), os.path.join("/acct", ".gemini"))


if __name__ == "__main__":
    unittest.main()
