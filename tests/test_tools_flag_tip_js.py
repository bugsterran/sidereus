"""Tools list «overridden» tooltip (web/js/47-tools.js tvwFlagTip) names project folders by basename on both path styles.

⚠Splitting on '/' only left a Windows `~\\src\\repo` path whole in the tooltip (and in the project column)."""
import json
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

_STUBS = ("const T = s => s;"
          " function esc(s){ return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/\"/g, '&quot;'); }\n")


def tip(row, flag):
    js = _STUBS + js_fn("tvwFlagTip") + "\nconsole.log(JSON.stringify(tvwFlagTip(%s, %s)));" % (json.dumps(row), json.dumps(flag))
    return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


class FlagTip(unittest.TestCase):
    def test_basenames_posix_and_windows(self):
        t = tip({"shadowBy": ["~/src/web", "~\\src\\api"]}, "shadow")
        self.assertIn(": web, api", t)
        self.assertNotIn("src", t)

    def test_only_shadow_flag_with_projects(self):
        self.assertEqual(tip({"shadowBy": ["~/a"]}, "dup"), "")
        self.assertEqual(tip({}, "shadow"), "")

    def test_tooltip_escaped(self):
        self.assertIn("&quot;", tip({"shadowBy": ['~/a"b']}, "shadow"))


if __name__ == "__main__":
    unittest.main()
