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


class RtVerdict(unittest.TestCase):
    """rt_verdict: patch line vs own cycle, newest line vs every line. Pure — no network or clock."""
    TODAY = datetime.date(2026, 10, 28)
    NODE = {"rt": "nodejs", "path": "/opt/homebrew/opt/node@22/bin/node", "cls": "homebrew", "viewer": False}
    PY = {"rt": "python", "path": "/usr/bin/python3", "cls": "system", "viewer": True}
    NREL = [{"v": v, "security": s} for v, s in (("26.1.0", False), ("25.9.0", False), ("24.10.0", False),
                                                  ("22.23.4", False), ("22.23.3", True), ("22.23.2", False))]

    def lv(self, it):
        return (it["level"], it["patch"]["level"], it["patch"]["target"], it["patch"]["security"], it["newest"]["level"],
                it["newest"]["target"], it["newest"]["behind_n"])

    def test_fail_eol(self):
        it = da.rt_verdict(self.PY, "3.9.6", [{"v": "3.9.25", "security": False}, {"v": "3.14.2", "security": False},
                                              {"v": "3.12.9", "security": False}], da.PY_EOL, self.TODAY)
        self.assertEqual(self.lv(it), ("fail", "fail", "3.9.25", False, "info", "3.14.2", 2))
        self.assertEqual((it["patch"]["eol"], it["patch"]["eol_past"], it["cycle"]), ("2025-10-31", True, "3.9"))

    def test_fail_missed_node_security(self):
        it = da.rt_verdict(self.NODE, "22.23.2", self.NREL, da.NODE_EOL, self.TODAY)
        self.assertEqual(self.lv(it), ("fail", "fail", "22.23.4", True, "info", "26.1.0", 2))   # odd 25 not counted

    def test_warn_patch_behind(self):
        it = da.rt_verdict(self.NODE, "22.23.3", self.NREL, da.NODE_EOL, self.TODAY)
        self.assertEqual(self.lv(it), ("warn", "warn", "22.23.4", False, "info", "26.1.0", 2))

    def test_info_only_below_newest(self):
        it = da.rt_verdict(self.NODE, "22.23.4", self.NREL, da.NODE_EOL, self.TODAY)
        self.assertEqual(self.lv(it), ("info", "ok", "22.23.4", False, "info", "26.1.0", 2))
        top = da.rt_verdict(self.NODE, "26.1.0", self.NREL, da.NODE_EOL, self.TODAY)
        self.assertEqual(self.lv(top)[:2] + self.lv(top)[4:], ("ok", "ok", "ok", "26.1.0", 0))

    def test_cycle_not_in_eol_table_never_ok(self):
        rel = self.NREL + [{"v": "25.9.1", "security": False}]
        it = da.rt_verdict(self.NODE, "25.9.1", rel, da.NODE_EOL, self.TODAY)   # odd major: no EOL date here
        self.assertEqual((it["patch"]["level"], it["patch"]["eol"], it["level"]), ("unknown", "", "unknown"))
        behind = da.rt_verdict(self.NODE, "25.9.0", rel, da.NODE_EOL, self.TODAY)
        self.assertEqual(behind["patch"]["level"], "warn")

    def test_unknown_no_data(self):
        it = da.rt_verdict(self.NODE, "22.23.3", None, da.NODE_EOL, self.TODAY)
        self.assertEqual(self.lv(it), ("unknown", "unknown", "", False, "unknown", "", 0))
        py = da.rt_verdict(self.PY, "3.9.6", None, da.PY_EOL, self.TODAY)
        self.assertEqual((py["level"], py["patch"]["level"]), ("fail", "fail"))   # EOL is known offline
        miss = da.rt_verdict(self.NODE, "21.0.0", self.NREL, da.NODE_EOL, self.TODAY)
        self.assertEqual(miss["patch"]["level"], "unknown")   # own line not listed: never ok


