"""Status bar SB_STEPS (60-statusbar.js): ext «Today» (step 4) is dropped only after limit % (5) and reset times (6)."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e
from tests.test_saver_quota_js import jconst
from tests.test_sbar_fit import FAKE

# Reuse the fake bar; widths: without 1,2,3 = 1148, without 5 = 968, without 6 = 878, without 4 = 836.
CASES = """
const res = {};
for(const [name, cw] of [['keepToday', 900], ['dropToday', 850]]){
  const el = bar(cw, P, 8); sbFit(el); res[name] = [...new Set(el.hidden())];
}
// With a saver secondary (.sbd7, 30px): without 6 = 908, still 7px over ⇒ 7 goes, «Today» (4) stays.
const el7 = bar(900, P.concat([[7, 30]]), 8); sbFit(el7); res.saverFirst = [...new Set(el7.hidden())];
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


if __name__ == "__main__":
    unittest.main()
