"""Empty diff message (web/js/30-diff.js diffBody): no upstream must not claim «pushed»."""
import json
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_fn
from tests._node import node_e


@unittest.skipUnless(shutil.which("node"), "node not installed")
class DiffEmptyNoUp(unittest.TestCase):
    def body(self, d):
        src = (i18n_prelude("'ko'", ("T", "TV", "U")) + "const esc = s => s, agoAt = s => s;\n"
               "function dfFiles(d){ return []; }\nfunction commitList(d){ return ''; }\n"
               + js_fn("diffBody") + "\nprocess.stdout.write(diffBody(" + json.dumps(d) + "));")
        return subprocess.run(node_e(src), check=True, capture_output=True, text=True).stdout

    def test_no_upstream(self):
        out = self.body({"ok": True, "hasUp": False})
        self.assertIn("커밋하지 않은 변경이 없습니다", out)
        self.assertNotIn("푸시까지 끝난", out)

    def test_with_upstream(self):
        self.assertIn("푸시까지 끝난", self.body({"ok": True, "hasUp": True}))


if __name__ == "__main__":
    unittest.main()
