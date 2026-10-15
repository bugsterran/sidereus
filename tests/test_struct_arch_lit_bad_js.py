"""Architecture map regressions: a layer/group path-bar highlight lights its intra-layer edges without throwing, and a
map that failed schema validation (bad: true) shows the invalid-map message instead of the empty state."""
import shutil
import unittest

from tests.test_struct_arch_detail_js import run


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchLitBad(unittest.TestCase):
    def test_layer_and_group_lit_sets_with_inner_edges(self):
        # 'back' group holds srv/svc/db with edges between them: pair() must get its target set.
        r = run("const g = archLitSet(D, {layer: 'service', group: null}), b = archLitSet(D, {layer: 'api', group: 'back'});"
                "const D2 = Object.assign({}, D, {modules: D.modules.map(m => Object.assign({}, m, {layer: 'one'}))});"
                "const a = archLitSet(D2, {layer: 'one', group: 'back'});"
                "console.log(JSON.stringify([[...g.n], [...b.n], [...a.n].sort(), [...a.e].sort()]));")
        self.assertEqual(r[0], ["m2"])
        self.assertEqual(r[1], ["m1"])
        self.assertEqual(r[2], ["m1", "m2", "m3"])
        self.assertEqual(r[3], sorted(["m1\u0001m2", "m2\u0001m1", "m2\u0001m3", "m3\u0001m2"]))

    def test_bad_map_shows_invalid_not_empty(self):
        r = run("const box = {innerHTML: '', querySelector(){ return null; }}; const out = [];"
                "for(const d of [{ok: true, empty: true, bad: true, modules: [], edges: []}, {ok: true, empty: true, modules: [], edges: []}]){"
                " ARCH.cache['/r'] = d; box._arsig = ''; archPaint(box, head); out.push(box.innerHTML); }"
                "console.log(JSON.stringify(out));")
        self.assertIn("저장된 구조도가 올바르지 않습니다", r[0])
        self.assertNotIn("아직 아키텍처 구조도가 없습니다", r[0])
        self.assertIn("data-arq", r[0])   # request button still offered
        self.assertIn("아직 아키텍처 구조도가 없습니다", r[1])
        self.assertNotIn("저장된 구조도가 올바르지 않습니다", r[1])


if __name__ == "__main__":
    unittest.main()
