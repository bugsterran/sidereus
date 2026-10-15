"""saver._saver_views: per-account hook snapshots by label. Temp dir only, accounts faked."""
import hashlib
import json
import os
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus, load

load()
sv = sidereus("saver")


class SaverViews(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-svviews-")
        self.accts = [{"dir": os.path.join(self.tmp, "a"), "label": "personal", "primary": True},
                      {"dir": os.path.join(self.tmp, "b"), "label": "work", "primary": False},
                      {"dir": os.path.join(self.tmp, "c"), "label": "side", "primary": False}]
        for obj, name, val in ((sv, "SAVER_VIEW", os.path.join(self.tmp, ".saver-view.json")),
                               (sv, "claude_accounts", lambda: self.accts)):
            p = mock.patch.object(obj, name, val)
            p.start()
            self.addCleanup(p.stop)

    def put(self, d, body):
        tag = hashlib.sha1(os.path.realpath(d).encode()).hexdigest()[:10]
        with open(os.path.join(self.tmp, ".saver-view-%s.json" % tag), "w") as f:
            f.write(body)

    def test_tag_maps_to_label_broken_skipped(self):
        self.put(self.accts[0]["dir"], json.dumps({"stage": 9}))   # primary: never read here
        self.put(self.accts[1]["dir"], json.dumps({"stage": 2, "pct": 61}))
        self.put(self.accts[2]["dir"], "{broken")
        self.assertEqual(sv._saver_views(), {"work": {"stage": 2, "pct": 61}})

    def test_none(self):
        self.assertEqual(sv._saver_views(), {})


if __name__ == "__main__":
    unittest.main()
