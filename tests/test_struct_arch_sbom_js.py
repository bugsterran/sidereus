"""syft/grype in the security issues window (web/js/84l6-structure-arch-sbom.js + 84l): R2 syft row «ran · N components»,
R4 grype rows beside osv-scanner with «pkg ver», R5 Maven/Gradle note texts, R6 summary (categories · severity · DB time · upgrades)."""
import json
import shutil
import unittest

import tests.test_struct_arch_checks_js as base
import tests.test_struct_arch_osv_js as osv

FNS = osv.FNS + ["archChkSbomNotes", "archChkSbomStat", "archChkDbAt", "archChkSummaryHtml"]


def run(body, lang="en"):
    old = osv.FNS
    osv.FNS = FNS
    try:
        return osv.run(body, lang)
    finally:
        osv.FNS = old


SYFT = {"id": "syft", "status": "ok", "n": {}, "components": 42, "notes": ["mvn-offline", "gradle-no-lock", "bogus", "mvn-offline"]}
GRYPE = {"id": "grype", "status": "ok", "n": {"critical": 1, "high": 1}, "db_built": "2026-11-12T03:04:05Z"}
OSV = {"id": "osv-scanner", "status": "ok", "n": {"high": 1}}
SUMMARY = {"cat": {"cve": 3, "sast": 1, "secret": 0, "config": 2}, "sev": {"critical": 1, "high": 2, "medium": 3, "low": 0},
           "db_built": "2026-11-12T03:04:05Z",
           "fixes": [{"pkg": "spring-web", "ver": "5.3.39", "to": "6.1.14", "n": 2, "sev": "critical"},
                     {"pkg": "a<b>{v}", "ver": "1.0", "to": "2.0", "n": 1, "sev": "high"},
                     {"pkg": "", "to": "1", "n": 1}, {"pkg": "x", "to": "", "n": 1}, {"pkg": "y", "to": "2", "n": 0}]}
