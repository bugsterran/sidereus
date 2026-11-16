"""17-attention.js attnWhy (en): loop/toolfail drop an unknown tool (v.tool null) instead of leaking the Korean generic word; a named tool still shows."""
import json
import re
import subprocess
import unittest

from tests._i18n_js import i18n_switch
from tests._load import js_fn
from tests._node import node_e

STUB = "let LANG = 'en'; function PL(n, w){ return n + ' ' + w; }\n"
HANGUL = re.compile("[가-힣]")


def why(k, v):
    js = (STUB + i18n_switch(("T", "TV", "U")) + js_fn("attnWhy")
          + "\nconsole.log(JSON.stringify(attnWhy(" + json.dumps({"k": k, "v": v}) + ")));")
    return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


class ToolFallback(unittest.TestCase):
    def test_unknown_tool_has_no_hangul(self):
        # sidereus/attention.py sends tool null when the tool is unknown.
        self.assertEqual(why("toolfail", {"n": 4, "tool": None}), "Same error repeated 4×")
        self.assertEqual(why("loop", {"n": 6, "tool": None}), "Same action repeated 6×")
        for k, n in (("toolfail", 4), ("loop", 6)):
            self.assertIsNone(HANGUL.search(why(k, {"n": n, "tool": None})))

    def test_named_tool_still_shows(self):
        self.assertEqual(why("toolfail", {"n": 4, "tool": "Bash"}), "Same error repeated 4× · Bash")
        self.assertEqual(why("loop", {"n": 6, "tool": "Bash"}), "Same action repeated 6× · Bash")


if __name__ == "__main__":
    unittest.main()
