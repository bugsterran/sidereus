"""ageU (55-saver-quota.js) replaced four hand-rolled data-age spans in burn/quota rows — outputs must match the old code byte for byte."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

# Old expressions, verbatim from 57-burn.js / 55-saver-quota.js before the change (reference only).
OLD = r"""
// Legacy U() with Korean units (removed from 05-i18n.js with the i18n bridge), kept here for the old expressions only.
const UNIT_EN = {'초':'s', '분':'m', '시간':'h', '일':'d'};
function UO(n, u){ return LANG !== 'en' ? n + u : n + (UNIT_EN[u] == null ? u : UNIT_EN[u]); }
function oldAll(s){
  const c={age:s}, u={stale:s}, cage=s, age=s;
  const a=KE(' · 마지막 실측 ' + (c.age < 120 ? c.age + '초' : Math.floor(c.age/60) + '분') + ' 전',
             ' · last measured ' + AGO(c.age < 120 ? UO(c.age,'초') : UO(Math.floor(c.age/60),'분')));
  const ago1 = u.stale==null ? '?' : (u.stale<60 ? u.stale+'초' : Math.floor(u.stale/60)+'분');
  const b=KE('백필 '+ago1+' 전', 'backfill '+(u.stale==null ? '?' : AGO(u.stale<60 ? UO(u.stale,'초') : UO(Math.floor(u.stale/60),'분'))));
  const c3=(LANG === 'en' ? 'as of ' + AGO(cage>=3600 ? UO(Math.floor(cage/3600),'시간') : UO(Math.floor(cage/60),'분'))
           : (cage>=3600 ? Math.floor(cage/3600)+'시간' : Math.floor(cage/60)+'분') + ' 전 값');
  const d=AGO(age>=3600?UO(Math.floor(age/3600),'시간'):UO(Math.floor(age/60),'분'));
  return [a,b,c3,d];
}
function newAll(s){
  const u={stale:s};
  const a=KE(' · 마지막 실측 ' + AGO(ageU(s,120,false)), ' · last measured ' + AGO(ageU(s,120,false)));
  const ago = u.stale==null ? KE('? 전', '?') : AGO(ageU(u.stale,60,false));
  const b=KE('백필 '+ago, 'backfill '+ago);
  const c3=KE(ageU(s,0,true) + ' 전 값', 'as of ' + AGO(ageU(s,0,true)));
  const d=AGO(ageU(s,0,true));
  return [a,b,c3,d];
}
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class AgeSpan(unittest.TestCase):
    def test_new_matches_old(self):
        import re
        src = js_all()
        unit = re.search(r"^const UNIT_KO = \{.*?\};", src, re.S | re.M).group(0) + "\n" + js_fn("U") + "\n"
        helpers = "\n".join(re.search(r"function %s\([^\n]*" % n, src).group(0) for n in ("AGO", "KE"))
        js = ("var LANG='ko';\n" + unit + helpers + "\n" + js_fn("ageU") + OLD
              + "const bad=[];for(const L of ['ko','en']){LANG=L;"
              "for(const s of [null,0,1,59,60,61,119,120,121,599,3599,3600,3601,7199,7200,86399,86400,90000,200000]){"
              "const o=JSON.stringify(oldAll(s)), n=JSON.stringify(newAll(s)); if(o!==n) bad.push([L,s,o,n]);}}"
              "process.stdout.write(JSON.stringify(bad));")
        r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), [])

    def test_callers_use_ageu(self):
        src = js_all()
        self.assertNotIn("Math.floor(cage/3600)", src)
        self.assertNotIn("u.stale<60 ? u.stale+'초'", src)
        self.assertEqual(src.count("ageU("), 5)   # definition + 4 call sites (one per age readout)


if __name__ == "__main__":
    unittest.main()
