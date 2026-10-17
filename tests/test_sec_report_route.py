"""GET /api/arch/secreport (arch_map.security_report): one security report file of an allowed repo's store.
Temp dirs only; allow list and ARCH_DIR patched."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock
from urllib.parse import quote, urlparse

from tests._load import sidereus

AM = sidereus("arch_map")
AV = sidereus("arch_verify")
RS = sidereus("routes_struct")
NAME = "security-report-20261017-0930.md"


class _Stub(RS._StructRoutes):
    def _raw_json(self, code, out, cache=True):
        self.code, self.raw = code, json.loads(json.dumps(out))


class SecReportRoute(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-secrep-"))
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        self.store = os.path.join(self.tmp, "store")
        self.kdir = os.path.join(self.store, AV.repo_key(self.repo))
        os.makedirs(self.kdir)
        self.allowed = {self.repo}
        roots = lambda p: (os.path.realpath(p) if p and os.path.realpath(p) in self.allowed else "")
        self.p = [mock.patch.object(AM, "ARCH_DIR", self.store), mock.patch.object(AM, "_struct_src_root", roots)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, name, text):
        with open(os.path.join(self.kdir, name), "w", encoding="utf-8") as f:
            f.write(text)

    def get(self, path, name):
        h = _Stub()
        h._g_arch_secreport(urlparse("/api/arch/secreport?path=%s&name=%s" % (quote(path), quote(name))))
        return h

    def test_ok(self):
        self.put(NAME, "# Report\n<b>x</b>\n")
        h = self.get(self.repo, NAME)
        self.assertEqual(h.code, 200)
        self.assertEqual(h.raw, {"ok": True, "name": NAME, "text": "# Report\n<b>x</b>\n"})

    def test_disallowed_root(self):
        self.put(NAME, "secret")
        self.allowed = set()
        r = self.get(self.repo, NAME).raw
        self.assertFalse(r["ok"])
        self.assertNotIn("text", r)

    def test_bad_names(self):
        self.put(NAME, "x")
        self.put("security-log.jsonl", "{}")
        for bad in ("security-log.jsonl", "../" + NAME, "security-report-2026101-0930.md", NAME + "x", "", "/etc/passwd",
                    "security-report-20261017-0930.md/../security-log.jsonl"):
            r = self.get(self.repo, bad).raw
            self.assertFalse(r["ok"], bad)
            self.assertNotIn("text", r)

    def test_symlink_refused(self):
        outside = os.path.join(self.tmp, "outside.md")
        with open(outside, "w", encoding="utf-8") as f:
            f.write("outside")
        os.symlink(outside, os.path.join(self.kdir, NAME))
        r = self.get(self.repo, NAME).raw
        self.assertFalse(r["ok"])
        self.assertNotIn("text", r)

    def test_missing(self):
        self.assertFalse(self.get(self.repo, NAME).raw["ok"])

    def test_registered(self):
        cs = __import__("tests._load", fromlist=["load"]).load()
        self.assertIs(cs.Handler._GET_ROUTES["/api/arch/secreport"], RS._StructRoutes._g_arch_secreport)


if __name__ == "__main__":
    unittest.main()
