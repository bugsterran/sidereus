"""Whole-file diff view: dfChangeN (30-diff.js) counts runs of +/- lines, the steps of the ▲▼ change arrows."""
import json
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def count(patch):
    js = "const NL='\\n';\n" + js_fn("dfChangeN") + "\nprocess.stdout.write(JSON.stringify(dfChangeN(" + json.dumps(patch) + ")));"
    return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True).stdout)


class ChangeCount(unittest.TestCase):
    def test_runs_not_lines(self):
        p = "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1,6 +1,6 @@\n a\n-b\n+B\n+C\n c\n d\n-e\n f\n+g"
        self.assertEqual(count(p), 3)   # -b+B+C is one block; -e and +g are two more

    def test_headers_and_empty(self):
        self.assertEqual(count("--- a/x\n+++ b/x\n@@ -1 +1 @@\n same"), 0)
        self.assertEqual(count(""), 0)


if __name__ == "__main__":
    unittest.main()
