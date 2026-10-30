"""Harness «Guard self-check» fold (47f hnSelfcheck): R2 grouped rows · R3 real-run side cell · R4 not-run and stale states."""
import json
import os
import re
import subprocess
import unittest

from tests._load import ROOT
from tests._node import node_e
from tests import test_harness_js as thj   # module import: the Harness class must not be collected twice
from tests._i18n_js import i18n_switch

_FS = [os.path.join(ROOT, "web", "js", f) for f in ("47b-harness.js", "47e-harness-person.js", "47f-harness-selfcheck.js")]


def _js(body):
    src = thj._STUB + i18n_switch() + "const document = {addEventListener(){}, querySelector(){ return null; }};\n"
    for p in _FS:
        with open(p, encoding="utf-8") as f:
            src += f.read() + "\n"
    return json.loads(subprocess.run(node_e(src + body), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


def _c(name, guard, expect, actual, pair, codes=(), situation=None):
    return {"name": name, "guard": guard, "situation": situation or ("sit " + name), "expect": expect, "actual": actual,
            "pass": expect == actual, "pair": pair, "codes": list(codes)}


_CASES = [_c("gate-pass-only", "gate", "no r2g", "no r2g", "gate-red-green"),
          _c("gate-red-green", "gate", "r2g", "r2g", "gate-pass-only"),
          _c("guard-commit", "guard", "blocked", "blocked", "guard-commit-after-pass", ["gate"]),
          _c("guard-commit-after-fail", "guard", "blocked", "allowed", "guard-commit-after-pass"),
          _c("guard-commit-after-pass", "guard", "allowed", "allowed", "guard-commit-after-fail"),
          _c("guard-jump", "guard", "blocked", "blocked", "guard-jump-declared", ["jump"], situation="<img onerror=1> jump"),
          _c("guard-jump-declared", "guard", "allowed", "allowed", "guard-jump"),
          _c("guard-skip-declared", "guard", "allowed", "allowed", "guard-skip-required"),
          _c("guard-skip-required", "guard", "blocked", "blocked", "guard-skip-declared", ["skipgate"]),
          _c("keep-held", "keep", "held", "held", "keep-reverted"),
          _c("keep-reverted", "keep", "reverted", "reverted", "keep-held")]


def _data(sc):
    rep = json.loads(json.dumps(thj.Harness._REPORT))
    return json.dumps({"report": rep, "guards": dict(thj.Harness._GUARDS, codes={"jump": 2, "gate": 4, "<x>": 1}), "selfcheck": sc})


_OK = {"state": "ok", "ts": 1790000000, "head": "abcdef0123456789", "stale": False, "cmd": "python3 scripts/harness_selfcheck.py", "cases": _CASES}


class Selfcheck(unittest.TestCase):
    def test_node_check(self):
        subprocess.run(["node", "--check", _FS[2]], check=True)

    def test_r4_not_run(self):
        for sc in ({"state": "none", "cmd": "python3 scripts/harness_selfcheck.py"}, None):
            h = _js("console.log(JSON.stringify(hnSelfcheck(%s)))" % _data(sc))
            self.assertIn('data-hnmore=sc>', h)        # closed by default
            self.assertIn("아직 실행 안 함", h)
            self.assertIn("<code class=hnrc>python3 scripts/harness_selfcheck.py</code>", h)
            self.assertNotIn("hnskg", h)

    def test_r2_groups_rows(self):
        h = _js("console.log(JSON.stringify(hnSelfcheck(%s)))" % _data(_OK))
        self.assertIn("가드 자가 점검", h)
        groups = h.split("<div class=hnskg>")[1:]
        self.assertEqual(len(groups), 5)              # gate · commit · jump · skip · keep
        names = [re.findall(r'class=hnsks title="([^"]+)"', g) for g in groups]
        self.assertEqual(names[0], ["gate-red-green", "gate-pass-only"])   # catch row before its control
        self.assertEqual(names[1], ["guard-commit", "guard-commit-after-fail", "guard-commit-after-pass"])
        self.assertEqual(len(re.findall(r"hnpf hnok", h)), 10)
        self.assertEqual(len(re.findall(r"hnpf hnng", h)), 1)
        self.assertIn('class="hnskr hnng"', groups[1])
        self.assertIn("PASS 10/11", h)
        self.assertIn("차단", groups[1])
        self.assertIn("통과시킴", groups[1])

    def test_r3_side_cells(self):
        h = _js("console.log(JSON.stringify(hnSelfcheck(%s)))" % _data(_OK))
        side = re.findall(r'<div class=hnske[^>]*>([^<]*)</div>', h)
        self.assertEqual(side[1], "게이트 전 커밋: 차단 4")
        self.assertEqual(side[2], "단계 건너뛰기: 차단 2")
        self.assertEqual(side[3], "필수 게이트 건너뛰기: 차단 0")
        self.assertEqual(side[0], "잡음 1")             # fast 1 + full 0
        self.assertEqual(side[4], "유지 3 · 되돌림 1")
        self.assertNotIn("&lt;x&gt;", h)               # unknown deny codes never shown

    def test_stale_badge_and_escape(self):
        h = _js("console.log(JSON.stringify(hnSelfcheck(%s)))" % _data(dict(_OK, stale=True, head="\"><b>abcdef0123")))
        self.assertIn("다른 커밋</em>", h)
        self.assertIn("&quot;&gt;&lt;b&gt;abc", h)
        self.assertNotIn("<b>abc", h)
        self.assertIn("&lt;img onerror=1&gt; jump", h)
        self.assertNotIn("<img", h)
        self.assertNotIn("다른 커밋", _js("console.log(JSON.stringify(hnSelfcheck(%s)))" % _data(_OK)))

    def test_en_and_hnhtml(self):
        en = _js("LANG = 'en'; console.log(JSON.stringify(hnSelfcheck(%s)))" % _data(dict(_OK, stale=True)))
        for s in ("Guard self-check", "different commit", "Situation fed", "Stage jump: Blocked 2", "let through"):
            self.assertIn(s, en)
        self.assertFalse(any("가" <= ch <= "힣" for ch in en))
        d = _data(_OK)
        h = _js("HN.data[hnKey(PLS.proj)] = %s; HN.at[hnKey(PLS.proj)] = NOW; console.log(JSON.stringify(hnHtml()))" % d)
        self.assertLess(h.index("data-hnmore=read"), h.index("data-hnmore=sc"))
        self.assertLess(h.index("data-hnmore=sc"), h.index("data-hnmore=runs"))

    def test_css_wraps(self):
        with open(os.path.join(ROOT, "web", "css", "41b-harness.css"), encoding="utf-8") as f:
            css = f.read()
        self.assertIn("@media (max-width:1439px){.hnske{flex-basis:100%", css)
        self.assertIn(".hnskg{display:flex;flex-wrap:wrap", css)


if __name__ == "__main__":
    unittest.main()
