"""Status bar SB_STEPS (60-statusbar.js): ext «Today» (step 4) is dropped only after limit % (5), reset times (6),
saver secondary (7) and ext cost / 7d used (8)."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e
from tests.test_saver_quota_js import jconst
from tests.test_sbar_fit import FAKE

# Reuse the fake bar; widths: without 1,2,3 = 1148, without 5 = 968, without 6 = 878, without 4 = 836 (no padding-squeeze step, the bar padding stays, so «Today» stays only from ~950).
CASES = """
const res = {};
for(const [name, cw] of [['keepToday', 950], ['dropToday', 850]]){
  const el = bar(cw, P, 8); sbFit(el); res[name] = [...new Set(el.hidden())];
}
// With a saver secondary (.sbd7, 30px): at 960 still over after 6 ⇒ 7 goes, «Today» (4) stays.
const el7 = bar(960, P.concat([[7, 30]]), 8); sbFit(el7); res.saverFirst = [...new Set(el7.hidden())];
// 900 with goal pill + 3 ext token+cost segments: 907 after step 7 (63 px over 844) ⇒ 8 (3 costs + 7d used, 145) clears it.
const P8 = [[0, 699], [1, 100], [5, 50], [6, 40], [7, 30], [4, 21], [4, 21], [4, 21], [8, 35], [8, 35], [8, 35], [8, 40]];
const el8 = bar(844, P8, 0); sbFit(el8); res.costFirst = [...new Set(el8.hidden())];
process.stdout.write(JSON.stringify(res));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SbStepsOrder(unittest.TestCase):
    def test_today_after_reset_times(self):
        fake = FAKE.replace("process.stdout.write(JSON.stringify(out));", "")
        src = jconst("SB_STEPS") + "\n" + js_fn("sbFit") + "\n" + fake + CASES
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        o = json.loads(r.stdout)
        self.assertEqual(o["keepToday"], [1, 2, 3, 5, 6])
        self.assertEqual(sorted(o["dropToday"]), [1, 2, 3, 4, 5, 6])
        self.assertEqual(sorted(o["saverFirst"]), [1, 2, 3, 5, 6, 7])
        self.assertEqual(sorted(o["costFirst"]), [1, 5, 6, 7, 8])


class SbStep8Tags(unittest.TestCase):
    def test_8_before_4(self):
        steps = json.loads(jconst("SB_STEPS").split("=", 1)[1].strip().rstrip(";").replace("'", '"'))
        self.assertLess(steps.index(8), steps.index(4))

    def test_ext_cost_tagged(self):
        self.assertIn("<small class=sbd8>· ' + esc(extCostStr(e.cost))", js_fn("sbExtSeg"))

    def test_used_7d_only(self):
        # 5h keeps its used: only the 7d branch wraps it in .sbd8.
        self.assertIn("u && k === '7d' ? '<span class=sbd8>' + u + '</span>' : u", js_fn("buildSbar"))


if __name__ == "__main__":
    unittest.main()
