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
        f = self._w(os.path.join("sidereus", "b.py"), "import requests\nfrom yaml import safe_load\nimport os.path\n")
        self.assertEqual(da.foreign_py([f], self.root), [(os.path.join("sidereus", "b.py"), "requests"), (os.path.join("sidereus", "b.py"), "yaml")])

    def test_syntax_error_reported(self):
        f = self._w(os.path.join("sidereus", "c.py"), "def (:\n")
        self.assertEqual(da.foreign_py([f], self.root), [(os.path.join("sidereus", "c.py"), "<syntax>")])

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


class Online(unittest.TestCase):
    def test_offline_reason_probe_both_ways(self):
        self.assertIsNone(da.offline_reason([], lambda: True))
        self.assertEqual(da.offline_reason([], lambda: False), "offline")
        self.assertEqual(da.offline_reason(["--offline"], lambda: 1 / 0), "--offline")   # opt-out never probes
        self.assertIsNone(da.offline_reason(["--online"], lambda: True))   # legacy flag: no-op

    def test_osv_vulns_pages_and_severity(self):
        pages = [{"vulns": [{"id": "GHSA-aaaa-bbbb-cccc", "database_specific": {"severity": "HIGH"}, "details": "x"}],
                  "next_page_token": "t"}, {"vulns": [{"id": "CVE-1"}]}]
        sent = []
        fetch = lambda url, body: sent.append(body) or pages[len(sent) - 1]
        self.assertEqual(da.osv_vulns("npm", "p", "1.0.0", fetch), [("GHSA-aaaa-bbbb-cccc", "high"), ("CVE-1", "unrated")])
        self.assertEqual((sent[0]["package"], "page_token" in sent[0], sent[1]["page_token"]),
                         ({"name": "p", "ecosystem": "npm"}, False, "t"))
        self.assertEqual(da.osv_vulns("npm", "p", "1", lambda u, b: {}), [])
        with self.assertRaises(ValueError):
            da.osv_vulns("npm", "p", "1", lambda u, b: [])

    def test_osv_targets(self):
        root = tempfile.mkdtemp(prefix="deps-audit-")
        self.addCleanup(shutil.rmtree, root)
        os.makedirs(os.path.join(root, "node_modules", "playwright"))
        with open(os.path.join(root, "node_modules", "playwright", "package.json"), "w", encoding="utf-8") as h:
            h.write('{"version": "1.2.3"}')
        f = os.path.join(root, "a.mjs")
        with open(f, "w", encoding="utf-8") as h:
            h.write("import { chromium } from 'playwright';\nimport p from 'puppeteer';\n")
        self.assertEqual(da.osv_targets([f], root), [("npm", "playwright", "1.2.3")])
        self.assertEqual(da.osv_targets([], root), [])


class Collect(unittest.TestCase):
    """collect(): default covers the viewer's python only; --dev adds node / Chrome / drivers; never the Claude CLI."""
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="deps-audit-")
        self.addCleanup(shutil.rmtree, self.root)
        os.makedirs(os.path.join(self.root, "scripts"))
        os.makedirs(os.path.join(self.root, "node_modules", "playwright"))
        with open(os.path.join(self.root, "node_modules", "playwright", "package.json"), "w", encoding="utf-8") as h:
            h.write('{"version": "1.2.3"}')
        with open(os.path.join(self.root, "scripts", "a.mjs"), "w", encoding="utf-8") as h:
            h.write("import { chromium } from 'playwright';\n")
        self.ran, self.fetched = [], []
        rows = {"python": [{"cycle": "3.9", "latest": "3.9.6", "eol": "2025-10-31"}],
                "nodejs": [{"cycle": "22", "latest": "22.1.0", "eol": "2027-04-30"}]}

        def fetch(url, body=None):
            self.fetched.append(url)
            if body is not None:
                return {}
            return rows["python" if "python" in url else "nodejs"]
        vals = {"ROOT": self.root, "CHROME_APP": os.path.join(self.root, "none.app"), "_launchd_python": lambda: "/usr/bin/python3",
                "_run": lambda argv: self.ran.append(argv) or ("v22.1.0" if argv[0] == "node" else "3.9.6"),
                "_probe": lambda: True, "_fetch": fetch}
        old = {k: getattr(da, k) for k in vals}
        for k, v in vals.items():
            setattr(da, k, v)
        self.addCleanup(lambda: [setattr(da, k, v) for k, v in old.items()])

    def items(self, argv):
        return [x[1] for x in da.collect(argv)]

    def test_default(self):
        it = self.items([])
        self.assertEqual(it, ["python imports", "python (launchd: /usr/bin/python3)", "online python"])
        self.assertEqual([a[0] for a in self.ran], ["/usr/bin/python3"])
        self.assertFalse(any("nodejs" in u or "osv" in u for u in self.fetched))

    def test_dev(self):
        it = self.items(["--dev"])
        for w in ("node imports", "node (dev tooling)", "browser (screen_check)", "online nodejs", "osv playwright 1.2.3",
                  "osv runtimes"):
            self.assertIn(w, it)
        self.assertFalse(any("claude" in x.lower() for x in it))
        self.assertNotIn("claude", [a[0] for a in self.ran])

    def test_offline_and_main(self):
        it = da.collect(["--offline", "--dev"])
        self.assertEqual(it[-1][:2], ("WARN", "online lookups"))
        self.assertEqual(self.fetched, [])
        import io
        from contextlib import redirect_stdout
        with redirect_stdout(io.StringIO()) as out:
            rc = da.main(["--offline"])
        self.assertEqual(rc, 0)
        self.assertIn("OK   python imports — stdlib + first-party only", out.getvalue())


if __name__ == "__main__":
    unittest.main()
