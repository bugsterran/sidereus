"""17-attention.js attnWhy (en): loop/toolfail drop the server's Korean unknown-tool fallback word; a named tool still shows."""
import json
import re
import subprocess
import unittest

from tests._i18n_js import i18n_switch
from tests._load import js_fn
from tests._node import node_e

STUB = "let LANG = 'en'; function PL(n, w){ return n + ' ' + w; }\n"
HANGUL = re.compile("[가-힣]")


def why(k, w):
    js = (STUB + i18n_switch(("T", "TV", "U")) + js_fn("attnWhy")
          + "\nconsole.log(JSON.stringify(attnWhy(" + json.dumps({"k": k, "why": w}) + ")));")
    return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


class ToolFallback(unittest.TestCase):
    def test_unknown_tool_has_no_hangul(self):
        # Same why templates as sidereus/attention.py toolfail and loop, with its unknown-tool fallback word.
        self.assertEqual(why("toolfail", "같은 오류 4회 반복 · 도구"), "Same error repeated 4×")
        self.assertEqual(why("loop", "도구 같은 호출 6회 반복"), "Same action repeated 6×")
        for k, w in (("toolfail", "같은 오류 4회 반복 · 도구"), ("loop", "도구 같은 호출 6회 반복")):
            self.assertIsNone(HANGUL.search(why(k, w)))

    def test_named_tool_still_shows(self):
        self.assertEqual(why("toolfail", "같은 오류 4회 반복 · Bash"), "Same error repeated 4× · Bash")
        self.assertEqual(why("loop", "Bash 같은 호출 6회 반복"), "Same action repeated 6× · Bash")


if __name__ == "__main__":
    unittest.main()
