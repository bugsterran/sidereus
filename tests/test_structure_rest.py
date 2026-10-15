"""Omitted functions of a capped area are summarised per file in `rest` (sum invariant, cap folding)."""
import unittest

from tests._load import sidereus

SC = sidereus("structure_scan")


def _fns(spec):
    # spec: [(file, count, lines_each)] -> function rows as _struct_group expects them
    out = []
    for file, cnt, ln in spec:
        for i in range(cnt):
            out.append({"name": "f%d_%s" % (i, file), "lang": "py", "file": file, "line": i + 1, "lines": ln})
    return out


class RestTest(unittest.TestCase):
    def _area(self, fns, maxf):
        g = SC._struct_group(0, fns, False, {}, maxf=maxf)
        self.assertEqual(len(g["areas"]), 1)
        return g["areas"][0]

    def test_no_rest_under_cap(self):
        a = self._area(_fns([("a/x.py", 3, 5)]), maxf=10)
        self.assertNotIn("more", a)
        self.assertNotIn("rest", a)

    def test_sum_equals_omitted_lines(self):
        fns = _fns([("a/big.py", 5, 50), ("a/x.py", 4, 3), ("a/y.py", 2, 7)])
        a = self._area(fns, maxf=5)
        kept = sum(f["lines"] for f in a["fns"])
        self.assertEqual(sum(r["lines"] for r in a["rest"]), a["lines"] - kept)
        self.assertEqual(sum(r["n"] for r in a["rest"]), a["more"])
        self.assertEqual([r["file"] for r in a["rest"]], ["a/y.py", "a/x.py"])   # lines desc
        self.assertEqual(a["rest"][0], {"file": "a/y.py", "n": 2, "lines": 14})

    def test_cap_folds_tail_into_etc(self):
        spec = [("a/big.py", 2, 100)] + [("a/f%02d.py" % i, 1, 20 - i) for i in range(6)]
        fns = _fns(spec)
        g = SC._struct_group(0, fns, False, {}, maxf=2)
        a = g["areas"][0]
        rest = SC._struct_rest(sorted(fns, key=lambda r: -r["lines"])[2:], cap=3)
        self.assertEqual(len(rest), 4)
        self.assertTrue(rest[-1]["etc"])
        self.assertEqual(rest[-1]["files"], 3)
        self.assertEqual(sum(r["lines"] for r in rest), sum(r["lines"] for r in a["rest"]))
        self.assertEqual(sum(r["n"] for r in rest), a["more"])
        self.assertTrue(all(not r.get("etc") for r in a["rest"]))   # 6 files fit the default cap (40)

    def test_drilldown_never_folds_into_etc(self):
        # «기타 N개 파일» opens via full=1 (maxf raised); folding again there left a cell that did nothing.
        nfile = SC.STRUCT_REST_FILES + 5
        spec = [("a/f%03d.py" % i, 1, 10) for i in range(SC.STRUCT_FULL_FNS + nfile)]
        full = self._area(_fns(spec), maxf=SC.STRUCT_FULL_FNS)
        self.assertEqual(len(full["rest"]), nfile)
        self.assertTrue(all(not r.get("etc") for r in full["rest"]))
        self.assertEqual(sum(r["n"] for r in full["rest"]), full["more"])
        top = self._area(_fns(spec), maxf=SC.STRUCT_MAX_FNS)      # full screen keeps the cap
        self.assertTrue(top["rest"][-1]["etc"])
        self.assertEqual(len(top["rest"]), SC.STRUCT_REST_FILES + 1)


if __name__ == "__main__":
    unittest.main()