class Runtimes(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="deps-rt-"))
        self.addCleanup(shutil.rmtree, self.root)
        brew = os.path.join(self.root, "brew")
        cel = os.path.join(brew, "Cellar", "python@3.12", "3.12.9", "bin")
        os.makedirs(cel)
        open(os.path.join(cel, "python3.12"), "w", encoding="utf-8").close()
        for d in ("python@3.12", "python@3"):   # python@3 links to the same keg: one row after realpath dedupe
            os.makedirs(os.path.join(brew, "opt", d, "bin"))
            os.symlink(os.path.join(cel, "python3.12"), os.path.join(brew, "opt", d, "bin", "python3.12"))
        open(os.path.join(brew, "opt", "python@3.12", "bin", "python3.12-config"), "w", encoding="utf-8").close()
        nb = os.path.join(brew, "opt", "node@22", "bin")
        os.makedirs(nb)
        open(os.path.join(nb, "node"), "w", encoding="utf-8").close()
        sysp = os.path.join(self.root, "usr-bin-python3")
        open(sysp, "w", encoding="utf-8").close()
        self.ran = []
        ver = {"python3.12": "3.12.9", "usr-bin-python3": "3.9.6", "node": "v22.23.3"}
        vals = {"RT_PREFIXES": (brew,), "SYS_PY": sysp, "_launchd_python": lambda: sysp,
                "_which": lambda n: os.path.join(nb, "node"),
                "_run": lambda argv: self.ran.append(argv) or ver.get(os.path.basename(argv[0]), "")}
        old = {k: getattr(da, k) for k in vals}
        for k, v in vals.items():
            setattr(da, k, v)
        self.addCleanup(lambda: [setattr(da, k, v) for k, v in old.items()])

    def test_realpath_dedupe_and_classes(self):
        rows = da.runtimes(dev=True)
        self.assertEqual([(r["rt"], r["cls"], r["viewer"], r["cur"]) for r in rows],
                         [("python", "homebrew", False, "3.12.9"), ("python", "system", True, "3.9.6"),
                          ("nodejs", "homebrew", False, "22.23.3")])
        self.assertFalse(any(a[0].endswith("-config") for a in self.ran))
        self.assertEqual([r["rt"] for r in da.runtimes(dev=False)], ["python", "python"])


class CollectRich(Collect):
    """rich=[] adds one runtime dict and the release fetches; the printed lines stay byte-identical."""
    def setUp(self):
        super().setUp()
        rels = {da.PY_RELEASES: [{"name": "Python 3.9.25", "pre_release": False}, {"name": "Python 3.15.0a1", "pre_release": True}],
                da.NODE_RELEASES: [{"version": "v22.2.0", "security": True}]}
        base, rts = da._fetch, da.runtimes
        da._fetch = lambda url, body=None: (self.fetched.append(url) or rels[url]) if url in rels else base(url, body)
        da.runtimes = lambda dev=True: [{"rt": "python", "path": "/usr/bin/python3", "cls": "system", "viewer": True, "cur": "3.9.6"}]
        self.addCleanup(lambda: [setattr(da, "_fetch", base), setattr(da, "runtimes", rts)])

    def test_lines_identical_and_fetch_only_when_rich(self):
        plain = da.collect(["--dev"])
        self.assertFalse(any(u in (da.PY_RELEASES, da.NODE_RELEASES) for u in self.fetched))
        rich = []
        self.assertEqual(da.collect(["--dev"], rich=rich), plain)
        self.assertEqual(len(rich), 1)
        self.assertIn(da.NODE_RELEASES, self.fetched)
        it = rich[0]["items"][0]
        self.assertEqual((rich[0]["offline"], it["patch"]["level"], it["patch"]["target"]), (False, "fail", "3.9.25"))

    def test_main_stdout_identical_and_offline_unknown(self):
        import io
        from contextlib import redirect_stdout
        with redirect_stdout(io.StringIO()) as a:
            da.main(["--offline"])
        rich, orig = [], da.collect
        da.collect = lambda argv: orig(argv, rich=rich)
        try:
            with redirect_stdout(io.StringIO()) as b:
                da.main(["--offline"])
        finally:
            da.collect = orig
        self.assertEqual(a.getvalue(), b.getvalue())
        self.assertEqual(rich[0]["offline"], True)
        self.assertEqual(rich[0]["items"][0]["newest"]["level"], "unknown")


if __name__ == "__main__":
    unittest.main()
