"""CLK (web/js/05-i18n.js): en caches one Intl formatter and equals the uncached call; ko is built from I18N (no ko-KR locale data). TZ=UTC."""
import json
import os
import shutil
import subprocess
import unittest

from tests.test_saver_quota_js import i18n
from tests._node import node_e


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ClkCache(unittest.TestCase):
    def test_same_as_uncached_ko_en(self):
        js = "var document = {getElementById: () => null, documentElement: null};\n" + i18n() + r"""
const ref = d => d.toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit'});
const bad = [], ko = [];
for(const l of ['ko', 'en', 'ko', 'en']){          // switching back and forth keeps each language's output
  LANG = l;
  for(const t of [0, 1700000000000, 1700040000000, 1759900000000, 1759943999000]){
    if(l === 'en' && CLK(new Date(t)) !== ref(new Date(t))) bad.push(t + ' ' + CLK(new Date(t)));
    if(l === 'ko') ko.push(CLK(new Date(t)));
  }
}
process.stdout.write(JSON.stringify({bad: bad, ko: ko.slice(0, 5), keys: Object.keys(CLK.fmt).sort(), inv: CLK(new Date(NaN))}));"""
        r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["bad"], [])
        self.assertEqual(out["ko"], ["오전 12:00", "오후 10:13", "오전 09:20", "오전 05:06", "오후 05:19"])
        self.assertEqual(out["keys"], ["en"])
        self.assertEqual(out["inv"], "Invalid Date")


if __name__ == "__main__":
    unittest.main()
