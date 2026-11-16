"""84k flow steps without a current verdict (sidereus/arch_flow.py why «unchecked»: stale VERIFIER_V or no flows.verify.json)
read as unknown, not failed: no ✗, no «Check failed»/archbad, no red .bad rate, no .archfx. A real failure (noroute) stays red,
and every tooltip shows a reason label, never the raw why code."""
import json
import shutil
import unittest

from tests.test_struct_arch_js import run_flow


def step(a, b, ok, why):
    return {"from": a, "to": b, "label": a + b, "ok": ok, "est": 0, "why": why, "evidence": {"file": a + ".py", "line": 1, "symbol": "f"}}


UNK = {"id": "fresh", "name": "Fresh", "ok": False, "entry": {"kind": "http", "label": "GET /x"},
       "steps": [step("a", "b", False, "unchecked"), step("b", "c", False, "unchecked")]}
MIX = {"id": "mix", "name": "Mix", "ok": False, "entry": {"kind": "job", "label": "cron"},
       "steps": [step("a", "b", True, None), step("b", "c", False, "unchecked")]}
BAD = {"id": "real", "name": "Real", "ok": False, "entry": {"kind": "http", "label": "POST /y"},
       "steps": [step("a", "b", False, "noroute"), step("b", "c", False, "unchecked")]}
FLS = [UNK, MIX, BAD]
FAKE_SVG = ("const mk = () => { const g = { kids: [], cls: [], classList: { add(c){ g.cls.push(c); } }, insertBefore(t){ g.kids.unshift(t); } }; return g; };"
            "const G = {'1': mk(), '2': mk()}, svg = { querySelector(s){ const m = s.match(/data-i=\"(\\d+)\"/); return m ? G[m[1]] || null : null; } };")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchFlowUnchecked(unittest.TestCase):
    def render(self, expr):
        return run_flow("const F = " + json.dumps(FLS) + ";" + FAKE_SVG + "console.log(JSON.stringify(" + expr + "));")

    def test_picker_marks_unchecked_neutral(self):
        h = self.render("archFlowPick(F, '')")
        self.assertIn("? Fresh", h)
        self.assertIn("? Mix", h)
        self.assertIn("✗ Real", h)                              # a real failure keeps ✗
        self.assertNotIn("✗ Fresh", h)
        self.assertNotIn("✗ Mix", h)

    def test_rows_badge_and_tooltip(self):
        r = self.render("[archFlowRow(F[0].steps[0], {}, 0), archFlowRow(F[2].steps[0], {}, 0), archFlowRow(F[1].steps[0], {}, 0)]")
        unk, bad, ok = r
        self.assertNotIn("archbad", unk)
        self.assertNotIn("검증 실패", unk)
        self.assertNotIn(" bad", unk)
        self.assertIn("archunk", unk)
        self.assertIn("미검증", unk)
        self.assertIn('title="아직 검증 전"', unk)
        self.assertNotIn("unchecked", unk)                      # no raw code in the tooltip
        self.assertIn("archbad", bad)                            # noroute stays red exactly as before
        self.assertIn("검증 실패", bad)
        self.assertIn('class="arche archfs bad"', bad)
        self.assertIn("증명 안 됨: 대상에 맞는 라우트 없음", bad)
        self.assertNotIn("noroute", bad)
        self.assertNotIn("archbg", ok)

    def test_body_rate(self):
        r = self.render("[0, 1, 2].map(i => archFlowBody(F, i, {}).match(/<span class=\"archfr[^\"]*\">[^<]*/)[0])")
        self.assertEqual(r[0], '<span class="archfr unk">미검증')            # all unchecked: not «0/2 proven», not red
        self.assertEqual(r[1], '<span class="archfr unk">단계 1/2 증명 · 미검증 1')
        self.assertEqual(r[2], '<span class="archfr bad">단계 0/2 증명 · 미검증 1')

    def test_mark_no_archfx_for_unchecked(self):
        r = self.render("[archFlowMark(svg, F[0]), G['1'].cls, G['2'].cls, G['1'].kids.map(k => k.textContent),"
                        " (G['1'].cls = [], G['1'].kids = [], G['2'].cls = [], archFlowMark(svg, F[2])), G['1'].cls, G['2'].cls, G['1'].kids.map(k => k.textContent)]")
        self.assertEqual(r[0:3], [0, [], []])
        self.assertEqual(r[3], ["아직 검증 전"])
        self.assertEqual(r[4:7], [1, ["archfx"], []])           # only the noroute step goes red
        self.assertEqual(r[7], ["증명 안 됨: 대상에 맞는 라우트 없음"])

    def test_unknown_code_never_raw(self):
        r = self.render("[archFlowTip({ok: false, why: '<zz>'}), archFlowTip({ok: false}), archFlowWhy('constructor')]")
        self.assertEqual(r, ["증명 안 됨: 알 수 없는 사유"] * 2 + ["알 수 없는 사유"])


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchMapUnchecked(unittest.TestCase):
    """84j3: lit map edges and the «Flows through here» list follow the same step verdicts as 84k."""
    def test_lit_edges_and_flow_list(self):
        from tests.test_struct_arch_detail_js import run
        fl = [{"id": "u", "name": "Unk", "ok": False, "steps": [step("web", "srv", False, "unchecked"), step("srv", "svc", True, None)]},
              {"id": "r", "name": "Real", "ok": False, "steps": [step("srv", "svc", False, "noroute"), step("svc", "db", False, "unchecked")]}]
        r = run("D.flows = " + json.dumps(fl) + "; const svg = fakeSvg(['m0', 'm1', 'm2', 'm3'], [['m0', 'm1'], ['m1', 'm2'], ['m2', 'm3']]);"
                "const fx = q => { archLitPaint(svg, archLitSet(D, q)); return svg.es.filter(e => e.classList.contains('archfx')).map(e => e.dataset.f + '>' + e.dataset.t); };"
                "console.log(JSON.stringify([fx({flow: 'u'}), fx({flow: 'r'}), archDetHtml(D, 'srv', NAMES, {}, {})]));")
        self.assertEqual(r[0], [])                              # unchecked step: lit, not red
        self.assertEqual(r[1], ["m1>m2"])                       # noroute stays red; its unchecked neighbour does not
        self.assertIn("? Unk", r[2])
        self.assertIn("✗ Real", r[2])
        self.assertNotIn("✗ Unk", r[2])


if __name__ == "__main__":
    unittest.main()
