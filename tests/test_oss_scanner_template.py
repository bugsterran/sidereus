"""OSS Scanner files (templates/oss-scanner/ and the filled .oss-scanner/) keep the upstream format.

Reads repo files only.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANGUL = re.compile("[가-힣ᄀ-ᇿ㄰-㆏]")
DIRS = ("templates/oss-scanner", ".oss-scanner")
HEADINGS = ("# Threat model",
            "## What this project does and where untrusted input enters",
            "## Components that matter most / least",
            "## How to exercise it",
            "## How you rate severity",
            "## Anything to leave alone",
            "## Report and patch preferences")
KEYS = ("repo", "primary_contact", "auto_ccs", "homepage", "disabled", "dockerfile", "threat_model")
FETCH = re.compile(r"\b(apt-get|apk|pip3?|npm|yarn|curl|wget|git\s+clone|go\s+get|ADD\s+https?:)", re.I)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def yaml_top(text):
    """{key: raw value} for top-level `key: value` lines (no YAML library offline)."""
    out = {}
    for ln in text.splitlines():
        m = re.match(r"^([a-z_]+):\s*(.*)$", ln)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


class OssScannerFiles(unittest.TestCase):
    def test_threat_model_headings_in_order(self):
        for d in DIRS:
            heads = [ln.strip() for ln in read(d + "/threat_model.md").splitlines() if ln.startswith("#")]
            self.assertEqual(tuple(heads), HEADINGS, d)

    def test_project_yaml_keys_and_paths(self):
        for d in DIRS:
            y = yaml_top(read(d + "/project.yaml"))
            for k in KEYS:
                self.assertIn(k, y, "%s: %s" % (d, k))
            self.assertEqual(y["dockerfile"], ".oss-scanner/Dockerfile", d)
            self.assertEqual(y["threat_model"], ".oss-scanner/threat_model.md", d)
            self.assertIn(y["disabled"], ("true", "false"), d)
            self.assertTrue(y["repo"].startswith("https://"), d)
        self.assertTrue(yaml_top(read(".oss-scanner/project.yaml"))["repo"]
                        .startswith("https://github.com/bugsterran/sidereus"))

    def test_no_hangul(self):
        for d in DIRS:
            for name in os.listdir(os.path.join(ROOT, d)):
                self.assertIsNone(HANGUL.search(read(d + "/" + name)), d + "/" + name)

    def test_dockerfile_offline_after_copy(self):
        for d in DIRS:
            lines = [ln for ln in read(d + "/Dockerfile").splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
            copies = [i for i, ln in enumerate(lines) if re.match(r"^COPY\s+\.\s+/src\b", ln)]
            self.assertEqual(len(copies), 1, d)
            self.assertTrue(lines[0].startswith("FROM "), d)
            tail = lines[copies[0] + 1:]
            self.assertTrue(tail, d)
            for ln in tail:
                self.assertIsNone(FETCH.search(ln), "%s: network fetch after COPY: %s" % (d, ln))

    def test_security_links_scanner_folder(self):
        for f in ("SECURITY.md", "SECURITY.ko.md"):
            self.assertIn("(.oss-scanner/)", read(f), f)


if __name__ == "__main__":
    unittest.main()
