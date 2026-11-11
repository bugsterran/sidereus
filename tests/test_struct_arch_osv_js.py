"""osv reachability verdicts in the security issues window (web/js/84l5-structure-arch-osv.js + 84l):
R1 «Unused (verified)» chip with rule + date, R2 «Invalidated» chip with the hit file:line (code popup button), R3 «Unjudged» chip +
header hint count, R4 unused rows collapsed by default (count only, never selected); old data without `use` shows no chip."""
import json
import shutil
import subprocess
import unittest

import tests.test_struct_arch_checks_js as base
from tests._load import js_fn
from tests._node import node_e

FNS = base.FNS + ["archChkUse", "archChkUseChip", "archChkUnusedSplit", "archChkOsvHint"]


def run(body, lang="en"):
    pre = base.PRE if lang == "ko" else base.PRE.replace("let LANG = 'ko';", "let LANG = 'en';", 1)
    js = "process.env.TZ = 'UTC';\n" + pre + "\n" + "\n".join(js_fn(n) for n in FNS) + "\n(async () => {\n" + body + "\n})().catch(e => { console.error(e); process.exit(1); });"
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


def _it(n, use=None, sev="high"):
    x = {"tool": "osv-scanner", "file": "package-lock.json", "line": n, "rule": "GHSA-%d" % n, "sev": sev, "pkg": "p%d" % n}
    if use is not None:
        x["use"] = use
    return x


