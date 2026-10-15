"""Saver level table: `_saver_levels_clean` passthrough/validation (sidereus/saver.py) and the
«What each level does» fold (web/js/90-settings.js svLevelsFold). Temp files only; node for the render."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tests._load import js_all, js_fn, load, sidereus
from tests._node import node_e

load()
sv = sidereus("saver")
LV = [{"lv": 0, "cap": None, "rules": ["No cap"]}, {"lv": 1, "cap": 2, "rules": ["At most 2", "Batch"]},
      {"lv": 3, "cap": 0, "rules": ["No new subagents"]}]
HOW = ["Auto brakes only when ...", "Pace badge ..."]


class Clean(unittest.TestCase):
    def test_valid_passes_through(self):
        d = sv._saver_levels_clean({"stage": 1, "levels": json.loads(json.dumps(LV)), "how": list(HOW)})
        self.assertEqual(d["levels"], LV)
        self.assertEqual(d["how"], HOW)
        self.assertEqual(d["stage"], 1)

    def test_extra_keys_dropped_from_entries(self):
        d = sv._saver_levels_clean({"levels": [{"lv": 1, "cap": 2, "rules": ["a"], "x": "<b>"}]})
        self.assertEqual(d["levels"], [{"lv": 1, "cap": 2, "rules": ["a"]}])

    def test_bad_shapes_drop_the_key(self):
        bad = ([], "x", [1], [{"lv": "1", "cap": 2, "rules": ["a"]}], [{"lv": True, "cap": 2, "rules": ["a"]}],
               [{"lv": 1, "cap": -1, "rules": ["a"]}], [{"lv": 1, "cap": 2, "rules": []}],
               [{"lv": 1, "cap": 2, "rules": ["x" * 121]}], [{"lv": 1, "cap": 2, "rules": [3]}],
               [{"lv": i, "cap": 0, "rules": ["a"]} for i in range(9)])
        for b in bad:
            d = sv._saver_levels_clean({"stage": 2, "levels": b, "how": [""]})
            self.assertNotIn("levels", d, b)
            self.assertNotIn("how", d)
            self.assertEqual(d["stage"], 2)

    def test_reader_applies_it(self):
        tmp = tempfile.mkdtemp(prefix="sidereus-svlv-")
        self.addCleanup(shutil.rmtree, tmp, True)
        p = os.path.join(tmp, ".saver-view.json")
        with open(p, "w") as f:
            json.dump({"stage": 1, "levels": "bogus", "how": HOW}, f)
        with mock.patch.object(sv, "SAVER_VIEW", p):
            self.assertEqual(sv._saver_view(), {"stage": 1, "how": HOW})


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Fold(unittest.TestCase):
    def run_js(self, sv_obj):
        esc = js_all().split("const esc = ", 1)[1].split(";\n", 1)[0]
        src = ("const T = s => s; const lsGet = () => ''; const esc = " + esc + ";\nlet SV = " + json.dumps(sv_obj) + ";\n"
               + js_fn("svLevelsFold") + "\nprocess.stdout.write(JSON.stringify(svLevelsFold()));")
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        return json.loads(r.stdout)

    def test_hidden_without_levels(self):
        self.assertEqual(self.run_js(None), "")
        self.assertEqual(self.run_js({"stage": 1}), "")

    def test_rows_current_and_escaped(self):
        lv = LV + [{"lv": 4, "cap": 0, "rules": ["<img src=x>"]}]
        h = self.run_js({"stage": 1, "mode": "auto", "levels": lv, "how": ["a<b"]})
        self.assertIn("What each level does", h)
        self.assertEqual(h.count("<tr class=on"), 1)
        self.assertIn("<tr class=on aria-current=true><td>1</td><td>2</td>", h)
        self.assertIn("<td>No cap</td>", h)
        self.assertNotIn("<img", h)
        self.assertIn("a&lt;b", h)

    def test_off_highlights_nothing(self):
        h = self.run_js({"stage": 0, "mode": "off", "levels": LV})
        self.assertNotIn("class=on", h)


if __name__ == "__main__":
    unittest.main()
