"""The header KPI strip is gone (R1/R4): no #kn host in the page skeleton and no web/js code that builds or styles it."""
import glob
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class KpiStripRemoved(unittest.TestCase):
    def test_no_host_in_index(self):
        h = read(os.path.join(ROOT, "web", "index.html"))
        self.assertNotIn("id=kn>", h)
        self.assertNotIn('id="kn"', h)
        self.assertIn("id=hlb", h)       # the neighbour slot stays

    def test_no_strip_code_in_js(self):
        hits = []
        for p in sorted(glob.glob(os.path.join(ROOT, "web", "js", "*.js"))):
            s = read(p)
            for needle in ("buildKn", "#kn ", "'knpop'", "getElementById('kn')"):   # code only; prose comments may still name it
                if needle in s:
                    hits.append("%s: %s" % (os.path.basename(p), needle))
        self.assertEqual(hits, [])

    def test_strip_files_deleted(self):
        for n in ("56-kpi-cards.js", "56b-kpi-fillers.js"):
            self.assertFalse(os.path.exists(os.path.join(ROOT, "web", "js", n)), n)

    def test_shared_helpers_kept(self):
        js = "\n".join(read(p) for p in glob.glob(os.path.join(ROOT, "web", "js", "*.js")))
        for fn in ("function knQ(", "function knUnc(", "function sesCount("):
            self.assertEqual(js.count(fn), 1, fn)
        self.assertEqual(js.count("let EXTU = "), 1)


if __name__ == "__main__":
    unittest.main()
