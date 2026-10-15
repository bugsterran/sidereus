"""84j architecture view on a map.json v2 load() result: entry/store modules and serve/read/write/event edges render
without throwing (overview source, ranks, edge rows, full paint)."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus
from tests.test_archmap_v2 import C1, v2_map
from tests.test_struct_arch_js import run

AM = sidereus("arch_map")
AV = sidereus("arch_verify")


def v2_load():
    """arch_map.load() of a stored v2 map (temp store, allow list and HEAD patched; no git)."""
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-archv2js-"))
    try:
        repo, store = os.path.join(tmp, "repo"), os.path.join(tmp, "store")
        os.makedirs(repo)
        m = v2_map(repo, C1)
        d = os.path.join(store, AV.repo_key(repo), C1)
        os.makedirs(d)
        v = {"commit": C1, "total": 5, "passed": 5, "rate": 1.0, "edges": [{"i": i, "ok": True, "why": None} for i in range(5)]}
        for name, data in (("map.json", m), ("verify.json", v)):
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                json.dump(data, f)
        with mock.patch.object(AM, "ARCH_DIR", store), \
                mock.patch.object(AM, "_struct_src_root", lambda p: os.path.realpath(p) if p == repo else ""), \
                mock.patch.object(AM, "head_of", lambda r: C1), mock.patch.object(AM, "behind_of", lambda r, c: 0):
            return AM.load(repo)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class StructArchV2(unittest.TestCase):
    def test_v2_renders(self):
        d = v2_load()
        self.assertEqual((d["v"], d.get("bad")), (2, None))
        r = run("const d = " + json.dumps(d) + ", N = {}; d.modules.forEach(m => { N[m.id] = m.name; });"
                "const src = archSrc(d.modules, d.edges, false, '', false), sel = archSrc(d.modules, d.edges, false, 'app', false);"
                "const ps = archPairs(d.modules, d.edges, false), rk = archRanks(d.modules.map(m => m.id), ps);"
                "const rows = d.edges.map((e, i) => archEdgeRow(e, N, i, true, 'out'));"
                "globalThis.archMmd = s => '<M/>'; ARCH.cache['/r'] = d; const box = {innerHTML: '', querySelector(){ return null; }}; archPaint(box, head);"
                "const band = archBandSrc(d.modules, d.edges, false, false, d.groups);"
                "console.log(JSON.stringify([src, sel, rk, rows, archBarHtml(d.modules, d.edges, '', false, false, ''), box.innerHTML, band]));")
        src, sel, rk, rows, bar, html, band = r
        self.assertEqual(d["edges"][3]["est"], 1)         # event = estimated (merged with the app->lib call, drawn solid)
        self.assertIn('m0["HTTP"]', src)                  # entry/store draw as plain boxes, outside the External group
        self.assertIn("m0 --> m1", src)
        self.assertIn("m1", sel)
        self.assertEqual(set(rk), {"http", "app", "lib", "pg"})
        self.assertTrue(any("serve" in x for x in rows))
        self.assertIn("archel-list", html)
        self.assertTrue(bar)
        # R1: a layered v2 map paints the banded overview: entry band first, data band last, no «No layers» notice
        self.assertLess(band.index("subgraph L0["), band.index("subgraph L3["))
        self.assertLess(band.index("subgraph L3["), band.index("subgraph L7["))
        self.assertIn('subgraph G0["I/O"]', band)
        self.assertNotIn("archnol", html)
        self.assertIn("data-k=\"read\"", html)          # legend gains the edge-kind swatches (R3)


if __name__ == "__main__":
    unittest.main()
