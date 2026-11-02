"""Security badge/window (web/js/84l-structure-arch-checks.js): a scan where no scanner ran ok reads «not checked», never «issues 0»;
window header counts are scanner totals (image scans included), matching the badge's archChkSum."""
import json
import unittest

from tests.test_struct_arch_checks_js import run

NONE_RAN = {"at": 1700000000, "tools": [{"id": "semgrep", "status": "fail", "why": "exit 2", "n": {}}, {"id": "osv", "status": "missing", "n": {}}], "top": []}
CLEAN = {"at": 1700000000, "tools": [{"id": "semgrep", "status": "ok", "n": {}}], "top": []}
NEVER = {"tools": [], "top": []}
IMG = {"at": 1700000000, "tools": [{"id": "bandit", "status": "ok", "n": {"high": 1}},
                                   {"id": "trivy-image", "target": "node:18", "status": "ok", "n": {"critical": 1, "high": 2}}],
       "top": [{"tool": "bandit", "file": "a.py", "line": 1, "rule": "B1", "sev": "high"}]}


def _d(sec):
    return {"checks": {"security": sec}}


class Unchecked(unittest.TestCase):
    def test_badge_states(self):
        r = run("globalThis.lsJson = () => ({}); const qs = " + json.dumps([_d(NONE_RAN), _d(CLEAN), _d(NEVER)]) + ";"
                "console.log(JSON.stringify(qs.map(x => archChkTopBtn(x, '/r'))));", lang="en")
        self.assertIn(">Security not checked</button>", r[0])
        self.assertIn("strbg-archckin", r[0])
        self.assertNotIn("archckiw", r[0])
        self.assertIn(">Security issues 0</button>", r[1])       # ran clean stays amber «issues 0»
        self.assertIn("strbg-archckiw", r[1])
        self.assertIn(">Security issues 0</button>", r[2])       # «Never checked» unchanged
        self.assertNotIn("archckin", r[2])

    def test_window_none_ran_line(self):
        r = run("globalThis.lsJson = () => ({}); const qs = " + json.dumps([_d(NONE_RAN), _d(CLEAN)]) + ";"
                "console.log(JSON.stringify(qs.map(x => archChkWinHtml('/r', x, {sel: {}}, []))));", lang="en")
        self.assertIn(">No scanner ran</div>", r[0])
        self.assertIn(">No scanner findings</div>", r[1])

    def test_ko_labels(self):
        r = run("globalThis.lsJson = () => ({}); const x = " + json.dumps(_d(NONE_RAN)) + ";"
                "console.log(JSON.stringify([archChkTopBtn(x, '/r'), archChkWinHtml('/r', x, {sel: {}}, [])]));")
        self.assertIn(">보안 미점검</button>", r[0])
        self.assertIn(">실행된 검사기 없음</div>", r[1])

    def test_header_counts_include_image(self):
        r = run("globalThis.lsJson = () => ({}); const x = " + json.dumps(_d(IMG)) + ";"
                "console.log(JSON.stringify([archChkWinHtml('/r', x, {sel: {}}, []), archChkWinHtml('/r', x, {sel: {}, sev: 'critical'}, []),"
                " archChkWinHtml('/r', x, {sel: {}, tool: 'bandit'}, [])]));", lang="en")
        self.assertIn("critical 1 · high 3 · medium 0 · low 0", r[0])
        self.assertIn("<span>critical 1 · shown 0 of 1</span>", r[1])
        self.assertIn("critical 0 · high 1 · medium 0 · low 0", r[2])


if __name__ == "__main__":
    unittest.main()