UN = {"s": "unused", "r": "no-<import>", "at": "2026-11-10"}
USED = {"s": "used", "r": "imp<x>", "at": "2026-11-09", "hf": "src/a/<b>.js", "hl": 12}
NONE = {"s": "none"}
SEC = {"commit": "abc", "at": 1700000000, "osv_use": {"unused": 2, "used": 1, "none": 1},
       "tools": [{"id": "osv-scanner", "status": "ok", "n": {"high": 5}}],
       "top": [_it(1, UN), _it(2, USED), _it(3, NONE), _it(4), _it(5, dict(UN, r="r2"))]}


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchOsv(unittest.TestCase):
    def test_r1_r2_r3_chips(self):
        r = run("console.log(JSON.stringify(" + json.dumps([UN, USED, NONE]) + ".map(u => archChkUseChip({use: u}))"
                ".concat([archChkUseChip({}), archChkUseChip({use: {s: 'bogus'}}), archChkUseChip({use: {s: 'used'}}), archChkUseChip({use: {s: 'unused', at: 'x<y'}})])));")
        self.assertIn('<b class="ckuc ckuc-un">Unused (verified)</b>', r[0])               # R1
        self.assertIn("no-&lt;import&gt; · judged 2026-11-10", r[0])                       # R1: rule + date, escaped data
        self.assertNotIn("<import>", r[0])
        self.assertIn('<b class="ckuc ckuc-used">Invalidated</b>', r[1])                   # R2
        self.assertIn('data-ckv data-af="src/a/&lt;b&gt;.js" data-al="12"', r[1])          # R2: hit opens the code popup
        self.assertIn("src/<wbr>a/<wbr>&lt;b&gt;.js<span class=archevl>:12</span>", r[1])
        self.assertEqual(r[2], '<span class=ckuse><b class="ckuc ckuc-none">Unjudged</b></span>')   # R3
        self.assertEqual(r[3:5], ["", ""])                                                 # old data / unknown state: no chip
        self.assertNotIn("data-ckv", r[5])                                                  # used without a hit file: chip only
        self.assertNotIn("x&lt;y", r[6])                                                    # malformed date dropped

    def test_r1_ko(self):
        r = run("console.log(JSON.stringify([archChkUseChip({use: " + json.dumps(UN) + "}), archChkOsvHint({osv_use: {none: 3}})]));", lang="ko")
        self.assertIn("미사용 (검증됨)", r[0])
        self.assertIn("2026-11-10 판정", r[0])
        self.assertIn("미판정 3 · osv-triage 파이프라인을 실행하세요", r[1])

    def test_r3_hint_count(self):
        r = run("console.log(JSON.stringify([archChkOsvHint({osv_use: {unused: 2, used: 1, none: 4}}), archChkOsvHint({osv_use: {none: 0}}), archChkOsvHint({}),"
                "archChkOsvHint(null), archChkOsvHint({osv_use: {none: '<b>'}}), archChkOsvHint({osv_use: {none: 1.5}})]));")
        self.assertEqual(r[0], "<span class=ckosvh>Unjudged 4 · run the osv-triage pipeline</span>")
        self.assertEqual(r[1:], [""] * 5)                                                   # missing / zero / bad = nothing

    def test_r4_window_collapsed_and_select_all(self):
        r = run(base.MEMJS + base.EVJS + "const d2 = {checks: {security: " + json.dumps(SEC) + "}}; ARCH.cache['/r'] = d2;"
                "ARCH_CW = {p: '/r', w: W, sel: {}, sev: 'all', tool: ''}; const h0 = archChkWinHtml('/r', d2, ARCH_CW, []);"
                "archChkWinEv(ev('change', {ckall: ''}, {checked: true}), W);"
                "const sel = Object.keys(ARCH_CW.sel); ARCH_CW.sel[archChkKey(d2.checks.security.top[0])] = 1;"   # a stale key of a collapsed row
                "const picked = archChkSel(d2, ARCH_CW.sel, ARCH_CW, []).map(x => x.line); ARCH_CW.unz = true;"
                "console.log(JSON.stringify([h0, sel.length, picked, archChkWinHtml('/r', d2, ARCH_CW, []), archChkTopBtn(d2, '/r')]));")
        h = r[0]
        live = h.split("<ol class=archckl>")[1].split("</ol>")[0]
        self.assertEqual(live.count("<li "), 3)                                             # R4: unused rows are not in the live list
        self.assertNotIn("GHSA-1", live)
        self.assertIn('<details class=ckunz data-ckunused><summary>Unused (verified) 2</summary>', h)   # closed, count shown
        self.assertNotIn("data-ckunused open", h)
        un = h.split("data-ckunused>")[1].split("</details>")[0]
        self.assertNotIn("data-ckk", un)                                                    # no checkbox in the collapsed group
        self.assertIn("Top issues 3", h)
        self.assertIn("high 3", h)                                                          # counts: 5 scanner total minus 2 unused
        self.assertIn("Unjudged 1 · run the osv-triage pipeline", h)                       # R3 header hint
        self.assertIn("ckuc-used", live)
        self.assertIn("ckuc-none", live)
        self.assertEqual(r[1], 3)                                                           # select-all skips unused
        self.assertEqual(sorted(r[2]), [2, 3, 4])                                           # request fix never sends a collapsed row
        self.assertIn("data-ckunused open>", r[3])                                          # ARCH_CW.unz keeps it open
        self.assertIn(">Security issues 3</button>", r[4])

    def test_r4_badge_not_red_when_all_unused(self):
        sec = dict(SEC, tools=[{"id": "osv-scanner", "status": "ok", "n": {"critical": 1, "high": 1}}],
                   top=[_it(1, UN, "critical"), _it(2, dict(UN, r="r2"))])
        r = run(base.MEMJS + "console.log(JSON.stringify([archChkTopBtn({checks: {security: " + json.dumps(sec) + "}}, '/r'),"
                "archChkTopBtn({checks: {security: " + json.dumps(dict(sec, top=[_it(1, None, "critical"), _it(2)])) + "}}, '/r')]));")
        self.assertIn("strbg-archckiw", r[0])                                               # R4: all crit/high unused -> amber
        self.assertIn(">Security issues 0</button>", r[0])
        self.assertNotIn("archckiw", r[1])                                                  # same items without verdicts stay red

    def test_old_data_unchanged(self):
        old = dict(SEC, top=[_it(1), _it(2)])
        old.pop("osv_use")
        r = run("const S = {sel: {}, sev: 'all', tool: ''}; console.log(JSON.stringify(archChkWinHtml('/r', {checks: {security: " + json.dumps(old) + "}}, S, [])));")
        self.assertNotIn("ckuse", r)
        self.assertNotIn("data-ckunused", r)
        self.assertNotIn("Unjudged", r)
        self.assertIn("Top issues 2", r)


if __name__ == "__main__":
    unittest.main()
