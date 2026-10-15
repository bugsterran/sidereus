"""Drawer agent label split (40b subLab) and «+ 저장» visibility (97 vwHasState)."""
import json
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def node(src):
    return json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True).stdout)


class SubLab(unittest.TestCase):
    def run_(self, lab):
        return node("const SUB_PLAIN_TY = ['general-purpose', 'agent'];\n" + js_fn("plStrip") + "\n" + js_fn("subLab")
                    + "\nprocess.stdout.write(JSON.stringify(subLab(" + json.dumps(lab) + ")));")

    def test_default_types_drop_to_tooltip(self):
        self.assertEqual(self.run_("general-purpose: Fix the chat"), {"ty": "", "desc": "Fix the chat"})
        self.assertEqual(self.run_("agent: x"), {"ty": "", "desc": "x"})

    def test_other_type_becomes_chip(self):
        self.assertEqual(self.run_("sidereus-verifier: Gates"), {"ty": "sidereus-verifier", "desc": "Gates"})
        self.assertEqual(self.run_("plugin:rev: a: b"), {"ty": "plugin:rev", "desc": "a: b"})

    def test_plain_labels_untouched(self):
        for s in ("메일박스 감시 · Sidereus", "fix a: b", "", "general-purpose: "):
            r = self.run_(s)
            self.assertEqual(r["ty"], "", s)
        self.assertEqual(self.run_("fix a: b")["desc"], "fix a: b")      # a space before ':' = not a type prefix
        self.assertEqual(self.run_("general-purpose: ")["desc"], "general-purpose")


class SaveVisible(unittest.TestCase):
    def has(self, **k):
        st = dict({"place": "all", "filter": "all", "q": "", "idleMin": 0, "gitFil": "", "stFil": "", "todoOpen": False}, **k)
        pre = "".join("var %s = %s;\n" % (n, json.dumps(v)) for n, v in st.items())
        return node(pre + js_fn("vwHasState") + "\nprocess.stdout.write(JSON.stringify(vwHasState()));")

    def test_plain_room_list_has_nothing_to_save(self):
        self.assertFalse(self.has())

    def test_any_choice_is_savable(self):
        for k in ({"place": "room:dev"}, {"filter": "waiting"}, {"q": "x"}, {"idleMin": 10}, {"gitFil": "push"},
                  {"stFil": "ask"}, {"todoOpen": True}):
            self.assertTrue(self.has(**k), k)



class RoomTagParse(unittest.TestCase):
    def parse(self, s):
        return node(js_fn("rcParse") + "\nprocess.stdout.write(JSON.stringify(rcParse(" + json.dumps(s) + ")));")

    def test_case_insensitive_dedupe(self):
        self.assertEqual(self.parse("Dup,dup, DUP"), ["Dup"])

    def test_emoji_cut_at_code_points(self):
        out = self.parse("\U0001F600" * 25)
        self.assertEqual(out, ["\U0001F600" * 20])   # whole pairs only, never a lone surrogate

    def test_long_room_name_ellipsis_rule(self):
        import os, re
        css = open(os.path.join(os.path.dirname(__file__), "..", "web", "css", "50-layout-feed.css"), encoding="utf-8").read()
        rule = re.search(r"\.rmname\{([^}]*)\}", css).group(1)
        for k in ("min-width:0", "overflow:hidden", "text-overflow:ellipsis"):
            self.assertIn(k, rule)


if __name__ == "__main__":
    unittest.main()
