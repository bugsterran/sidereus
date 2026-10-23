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
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"stage": 1, "levels": "bogus", "how": HOW}, f)
        with mock.patch.object(sv, "SAVER_VIEW", p):
            self.assertEqual(sv._saver_view(), {"stage": 1, "how": HOW})


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Fold(unittest.TestCase):
    def run_js(self, sv_obj, ko=None):
        esc = js_all().split("const esc = ", 1)[1].split(";\n", 1)[0]
        src = ("const KO = " + json.dumps(ko or {}) + "; const T = s => KO[s] || s; const lsGet = () => ''; const esc = " + esc
               + ";\nlet SV = " + json.dumps(sv_obj) + ";\n" + js_fn("svTr") + "\n"
               + js_fn("svLevelsFold") + "\nprocess.stdout.write(JSON.stringify(svLevelsFold()));")
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
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

    def test_hook_strings_translated_numbers_kept(self):
        ko = {"At most {1} subagents at once": "KO-cap {1}", "Keep output short": "KO-short", "room": "KO-room",
              "Auto brakes only when the 5h quota is projected to run out more than {1} min before the reset "
              "(or the target time).": "KO-brake {1}",
              "While braking, the level follows room = remaining % / evenly-spent %: {1}.": "KO-follow {1}.",
              "Burning {1}x faster than needed at {2}%+ escalates to level 3.": "KO-hot {1} {2}"}
        lv = [{"lv": 1, "cap": 2, "rules": ["At most 2 subagents at once", "Keep output short", "Unknown <rule>"]},
              {"lv": 2, "cap": 1, "rules": ["At most 1 subagent at once"]}]
        how = ["Auto brakes only when the 5h quota is projected to run out more than 10 min before the reset (or the target time).",
               "While braking, the level follows room = remaining % / evenly-spent %: room < 0.3 -> 3 · room < 0.5 -> 2 · room < 1 -> 1.",
               "Burning 2x faster than needed at 70%+ escalates to level 3.", "Brand new note"]
        h = self.run_js({"stage": 1, "mode": "auto", "levels": lv, "how": how}, ko)
        self.assertIn("<td>KO-cap 2<br>KO-short<br>Unknown &lt;rule&gt;</td>", h)
        self.assertIn("<td>KO-cap 1</td>", h)
        self.assertIn("<li>KO-brake 10</li>", h)
        self.assertIn("<li>KO-follow KO-room &lt; 0.3 -&gt; 3 · KO-room &lt; 0.5 -&gt; 2 · KO-room &lt; 1 -&gt; 1.</li>", h)
        self.assertIn("<li>KO-hot 2 70</li>", h)
        self.assertIn("<li>Brand new note</li>", h)

    def test_template_text_is_not_a_capture(self):
        h = self.run_js({"stage": 1, "levels": [{"lv": 1, "cap": 2, "rules": ["At most <b> subagents at once"]}]},
                        {"At most {1} subagents at once": "KO {1}"})
        self.assertIn("At most &lt;b&gt; subagents at once", h)

    def test_off_highlights_nothing(self):
        h = self.run_js({"stage": 0, "mode": "off", "levels": LV})
        self.assertNotIn("class=on", h)


if __name__ == "__main__":
    unittest.main()
