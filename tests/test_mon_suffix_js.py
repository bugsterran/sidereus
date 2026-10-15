"""«· 감시 N» suffix beside «입력 대기» (web/js/20-session-state.js monSuffix): count only, state label unchanged."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_switch
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(lang):
    s = open(os.path.join(ROOT, "web", "js", "20-session-state.js"), encoding="utf-8").read()
    fn = lambda n: re.search(r"^function " + n + r"\(.*?^}", s, re.S | re.M).group(0)
    lbl = re.search(r"^const LBL = \{.*?\};", s, re.S | re.M).group(0)
    ctx = re.search(r"^const LBL_CTX = \{.*?\};", s, re.S | re.M).group(0)
    mon = [{"lab": "x", "min": 1, "src": "proc"}, {"lab": "y", "min": 2, "src": "beat"}]
    cases = [{"state": "wait", "mon": mon}, {"state": "wait", "mon": []}, {"state": "wait", "mon": mon[:1]},
             {"state": "wait", "bgs": [{}], "mon": mon}, {"state": "tool", "ageSec": 5, "mon": mon},
             {"state": "think", "ageSec": 5, "mon": mon}, {"state": "wait", "blocked": "b", "mon": mon}]
    js = "\n".join(["let LANG = " + json.dumps(lang) + ";",
                    i18n_switch(("T", "TV", "U", "srvEn")), lbl, ctx, fn("stateLbl"),
                    fn("sessLabel"), fn("wfRunning"), fn("waitOnLabel"), fn("monSuffix"),
                    "const C = " + json.dumps(cases) + ";",
                    "console.log(JSON.stringify(C.map(x => [sessLabel(x), monSuffix(x, x.state)])));"])
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class MonSuffix(unittest.TestCase):
    def test_ko(self):
        self.assertEqual(run("ko"), [["입력 대기", "· 감시 2"], ["입력 대기", ""], ["입력 대기", "· 감시 1"],
                                     ["명령 작업 완료 대기", ""], ["도구 실행 중", ""], ["생각 중", ""],
                                     ["막힘 · b", ""]])

    def test_en_plural(self):
        r = run("en")
        self.assertEqual((r[0][1], r[2][1], r[1][1]), ("· 2 monitors", "· 1 monitor", ""))


if __name__ == "__main__":
    unittest.main()
