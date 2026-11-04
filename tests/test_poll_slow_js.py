"""Slow is not disconnected (web/js/95-poll.js poll, 60-statusbar.js connTimedOut/sbBusy/sbBusyHtml): a poll timeout keeps
the connection «slow» until POLL_DOWN_MS with no reply, a network TypeError is still «Disconnected», and the status bar
shows «Data delayed» from state().srvLoad. One node run; real i18n; the clock is a stub."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e
from tests.test_saver_quota_js import i18n

BASE = r"""
const CL = {add(){ this.on = true; }, remove(){ this.on = false; }, on: false};
var document = {getElementById: id => id === 'dot' ? {classList: CL} : null, documentElement: {dataset: {}, classList: {add(){}, remove(){}}}};
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
let NOW = 0; Date.now = () => NOW;
let STATE_IN = true, since = 0, alarmAll = false, SBN = 0, ERR = null, TO = [];
function pollAcksQ(){ return ''; } function buildSbar(){ SBN++; } function softErr(){}
async function getJSON(u, o){ TO.push(o.timeout); NOW += 1000; throw ERR; }
function timeoutErr(){ const e = new Error('aborted'); e.timeout = true; return e; }
"""
FNS = ("ago", "connBackoffMs", "connMark", "connWait", "connAge", "connTimedOut", "sbBusy", "sbBusyHtml", "pollDown")


def run(body):
    src = js_all()
    consts = "\n".join(re.search(r"^(?:const|let|var) " + n + r"\b[^\n]*", src, re.M).group(0)
                       for n in ("CONN", "SB_SNAP_OLD_S", "SRVLOAD", "pollBusy", "POLL_TIMEOUT_MS"))
    poll = re.search(r"^async function poll\(.*?^}$", src, re.M | re.S).group(0)   # js_fn skips async
    js = (BASE + i18n() + "\n" + consts + "\n" + "\n".join(js_fn(f) for f in FNS) + "\n" + poll
          + "\nconst R = {};\n(async () => {\n" + body + "\nprocess.stdout.write(JSON.stringify(R));\n})();")
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PollSlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
// Timeouts: last good reply at 1 s; tries at 15 s and 40 s are slow, the one ending past 75 s is down.
connMark(CONN, true, false, 1000);
ERR = timeoutErr(); NOW = 14000; await poll();
R.t1 = [CONN.fails, CONN.slow, CL.on, CONN.pend];
NOW = 39000; await poll();
R.t2 = [CONN.fails, CONN.slow, CL.on];
NOW = 75000; await poll();
R.t3 = [CONN.fails, CONN.slow, CL.on];
R.to = TO;
// A network TypeError right after a good reply is still «Disconnected».
CL.on = false; connMark(CONN, true, false, 100000); NOW = 101000;
ERR = new TypeError('Failed to fetch'); await poll();
R.net = [CONN.fails, CONN.bad, CL.on];
// A timeout before any good reply (first load) is down.
const c0 = {fails: 0, next: 0, okAt: 0, bad: false, slow: false, pend: 0};
R.first = [connTimedOut(c0, 80000, 75000), c0.slow];
// A good reply clears slow.
const c1 = {fails: 0, next: 0, okAt: 1000, bad: false, slow: true, pend: 0};
connMark(c1, true, false, 5000); R.clear = c1.slow;
// Status-bar verdicts (okAt 100 s, now 101 s).
const ok = {fails: 0, next: 0, okAt: 100000, bad: false, slow: false, pend: 0};
R.none = [sbBusy(null, ok, 101000), sbBusy({load1: 150, snapAge: 1, slow: []}, ok, 101000), sbBusy({}, ok, 101000)];   // load alone is no delay
const hi = sbBusy({load1: 143.27, snapAge: 12, slow: [['<b>tl</b>', 3200.4], ['bad']]}, ok, 101000);
R.hi = hi;
R.hiKo = sbBusyHtml(hi);
R.old = sbBusyHtml(sbBusy({load1: null, snapAge: 12, slow: []}, ok, 101000));
R.pend = sbBusy(null, Object.assign({}, ok, {pend: 100500}), 111000);
R.pendShort = sbBusy(null, Object.assign({}, ok, {pend: 100500}), 105000);
LANG = 'en';
R.hiEn = sbBusyHtml(sbBusy({load1: 5.04, snapAge: 30, slow: [['cards', 900]]}, ok, 101000));
""")

    def test_timeout_is_slow_until_the_long_limit(self):
        self.assertEqual(self.R["t1"], [0, True, False, 0])
        self.assertEqual(self.R["t2"], [0, True, False])
        self.assertEqual(self.R["t3"], [1, False, True])   # 76 s without a reply -> «Disconnected»
        self.assertEqual(self.R["to"], [15000, 75000, 75000, 15000])   # longer wait after a timeout; back to 15 s after a reply

    def test_network_error_is_disconnected(self):
        self.assertEqual(self.R["net"], [1, False, True])

    def test_first_load_timeout_is_down_and_success_clears(self):
        self.assertEqual(self.R["first"], [True, False])
        self.assertFalse(self.R["clear"])

    def test_no_busy_when_quiet_or_srvload_absent(self):
        self.assertEqual(self.R["none"], [None, None, None])
        self.assertIsNone(self.R["pendShort"])

    def test_old_snapshot_label_and_escaped_tooltip(self):
        self.assertEqual(self.R["hi"]["age"], 12)   # max(snapAge 12, 1 s since the reply)
        self.assertEqual(self.R["hi"]["slow"], [["<b>tl</b>", 3200.4]])   # malformed piece dropped
        h = self.R["hiKo"]
        self.assertIn("● 데이터 수신 지연 · 12초 전</b>", h)
        self.assertIn("부하 143 · 느림: &lt;b&gt;tl&lt;/b&gt; 3200 ms", h)
        self.assertNotIn("머신", h)
        self.assertNotIn("<b>tl", h)
        self.assertIn("class=sbwarn", h)
        self.assertNotIn("sberr", h)

    def test_old_snapshot_without_load(self):
        self.assertIn("데이터 수신 지연 · 12초 전", self.R["old"])
        self.assertNotIn("부하", self.R["old"])

    def test_pending_poll_is_busy(self):
        self.assertEqual(self.R["pend"], {"load": None, "age": 11, "slow": []})

    def test_english(self):
        self.assertIn("● Data delayed · 30s ago</b>", self.R["hiEn"])
        self.assertIn("load 5 · slow: cards 900 ms", self.R["hiEn"])


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SlowAgeTicks(unittest.TestCase):
    def test_skipped_tick_repaints_while_slow(self):
        # After a timed-out poll pend restarts with the next request; while CONN.slow the skipped tick must still repaint
        # the bar, else «Data delayed · Ns ago» froze for SB_POLL_SLOW_MS.
        r = run("pollBusy = true; CONN.okAt = 1; CONN.slow = true; NOW = 50000; CONN.pend = NOW - 1000; SBN = 0;\n"
                "await poll(false); R.slow = SBN;\n"
                "CONN.slow = false; SBN = 0; await poll(false); R.fresh = SBN;")
        self.assertEqual((r["slow"], r["fresh"]), (1, 0))
