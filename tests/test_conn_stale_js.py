"""Poll connection state (web/js/60-statusbar.js): backoff schedule, reset on success, «N분 전 기준» age, popover notice,
and keepGood (46-tokens-tab.js) holding the last good snapshot. One node run; real i18n; now passed in (no clock)."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import i18n
from tests._node import node_e

BASE = "var document = {getElementById: () => null};\nconst esc = s => String(s);\n"
FNS = ("ago", "connBackoffMs", "connMark", "connWait", "connAge", "connStaleNote", "keepGood")


def run(body):
    src = (BASE + i18n() + "\n" + "\n".join(js_fn(f) for f in FNS)
           + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ConnStale(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
R.back = [0, 1, 2, 3, 4, 5, 9].map(connBackoffMs);
const c = {fails: 0, next: 0, okAt: 0, bad: false};
connMark(c, true, false, 1000);
R.okWait = connWait(c, 1000);
R.ageOk = connAge(c, 5000);
connMark(c, false, false, 10000);
R.f1 = [c.fails, c.next, connWait(c, 14749), connWait(c, 14750)];
connMark(c, false, false, 15000);
R.f2 = [c.fails, c.next];
R.ageKo = [connAge(c, 46000), connAge(c, 1000 + 150000)];
R.noteKo = connStaleNote(c, 46000);
LANG = 'en';
R.ageEn = [connAge(c, 46000), connAge(c, 1000 + 150000)];
connMark(c, false, true, 20000);
R.noteBad = connStaleNote(c, 46000);
LANG = 'ko';
connMark(c, true, false, 30000);
R.reset = [c.fails, c.next, c.bad, c.okAt, connWait(c, 30001), connAge(c, 40000), connStaleNote(c, 40000)];
const never = connMark({fails: 0, next: 0, okAt: 0, bad: false}, false, false, 5000);
R.never = [connAge(never, 9000), connStaleNote(never, 9000)];
// Real loop: 2.5s ticks from 0, every request fails; gaps between request starts.
R.gaps = [];
for(const jit of [0, 3]){                       // tick firing on time / slightly late
  const k = {fails: 0, next: 0, okAt: 0, bad: false}; let last = null;
  for(let t = 0; t < 120000; t += 2500){
    if(connWait(k, t + jit)) continue;
    if(last !== null) R.gaps.push(t - last);
    last = t; connMark(k, false, false, t);    // marked from request start (95-poll.js t0)
  }
}
const good = {at: 1, today: '2026-10-05', live: [1, 2]};
R.keep = [keepGood(good, 'x') === good, keepGood(null, 'x'), keepGood({err: 'old'}, 'x'), keepGood({}, 'x')];
""")

    def test_backoff_schedule_caps_at_10s(self):
        self.assertEqual(self.R["back"], [0, 5000, 10000, 10000, 10000, 10000, 10000])

    def test_fail_schedules_next_try(self):
        self.assertFalse(self.R["okWait"])
        self.assertEqual(self.R["f1"], [1, 14750, True, False])   # 5s minus 250ms jitter slack
        self.assertEqual(self.R["f2"], [2, 24750])   # 15000 + 10000 (cap) - 250

    def test_real_retry_gap_within_cap(self):
        # was 7.5/12.5s: next counted from the failure return, so the 2.5s tick skipped a round
        self.assertTrue(self.R["gaps"])
        self.assertLessEqual(max(self.R["gaps"]), 10000)
        self.assertEqual(sorted(set(self.R["gaps"])), [5000, 10000])

    def test_success_resets(self):
        self.assertEqual(self.R["reset"], [0, 0, False, 30000, False, "", ""])

    def test_age_label(self):
        self.assertEqual(self.R["ageOk"], "")
        self.assertEqual(self.R["ageKo"], ["45초 전 기준", "2분 전 기준"])
        self.assertEqual(self.R["ageEn"], ["as of 45s ago", "as of 2m ago"])
        self.assertEqual(self.R["never"], ["", ""])   # never connected: nothing to date

    def test_popover_note(self):
        self.assertEqual(self.R["noteKo"], "<div class=connst>연결 끊김 · 45초 전 기준</div>")
        self.assertEqual(self.R["noteBad"], "<div class=connst>Bad response · as of 45s ago</div>")

    def test_keep_good(self):
        self.assertTrue(self.R["keep"][0])
        self.assertEqual(self.R["keep"][1:], [{"err": "x"}, {"err": "x"}, {"err": "x"}])


if __name__ == "__main__":
    unittest.main()
