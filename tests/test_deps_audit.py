"""scripts/deps_audit.py: import guard and EOL logic over tmp files — no network, clock or live files."""
import datetime
import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("deps_audit", os.path.join(os.path.dirname(HERE), "scripts", "deps_audit.py"))
da = importlib.util.module_from_spec(spec)
spec.loader.exec_module(da)


class ImportGuard(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="deps-audit-")
        self.addCleanup(shutil.rmtree, self.root)
        os.makedirs(os.path.join(self.root, "sidereus"))

    def _w(self, rel, text):
        p = os.path.join(self.root, rel)
        with open(p, "w", encoding="utf-8") as h:
            h.write(text)
        return p

    def test_stdlib_and_first_party_pass(self):
        self._w("sidereus/util.py", "x = 1\n")
        f = self._w("sidereus/a.py", "import os, json\nfrom urllib import request\nfrom . import util\nimport util\n"
                                   "try:\n    import zoneinfo\nexcept ImportError:\n    pass\n")
        self.assertEqual(da.foreign_py([f], self.root), [])

    def test_third_party_flagged(self):
        f = self._w("sidereus/b.py", "import requests\nfrom yaml import safe_load\nimport os.path\n")
        self.assertEqual(da.foreign_py([f], self.root), [("sidereus/b.py", "requests"), ("sidereus/b.py", "yaml")])

    def test_syntax_error_reported(self):
        f = self._w("sidereus/c.py", "def (:\n")
        self.assertEqual(da.foreign_py([f], self.root), [("sidereus/c.py", "<syntax>")])

    def test_mjs_guard(self):
        ok = self._w("ok.mjs", "import fs from 'node:fs'\nimport { a } from './x.mjs'\nconst p = await import('playwright')\n")
        bad = self._w("bad.mjs", "import x from 'lodash'\nconst y = require(\"chalk\")\nimport 'side-effect'\n")
        self.assertEqual(da.foreign_mjs([ok], self.root), [])
        self.assertEqual(da.foreign_mjs([bad], self.root),
                         [("bad.mjs", "chalk"), ("bad.mjs", "lodash"), ("bad.mjs", "side-effect")])


class Eol(unittest.TestCase):
    T = {"3.9": "2025-10-31", "3.12": "2028-10-31"}

    def test_levels(self):
        d = datetime.date(2026, 10, 12)
        self.assertEqual(da.eol_status("3.9", self.T, d)[0], "WARN")
        self.assertEqual(da.eol_status("3.12", self.T, d)[0], "OK")
        self.assertEqual(da.eol_status("3.12", self.T, datetime.date(2028, 6, 1))[0], "WARN")   # within 180 days
        self.assertIn("not in the EOL table", da.eol_status("4.0", self.T, d)[1])

    def test_plist_program_skips_comments(self):
        x = ("<key>ProgramArguments</key>\n<array>\n<!-- a -- b <string>/no</string> -->\n"
             "<string>/usr/bin/python3</string>\n<string>srv.py</string>\n</array>")
        self.assertEqual(da.plist_program(x), "/usr/bin/python3")
        self.assertEqual(da.plist_program("<plist/>"), "?")


if __name__ == "__main__":
    unittest.main()
