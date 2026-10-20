"""Watcher suffix beside «입력 대기» (web/js/20-session-state.js monSuffix): one = its label, 2+ = count; state label unchanged."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_switch
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(name):
    with open(os.path.join(ROOT, "web", "js", name), encoding="utf-8") as f:
        return f.read()


def run(lang, extra_cases=(), row=False):
    s = _src("20-session-state.js")
    lst = _src("40b-sessions-list.js")
    fn = lambda n, src=s: re.search(r"^function " + n + r"\(.*?^}", src, re.S | re.M).group(0)
    lbl = re.search(r"^const LBL = \{.*?\};", s, re.S | re.M).group(0)
    ctx = re.search(r"^const LBL_CTX = \{.*?\};", s, re.S | re.M).group(0)
    mon = [{"lab": "x", "min": 1, "src": "proc"}, {"lab": "y", "min": 2, "src": "beat"}]
    cases = [{"state": "wait", "mon": mon}, {"state": "wait", "mon": []}, {"state": "wait", "mon": mon[:1]},
             {"state": "wait", "bgs": [{}], "mon": mon}, {"state": "tool", "ageSec": 5, "mon": mon},
             {"state": "think", "ageSec": 5, "mon": mon}, {"state": "wait", "blocked": "b", "mon": mon}]
    cases += list(extra_cases)
    out = ("C.map(x => sessStateRow(x, x.state))" if row else "C.map(x => [sessLabel(x), monSuffix(x, x.state)])")
    js = "\n".join(["let LANG = " + json.dumps(lang) + ";",
                    i18n_switch(("T", "TV", "U", "srvEn", "monLab")), lbl, ctx, fn("stateLbl"),
                    fn("sessLabel"), fn("wfRunning"), fn("waitOnLabel"), fn("monSuffix"), fn("sessKidLab", lst),
                    fn("sessStateRow", lst), "const esc = v => String(v), TIP = {}, BLKTIP = '', WAITTIP = '';",
                    "const sessAgoHtml = () => 'AGO', sessBurn = () => '';",
                    "const C = " + json.dumps(cases) + ";",
                    "console.log(JSON.stringify(" + out + "));"])
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class MonSuffix(unittest.TestCase):
    def test_ko(self):
        self.assertEqual(run("ko"), [["입력 대기", "· 감시 2"], ["입력 대기", ""], ["입력 대기", "· x"],
                                     ["명령 작업 완료 대기", ""], ["도구 실행 중", ""], ["생각 중", ""],
                                     ["막힘 · b", ""]])

    def test_en_plural(self):
        r = run("en")
        self.assertEqual((r[0][1], r[2][1], r[1][1]), ("· 2 monitors", "· x", ""))

    def test_single_watcher_label(self):
        w = [{"state": "wait", "mon": [{"lab": "Mailbox watch · ab12", "min": 1, "src": "proc"}]}]
        self.assertEqual(run("ko", w)[-1][1], "· 메일박스 감시 · ab12")
        self.assertEqual(run("en", w)[-1][1], "· Mailbox watch · ab12")

    def test_row_drops_stale_tool_while_watching(self):
        m1 = [{"lab": "Mailbox watch", "min": 1, "src": "proc"}]
        r = run("ko", [{"state": "wait", "tool": "Bash", "ageSec": 3, "mon": m1},
                       {"state": "tool", "tool": "Bash", "ageSec": 3, "mon": m1},
                       {"state": "wait", "tool": "Bash", "ageSec": 3, "mon": []}], row=True)[-3:]
        self.assertNotIn("Bash", r[0])
        self.assertIn("메일박스 감시</span> · AGO", r[0])
        self.assertIn("Bash · AGO", r[1])
        self.assertIn("Bash · AGO", r[2])


if __name__ == "__main__":
    unittest.main()
