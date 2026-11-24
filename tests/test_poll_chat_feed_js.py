"""Chat side of poll() (web/js/95-poll.js pollChatFeed, 10-feed.js decorateSync/waitIx/waiting):
the first *applied* state (not poll(true)) paints the feed and sets the unread baseline, a room member change with no new
post re-decorates every post, and the per-thread waiting index answers exactly like the old O(MSGS) scan."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e


def run(prelude, fns, body):
    js = (prelude + "\n" + "\n".join(js_fn(f) for f in fns)
          + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


FEED = r"""
let mainView = 'chat', MSGS = [], chatSeen = 0, CALLS = [];
function chatMark(){ const t = MSGS.reduce((a, m) => Math.max(a, +m.t || 0), 0); if(t) chatSeen = t; CALLS.push('mark'); }
function full(){ CALLS.push('full'); } function toBottom(){ CALLS.push('bottom'); }
function append(f){ CALLS.push('append:' + f.length); }
let pollFed = false;
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class FirstAppliedState(unittest.TestCase):
    def test_failed_first_poll_then_good_poll_paints_full_and_sets_baseline(self):
        # poll(true) timed out (pollChatFeed never ran); the next good poll carries the whole history as fresh.
        R = run(FEED, ("pollChatFeed",), r"""
MSGS = [{t: 10}, {t: 20}, {t: 30}];
pollChatFeed(MSGS.slice());
R.one = [CALLS.slice(), chatSeen];
CALLS = []; MSGS = MSGS.concat([{t: 40}]); pollChatFeed([{t: 40}]);
R.two = CALLS.slice();
""")
        self.assertEqual(R["one"], [["mark", "full", "bottom"], 30])   # no append of the whole history
        self.assertEqual(R["two"], ["mark", "append:1"])

    def test_off_chat_first_apply_sets_baseline_only(self):
        R = run(FEED, ("pollChatFeed",), r"""
mainView = 'time'; MSGS = [{t: 5}, {t: 9}];
pollChatFeed(MSGS.slice()); R.one = [CALLS.slice(), chatSeen];
CALLS = []; MSGS = MSGS.concat([{t: 12}]); pollChatFeed([{t: 12}]); R.two = [CALLS.slice(), chatSeen];
""")
        self.assertEqual(R["one"], [["mark"], 9])
        self.assertEqual(R["two"], [[], 9])   # posts arriving off Chat stay above the baseline (unread badge)

    def test_poll_keys_the_feed_on_the_applied_state_not_its_argument(self):
        poll = re.search(r"^async function poll\(.*?^}$", js_all(), re.M | re.S).group(0)
        self.assertIn("pollChatFeed(fresh)", poll)
        self.assertNotIn("chatMark(", poll)
        code = re.sub(r"//[^\n]*", "", poll)
        self.assertEqual(len(re.findall(r"\bfirst\b", code)), 3, "first may only gate the skip/backoff guards")


DECO = r"""
let ROOMS = {r: {members: ['a', 'b']}}, PROF = {}, MINE = ['a'], MSGS = [], DECO_SIG = null;
function kindOf(s){ const m = String(s || '').match(/^\[(\w+)\]/); return m ? {tag: m[1], cls: m[1]} : null; }
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class DecorateOnMemberChange(unittest.TestCase):
    def test_member_change_without_new_post_redecorates_all(self):
        R = run(DECO, ("decorate", "decorateSync"), r"""
MSGS = [{t: 1, from: 'a', room: 'r'}, {t: 2, from: 'b', room: 'r'}];
decorateSync(MSGS.slice());
R.before = MSGS[0].audience.slice();
ROOMS = {r: {members: ['a', 'b', 'c']}};          // same posts, new member
decorateSync([]);
R.after = MSGS[0].audience.slice();
PROF = {b: {role: 'reviewer'}}; decorateSync([]); R.role = MSGS[1].role;
""")
        self.assertEqual(R["before"], ["b"])
        self.assertEqual(R["after"], ["b", "c"])
        self.assertEqual(R["role"], "reviewer")

    def test_unchanged_inputs_decorate_only_fresh(self):
        R = run(DECO, ("decorate", "decorateSync"), r"""
MSGS = [{t: 1, from: 'a', room: 'r'}];
decorateSync(MSGS.slice());
MSGS[0].audience = ['sentinel'];
const n = {t: 2, from: 'b', room: 'r'}; MSGS = MSGS.concat([n]);
ROOMS = JSON.parse(JSON.stringify(ROOMS));        // replaced object, same content
decorateSync([n]);
R.old = MSGS[0].audience; R.fresh = n.audience;
""")
        self.assertEqual(R["old"], ["sentinel"])
        self.assertEqual(R["fresh"], ["a"])


WAIT = r"""
let MSGS = [], WAITIX = null;
function oldAnswered(m){ return MSGS.some(o => o.thread === m.thread && o.t > m.t && o.from !== m.from && !(o.kind && o.kind.cls === 'ask')); }
function oldWaiting(m){ if(!(m.kind&&m.kind.cls==='ask'&&m.thread)) return false;
  const later=MSGS.filter(o=>o.thread===m.thread&&o.t>m.t);
  if(later.length&&later[later.length-1].kind&&later[later.length-1].kind.cls==='done') return false;
  return !oldAnswered(m); }
let seed = 7; const rnd = n => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % n; };
const KINDS = [null, {cls: 'ask'}, {cls: 'ask'}, {cls: 'done'}, {cls: 'note'}];
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class WaitingIndex(unittest.TestCase):
    def test_index_matches_the_old_scan(self):
        R = run(WAIT, ("answered", "waitIx", "waiting"), r"""
let bad = 0, asks = 0, open = 0;
for(let round = 0; round < 60; round++){
  const n = 1 + rnd(40), t0 = rnd(5); MSGS = [];
  for(let i = 0; i < n; i++) MSGS.push({t: t0 + i - rnd(2), from: 'p' + rnd(3), thread: rnd(6) ? 'th' + rnd(3) : '', kind: KINDS[rnd(5)]});
  MSGS.sort((a, b) => a.t - b.t);                  // MSGS is time-ordered (poll appends by since)
  for(const m of MSGS){ if(waiting(m) !== oldWaiting(m)) bad++; if(m.kind && m.kind.cls === 'ask') asks++; if(waiting(m)) open++; }
}
R.v = [bad, asks > 100, open > 10];
""")
        self.assertEqual(R["v"], [0, True, True])

    def test_index_follows_a_new_post(self):
        R = run(WAIT, ("answered", "waitIx", "waiting"), r"""
const q = {t: 1, from: 'a', thread: 'x', kind: {cls: 'ask'}};
MSGS = [q]; R.a = waiting(q);
MSGS = MSGS.concat([{t: 2, from: 'b', thread: 'x', kind: {cls: 'ask'}}]); R.b = waiting(q);   // counter-question is no reply
MSGS = MSGS.concat([{t: 3, from: 'b', thread: 'x', kind: null}]); R.c = waiting(q);
MSGS = [q, {t: 2, from: 'a', thread: 'x', kind: {cls: 'done'}}]; R.d = waiting(q);              // closed thread
""")
        self.assertEqual([R["a"], R["b"], R["c"], R["d"]], [True, True, False, False])


if __name__ == "__main__":
    unittest.main()