SEC = {"commit": "abc", "at": 1700000000, "tools": [OSV, SYFT, GRYPE], "summary": SUMMARY,
       "top": [{"tool": "grype", "file": "pom.xml", "line": 1, "rule": "CVE-2024-38816", "sev": "critical", "pkg": "spring-web", "ver": "5.3.39", "fixv": "6.1.14"},
               {"tool": "osv-scanner", "file": "package-lock.json", "line": 1, "rule": "GHSA-1", "sev": "high", "pkg": "lodash"}]}


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchSbom(unittest.TestCase):
    def test_r2_r5_syft_row_text(self):
        bad = [dict(SYFT, components=None), dict(SYFT, components=1.5), dict(SYFT, components="3"), dict(SYFT, status="skipped", why="no packages"), dict(OSV, components=4)]
        r = run("console.log(JSON.stringify(" + json.dumps([SYFT, dict(SYFT, notes=None), dict(SYFT, components=0, notes=[])] + bad) + ".map(t => [archChkSbomStat(t), archChkStat(t)])));")
        self.assertEqual(r[0][0], "ran · 42 components · Maven versions not resolved (offline) · transitive dependencies not resolved")   # R2 + R5, deduped
        self.assertEqual(r[0][1], r[0][0])                                                  # archChkStat uses it for syft
        self.assertEqual(r[1][1], "ran · 42 components")
        self.assertEqual(r[2][1], "ran · 0 components")
        for x in r[3:6]:
            self.assertEqual(x, ["", "ran · 0 found"])                                       # unknown count: plain status, never «0 components»
        self.assertEqual(r[6], ["", "skipped: no packages · Maven versions not resolved (offline) · transitive dependencies not resolved"])   # notes on any status
        self.assertEqual(r[7], ["", "ran · 1 found"])                                         # only the syft row
        k = run("console.log(JSON.stringify(archChkSbomStat(" + json.dumps(SYFT) + ")));", lang="ko")
        self.assertEqual(k, "실행됨 · 구성 요소 42 · Maven 버전 확인 못 함 (오프라인) · 전이 의존성 확인 못 함")

    def test_r5_mvn_unresolved_note(self):
        rows = [dict(SYFT, notes=["mvn-unresolved"], unresolved=3), dict(SYFT, notes=["mvn-unresolved"]), dict(SYFT, notes=["mvn-unresolved"], unresolved=None),
                dict(SYFT, notes=["mvn-unresolved"], unresolved=-1), dict(SYFT, notes=[], unresolved=3)]
        r = run("console.log(JSON.stringify(" + json.dumps(rows) + ".map(archChkStat)));")
        self.assertEqual(r[0], "ran · 42 components · 3 Maven versions not resolved")
        self.assertEqual(r[1:4], ["ran · 42 components · ? Maven versions not resolved"] * 3)   # unknown count: «?», never 0
        self.assertEqual(r[4], "ran · 42 components")                                         # no note code: no text
        k = run("console.log(JSON.stringify(archChkSbomStat(" + json.dumps(rows[0]) + ")));", lang="ko")
        self.assertEqual(k, "실행됨 · 구성 요소 42 · Maven 버전 3개 미해석")

    def test_r5_skipped_gradle_row_keeps_note(self):
        rows = [{"id": "syft", "status": "skipped", "why": "no packages found", "notes": ["gradle-no-lock"]},
                {"id": "syft", "status": "fail", "why": "exit 1", "notes": ["mvn-offline"]}, {"id": "syft", "status": "skipped", "why": "x"},
                {"id": "grype", "status": "skipped", "why": "needs syft SBOM", "notes": ["gradle-no-lock"]}]
        r = run("console.log(JSON.stringify(" + json.dumps(rows) + ".map(archChkStat)));")
        self.assertEqual(r, ["skipped: no packages found · transitive dependencies not resolved", "failed: exit 1 · Maven versions not resolved (offline)",
                             "skipped: x", "skipped: needs syft SBOM"])                        # R5: build.gradle-only repo still says it; other tools never

    def test_syft_ok_alone_is_not_checked(self):
        sec = {"commit": "abc", "at": 1700000000, "top": [], "tools": [SYFT, {"id": "grype", "status": "skipped", "why": "vuln DB not available"},
                                                                        {"id": "gitleaks", "status": "missing"}]}
        r = run(base.MEMJS + "const d2 = {checks: {security: " + json.dumps(sec) + "}}; const S = {sel: {}, sev: 'all', tool: ''};"
                "const d3 = {checks: {security: " + json.dumps(dict(sec, tools=sec["tools"] + [GRYPE])) + "}};"
                "console.log(JSON.stringify([archChkTopBtn(d2, '/r'), archChkWinHtml('/r', d2, S, []), archChkTopBtn(d3, '/r')]));")
        self.assertIn(">Security not checked</button>", r[0])                                # syft lists packages, it checks nothing
        self.assertNotIn("Security issues", r[0])
        self.assertIn("No scanner ran", r[1])
        self.assertIn(">Security issues 0</button>", r[2])                                   # a real checker ok: issues count

    def test_r6_null_counts_are_unknown(self):
        s = dict(SEC, summary={"cat": {"cve": 2, "sast": None, "secret": None, "config": 0},
                               "sev": {"critical": None, "high": None, "medium": None, "low": None}, "fixes": []})
        r = run("console.log(JSON.stringify(archChkSummaryHtml(" + json.dumps(s) + ")));")
        self.assertIn(">CVE 2 · SAST ? · Secret ? · Config 0 | critical ? · high ? · medium ? · low ?</div>", r)   # null = «?», a real 0 stays 0

    def test_r4_grype_rows_beside_osv(self):
        r = run(base.MEMJS + "const d2 = {checks: {security: " + json.dumps(SEC) + "}}; ARCH.cache['/r'] = d2;"
                "const S = {sel: {}, sev: 'all', tool: ''}; const top = archChkTop(d2);"
                "console.log(JSON.stringify([archChkWinHtml('/r', d2, S, []), archChkTopBtn(d2, '/r'), archChkFixBody('/r', d2.checks, top, '/h', false), top.map(x => archChkRule(x))]));")
        h = r[0]
        live = h.split("<ol class=archckl>")[1].split("</ol>")[0]
        self.assertIn('<small title="grype">grype</small>', live)                           # R4: tool id grype
        self.assertIn("CVE-2024-38816 · spring-web 5.3.39", live)                            # version after the package
        self.assertIn('<small title="osv-scanner">osv-scanner</small>', live)                # beside osv-scanner
        self.assertIn('<option value="grype">grype</option>', h)
        self.assertIn("syft · ran · 42 components", h)                                       # scanner line
        self.assertIn("syft · ran · 42 components", r[1])                                    # badge tooltip
        self.assertIn("CVE-2024-38816 · spring-web 5.3.39 · pom.xml:1", r[2])                # relay text carries the version
        self.assertEqual(r[3][1], "GHSA-1 · lodash")                                          # no ver: unchanged

    def test_r6_summary(self):
        r = run("console.log(JSON.stringify([archChkSummaryHtml(" + json.dumps(SEC) + "), archChkSummaryHtml(" + json.dumps(SEC) + ", true)]));")
        h = r[0]
        self.assertIn('<div class="archckst cksum" role=status>CVE 3 · SAST 1 · Secret 0 · Config 2 | critical 1 · high 2 · medium 3 · low 0 | Vulnerability DB built 2026-11-12 03:04</div>', h)
        self.assertIn('<details class="ckunz cksfix" data-cksfix open><summary>Upgrades 2</summary>', h)
        self.assertIn('<li class="critical"><b class=archcks>critical</b><span>upgrade spring-web 5.3.39 to 6.1.14 resolves 2</span></li>', h)
        self.assertIn("upgrade a&lt;b&gt;{v} 1.0 to 2.0 resolves 1", h)                     # data esc'd; «{v}» in a name stays literal
        self.assertEqual(h.count("<li "), 2)                                                  # invalid fix rows dropped
        self.assertNotIn("more", h)
        self.assertIn("data-cksfix><summary>", r[1])                                          # closed state kept

    def test_r6_summary_more_and_ko(self):
        s = dict(SEC, summary=dict(SUMMARY, fixes_more=7))
        r = run("console.log(JSON.stringify([archChkSummaryHtml(" + json.dumps(s) + "), archChkSummaryHtml(" + json.dumps(dict(SEC, summary=dict(SUMMARY, fixes_more=0))) + ")]));")
        self.assertIn("</ol><div class=archckst>+7 more</div></details>", r[0])             # capped list says so
        self.assertNotIn("more", r[1])
        k = run("console.log(JSON.stringify(archChkSummaryHtml(" + json.dumps(s) + ")));", lang="ko")
        self.assertIn("CVE 3 · SAST 1 · 비밀값 0 · 설정 2", k)
        self.assertIn("취약점 DB 생성 2026-11-12 03:04", k)
        self.assertIn("spring-web 5.3.39 → 6.1.14 업그레이드로 2건 해결", k)
        self.assertIn("업그레이드 2", k)
        self.assertIn("<div class=archckst>외 7건</div>", k)                                # not the clickable «더 보기»

    def test_r6_unknown_is_not_zero(self):
        cases = [dict(SEC, summary=None), {k: v for k, v in SEC.items() if k != "summary"}, dict(SEC, summary=[1]), None,
                 dict(SEC, summary={"cat": {"cve": 1}, "sev": {}, "db_built": "1970-01-01", "fixes": "x"}),
                 dict(SEC, summary={"cat": {"cve": 1}, "sev": {"high": -1}, "db_built": 0})]
        r = run("console.log(JSON.stringify(" + json.dumps(cases) + ".map(s => archChkSummaryHtml(s))));")
        self.assertEqual(r[:4], ["", "", "", ""])                                              # old results: nothing, not zeros
        self.assertIn(">CVE 1 · SAST ? · Secret ? · Config ? | critical ? · high ? · medium ? · low ?</div>", r[4])
        self.assertNotIn("DB built", r[4])                                                     # malformed time: no line, never the epoch
        self.assertNotIn("<details", r[4])
        self.assertIn("high ?", r[5])
        self.assertNotIn("DB built", r[5])

    def test_r6_window_top_and_toggle(self):
        sfx = ("const sm = {parentNode: {open: true}}; const ev2 = {type: 'click', target: {closest: s => s === '[data-cksfix]>summary' ? sm : null, matches: () => false, dataset: {}}};")
        r = run(base.MEMJS + base.EVJS + sfx + "const d2 = {checks: {security: " + json.dumps(SEC) + "}}; ARCH.cache['/r'] = d2;"
                "ARCH_CW = {p: '/r', w: W, sel: {}, sev: 'all', tool: '', sfc: false}; const h0 = archChkWinHtml('/r', d2, ARCH_CW, []);"
                "archChkWinEv(ev2, W); const c1 = ARCH_CW.sfc, p1 = PAINTS; const h1 = archChkWinHtml('/r', d2, ARCH_CW, []);"
                "console.log(JSON.stringify([h0, c1, p1, h1]));")
        h0 = r[0]
        self.assertLess(h0.index("cksum"), h0.index("<div class=ckwf>"))                       # top: before the filter row
        self.assertLess(h0.index("</div>"), h0.index("cksum"))                                 # after the header
        self.assertIn("data-cksfix open>", h0)
        self.assertTrue(r[1])                                                                  # click on the open group records «closed»
        self.assertEqual(r[2], 0)                                                              # no repaint (native toggle)
        self.assertIn("data-cksfix><summary>", r[3])                                          # survives the next paint


if __name__ == "__main__":
    unittest.main()
