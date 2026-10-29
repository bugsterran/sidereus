"""Pipelines canvas row height (web/js/48d-pipeline-canvas.js plCvNeed): follows the graph, capped at 62vh.

The fixed 62vh row pushed the stage panel below the fold at 1440x900. Pure function run under node."""
import json
import os
import unittest

from tests._load import ROOT, js_fn
from tests.test_pipeline_graph import P, _js

FNS = "\n".join(js_fn(f) for f in ("plZFloor", "plFitRaw", "plCvNeed"))


def src(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class CanvasHeight(unittest.TestCase):
    def need(self, body):
        return _js(FNS + "\n" + body)

    def test_one_row_chain_is_short(self):
        # demo chain (5 stages, 2 loop-backs) on one row, 1100px canvas, 900px window
        out = self.need("const G = plgFrom(%s); plgLayout(G, 28, 5); console.log(JSON.stringify(plCvNeed(G, 1100, 900)));" % json.dumps(P))
        self.assertLess(out, 0.62 * 900)
        self.assertGreaterEqual(out, 200)

    def test_tall_graph_capped(self):
        mk = "plgFrom({name: 'x', defaults: {model: 'inherit', retry: 0}, stages: Array.from({length: 7}, (_, i) => ({title: 's' + i, agent: 'a'}))})"
        out = self.need("const G = %s; plgLayout(G, 28, 1); console.log(JSON.stringify([plCvNeed(G, 1100, 900), plCvNeed(G, 0, 900), plCvNeed({nodes: [], loops: []}, 1100, 900)]));" % mk)
        self.assertEqual(out, [558, 558, 200])

    def test_wired_into_fit_and_css(self):
        js = src("web/js/48d-pipeline-canvas.js")
        self.assertIn("plCvNeed(E.G, cv.clientWidth, innerHeight)", js)
        self.assertIn("placeholder=\"' + esc(T('Stage name')) + '\"", js)
        self.assertIn("var(--plcvh,", src("web/css/43-pipeline.css"))


if __name__ == "__main__":
    unittest.main()
