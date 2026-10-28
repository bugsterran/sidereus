"""trivy base images in the security issues window (web/js/84l3-structure-arch-images.js): per-target group with fixable /
waiting counts, failure reason instead of a clean row, escaping, `id target` scanner labels, «Include images» toggle."""
import json
import shutil
import unittest

from tests.test_struct_arch_checks_js import EVJS, run

SEC = {"commit": "abc", "at": 1700000000, "top": [],
       "tools": [{"id": "trivy-config", "status": "ok", "n": {}},
                 {"id": "trivy-image", "status": "ok", "target": "py<x>:3.9", "fixable": 3, "waiting": 2, "n": {"high": 3}},
                 {"id": "trivy-image", "status": "ok", "target": "alpine:3.20", "fixable": 0, "waiting": 0, "n": {}},
                 {"id": "trivy-image", "status": "fail", "why": "docker login ghcr.io needed", "target": "ghcr.io/a/b:1", "n": {}},
                 {"id": "trivy-image", "status": "skipped", "why": "skipped — add --images", "n": {}}]}


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchImages(unittest.TestCase):
    def test_groups_per_target(self):
        r = run("const s = " + json.dumps(SEC) + "; console.log(JSON.stringify([archChkImgHtml(s), archChkImgHtml({tools: [s.tools[0], s.tools[4]]}), archChkImgHtml(null)]));", lang="en")
        h = r[0]
        self.assertEqual(h.count("<li>"), 3)                               # the untargeted skipped row stays in the state line only
        self.assertIn("<code title=\"py&lt;x&gt;:3.9\">py&lt;x&gt;:3.9</code>", h)   # target is tool output: escaped
        self.assertNotIn("py<x>", h)
        self.assertIn("fixable high/critical 3 → Replace base image", h)
        self.assertIn("waiting 2", h)
        self.assertIn("No fixable high/critical", h)                       # alpine: ran clean
        self.assertIn("failed: docker login ghcr.io needed", h)            # access failure is a reason, never clean
        self.assertEqual(h.split("ghcr.io/a/b:1</code>")[1].split("</li>")[0].count("No fixable"), 0)
        self.assertEqual([r[1], r[2]], ["", ""])

    def test_korean_and_rule_image_count(self):
        r = run("console.log(JSON.stringify([archChkImgHtml(" + json.dumps(SEC) + "), archChkRule({rule: 'CVE-1', pkg: 'openssl', imgs: 2}), archChkRule({rule: 'CVE-1', imgs: 1}),"
                "archChkTid({id: 'trivy-image', target: 'a<b>'}), archChkTid({id: 'gitleaks'})]));")
        self.assertIn("베이스 이미지 교체", r[0])
        self.assertEqual(r[1], "CVE-1 · openssl · 이미지 2개")
        self.assertEqual(r[2], "CVE-1")                                    # one image: no count
        self.assertEqual(r[3:], ["trivy-image a<b>", "gitleaks"])          # raw: callers esc()

    def test_window_state_line_and_group(self):
        r = run("const d = {checks: {security: " + json.dumps(SEC) + "}}; console.log(JSON.stringify(archChkWinHtml('/r', d, {sel: {}, sev: 'all', tool: ''}, [])));", lang="en")
        self.assertIn("trivy-image py&lt;x&gt;:3.9 · ran · 3 found", r)
        self.assertIn("trivy-image ghcr.io/a/b:1 · failed: docker login ghcr.io needed", r)
        self.assertIn("<div class=ckimgs", r)

    def test_image_gap_line(self):
        # Gap line: missing trivy and untick «Include images» are named in the window and the badge tip; no trivy rows = no line.
        miss = {"tools": [{"id": "gitleaks", "status": "ok", "n": {}},
                          {"id": "trivy-config", "status": "missing", "why": "install: brew install trivy", "n": {}},
                          {"id": "trivy-image", "status": "missing", "why": "install: brew install trivy", "n": {}}], "top": []}
        skip = {"tools": [{"id": "trivy-config", "status": "ok", "n": {}}, SEC["tools"][4]], "top": []}
        none = {"tools": [{"id": "gitleaks", "status": "ok", "n": {}}], "top": []}
        arg = {"tools": [{"id": "trivy-config", "status": "ok", "n": {}},
                         {"id": "trivy-image", "status": "skipped", "why": "FROM uses a build ARG", "n": {}}], "top": []}
        r = run("const W = s => archChkWinHtml('/r', {checks: {security: s}}, {sel: {}, sev: 'all', tool: ''}, []);"
                "console.log(JSON.stringify([archChkImgGap(" + json.dumps(miss) + "), archChkImgGap(" + json.dumps(skip) + "), archChkImgGap(" + json.dumps(none) + "),"
                " archChkImgGap(" + json.dumps(SEC) + "), W(" + json.dumps(miss) + "), W(" + json.dumps(none) + "), archChkTopBtn({checks: {security: " + json.dumps(miss) + "}}, '/r'),"
                " archChkImgGap(" + json.dumps(arg) + ")]));", lang="en")
        self.assertEqual(r[0], "Container images not scanned — trivy is not installed")
        self.assertIn("tick «Include images»", r[1])
        self.assertEqual(r[2], "")                                         # no Dockerfile in the repo: no trivy rows, no nag
        self.assertEqual(r[3], "")                                         # images scanned (one untargeted skip row is not a gap)
        self.assertIn("archckgap", r[4])
        self.assertNotIn("archckgap", r[5])
        self.assertIn("⚠ Container images not scanned", r[6])             # badge tooltip
        self.assertEqual(r[7], "")                                         # ticked, but FROM is an ARG: not the «tick the box» gap

    def test_checkbox_toggles_run_img(self):
        r = run(EVJS + "ARCH_CW = {p: '/r', w: W, sel: {}, run: {sid: 'a', busy: false, again: true}};"
                "const e = ev('change', {ckimg: ''}); e.target.checked = true; archChkWinEv(e, W); const a = ARCH_CW.run.img, g = ARCH_CW.run.again;"
                "e.target.checked = false; archChkWinEv(e, W);"
                "console.log(JSON.stringify([a, g, ARCH_CW.run.img, PAINTS, POSTS]));")
        self.assertEqual(r, [True, False, False, 2, []])                   # view state only: nothing sent


if __name__ == "__main__":
    unittest.main()
