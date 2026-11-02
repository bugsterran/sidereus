"""92-mainview-tabs.js rcWhoIds: every viewer spelling (viewerIds) is one entry, so a language switch does not count the viewer twice."""
import json
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def who(cfg, ids):
    js = ("const CFG = " + json.dumps(cfg) + ";\n" + js_fn("rcWhoIds")
          + "\nprocess.stdout.write(JSON.stringify(rcWhoIds(" + json.dumps(ids) + ")));")
    return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


class RoomWhoViewer(unittest.TestCase):
    def test_default_spellings_fold_into_one(self):
        cfg = {"viewerMe": "사용자", "viewerIds": ["사용자", "user"]}
        self.assertEqual(who(cfg, ["alpha", "user", "사용자", "alpha", ""]), ["alpha", "사용자"])

    def test_explicit_name_leaves_other_ids(self):
        self.assertEqual(who({"viewerMe": "kim", "viewerIds": ["kim"]}, ["kim", "user"]), ["kim", "user"])

    def test_cards_use_it(self):
        self.assertIn("who: rcWhoIds(", js_fn("rcCards"))


if __name__ == "__main__":
    unittest.main()
