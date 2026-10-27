"""Settings «Security tools» (sidereus/sec_tools.py): installed + version from the file layout only, install command per OS,
no paths in the reply, nothing executed, and the «what it catches» text matches SECURITY.md."""
import json
import os
import re
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import ROOT, sidereus

ST = sidereus("sec_tools")
SC = sidereus("sec_checks")


def _touch(p, text=""):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


class SecTools(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix="sectools-")
        self.addCleanup(shutil.rmtree, self.t, True)
        t = self.t
        _touch(os.path.join(t, "Cellar/gitleaks/8.18.0_1/bin/gitleaks"))
        os.makedirs(os.path.join(t, "bin"))
        os.symlink(os.path.join(t, "Cellar/gitleaks/8.18.0_1/bin/gitleaks"), os.path.join(t, "bin/gitleaks"))
        _touch(os.path.join(t, "node/lib/node_modules/npm/package.json"), json.dumps({"name": "npm", "version": "10.8.2"}))
        _touch(os.path.join(t, "node/lib/node_modules/npm/bin/npm-cli.js"))
        os.makedirs(os.path.join(t, "node/bin"))
        os.symlink(os.path.join(t, "node/lib/node_modules/npm/bin/npm-cli.js"), os.path.join(t, "node/bin/npm"))
        _touch(os.path.join(t, "pipx/venvs/semgrep/bin/semgrep"))
        os.makedirs(os.path.join(t, "pipx/venvs/semgrep/lib/python3.12/site-packages/semgrep-1.90.0.dist-info"))
        os.symlink(os.path.join(t, "pipx/venvs/semgrep/bin/semgrep"), os.path.join(t, "bin/semgrep"))
        _touch(os.path.join(t, "venv/bin/bandit"))
        junk = "1.7<b>;x" if os.name == "posix" else "1.7;x"   # ⚠'<' '>' are invalid in Windows file names
        os.makedirs(os.path.join(t, "venv/lib/python3.9/site-packages/bandit-%s.dist-info" % junk))
        self.where = {"gitleaks": os.path.join(t, "bin/gitleaks"), "npm": os.path.join(t, "node/bin/npm"),
                      "semgrep": os.path.join(t, "bin/semgrep"), "bandit": os.path.join(t, "venv/bin/bandit")}

    def rows(self, where=None, nt=False, mac=True):
        w = self.where if where is None else where
        with mock.patch.object(ST, "_which", lambda n: w.get(n)), \
                mock.patch.object(SC.os, "name", "nt" if nt else "posix"), \
                mock.patch.object(SC.sys, "platform", "darwin" if mac and not nt else "win32" if nt else "linux"):
            return {r["id"]: r for r in ST.tools()}

    def test_versions_from_layout(self):
        r = self.rows()
        self.assertEqual([x for x in r], ["gitleaks", "semgrep", "bandit", "osv-scanner", "npm", "trivy"])
        self.assertEqual(r["trivy"]["net"], "images")
        self.assertEqual(r["gitleaks"], {"id": "gitleaks", "installed": True, "version": "8.18.0", "cmd": None, "net": "no"})
        self.assertEqual(r["npm"]["version"], "10.8.2")
        self.assertEqual(r["semgrep"]["version"], "1.90.0")
        self.assertTrue(r["bandit"]["installed"])
        self.assertIsNone(r["bandit"]["version"])                 # junk dist-info version -> null

    def test_missing_cmd_per_os(self):
        mac = self.rows(where={})
        self.assertEqual(mac["gitleaks"]["cmd"], "brew install gitleaks")
        self.assertEqual(mac["npm"]["cmd"], "brew install node")
        self.assertEqual(mac["trivy"]["cmd"], "brew install trivy")
        self.assertFalse(mac["osv-scanner"]["installed"])
        win = self.rows(where={}, nt=True)
        self.assertEqual(win["gitleaks"]["cmd"], "winget install Gitleaks.Gitleaks")   # «(or scoop)» stripped
        self.assertEqual(win["osv-scanner"]["cmd"], "winget install Google.OSVScanner")
        self.assertEqual(win["semgrep"]["cmd"], "pip install semgrep")
        self.assertEqual(win["npm"]["cmd"], "winget install OpenJS.NodeJS.LTS")
        self.assertEqual(win["trivy"]["cmd"], "winget install AquaSecurity.Trivy")
        self.assertEqual(self.rows(where={}, mac=False)["npm"]["cmd"], "nodejs.org")

    def test_install_hint_unchanged(self):
        with mock.patch.object(SC.os, "name", "nt"):
            self.assertEqual(SC.install_hint("gitleaks"), "install: winget install Gitleaks.Gitleaks (or scoop)")

    def test_no_paths_in_reply(self):
        blob = json.dumps(self.rows())
        self.assertNotIn(self.t, blob)
        self.assertNotIn("/", blob)
        for r in self.rows().values():
            self.assertEqual(sorted(r), ["cmd", "id", "installed", "net", "version"])

    def test_nothing_executed(self):
        with open(os.path.join(ROOT, "sidereus", "sec_tools.py"), encoding="utf-8") as f:
            src = f.read()
        for bad in ("subprocess", "os.system", "Popen", "popen", "os.exec", "spawn"):
            self.assertNotIn(bad, src)

    def test_catch_text_matches_security_md(self):
        with open(os.path.join(ROOT, "web", "js", "90e-diag.js"), encoding="utf-8") as f:
            js = f.read()
        block = re.search(r"const SEC_CATCH = \{(.*?)\n\};", js, re.S).group(1)
        catch = dict(re.findall(r"'([^']+)': '([^']+)'", block))
        self.assertEqual(sorted(catch), sorted(t for t, _ in ST.TOOLS))
        with open(os.path.join(ROOT, "SECURITY.md"), encoding="utf-8") as f:
            md = f.read()
        sec = md.split("## Security tools", 1)[1].split("\n## ", 1)[0]
        rows = [ln for ln in sec.splitlines() if ln.startswith("| `")]
        self.assertEqual(len(rows), len(ST.TOOLS))
        for tid, text in catch.items():
            self.assertTrue(any(ln.startswith("| `%s` | %s |" % (tid, text)) for ln in rows), tid)


if __name__ == "__main__":
    unittest.main()
