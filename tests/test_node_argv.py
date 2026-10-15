"""tests/_node.node_e keeps JS source out of argv (Linux MAX_ARG_STRLEN = 128 KiB per argv string; CI failed with E2BIG)."""
import ast
import glob
import json
import os
import shutil
import subprocess
import unittest
import warnings

from tests._load import ROOT
from tests._node import ARG_MAX_SAFE, node_e


class NodeArgv(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_big_source_runs_like_dash_e(self):
        pad = "// " + "x" * 300000 + "\n"
        argv = node_e(pad + "const fs = require('fs'); process.stdout.write(JSON.stringify([process.argv.slice(1), typeof module]));", "a", "b")
        self.assertTrue(all(len(a) < ARG_MAX_SAFE for a in argv))
        r = subprocess.run(argv, capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), [["a", "b"], "object"])
        self.assertFalse(os.path.exists(argv[3]))   # loader removes its temp file

    def test_no_inline_node_e_in_tests(self):
        bad = []
        for p in sorted(glob.glob(os.path.join(ROOT, "tests", "*.py"))):
            if p.endswith("_node.py"):
                continue
            with open(p, encoding="utf-8") as f:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")   # other files' invalid-escape DeprecationWarnings
                    tree = ast.parse(f.read())
            for n in ast.walk(tree):
                if isinstance(n, ast.List) and len(n.elts) >= 3 and all(isinstance(e, ast.Constant) for e in n.elts[:2]) \
                        and [e.value for e in n.elts[:2]] == ["node", "-e"]:
                    bad.append("%s:%d" % (os.path.basename(p), n.lineno))
        self.assertEqual(bad, [], "use tests._node.node_e (source in argv breaks on Linux over 128 KiB)")


if __name__ == "__main__":
    unittest.main()
