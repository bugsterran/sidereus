"""`live_cwds`: a terminal pid whose label sid was forked into an official session gives up its path slot. No live files."""
import types
import unittest

from tests._load import sidereus

lv = sidereus("live")

OLD = "cc33cc33-0000-4000-8000-000000000001"
NEW = "dd44dd44-0000-4000-8000-000000000002"
CWD = "/Users/x/proj"


class LiveFork(unittest.TestCase):
    def setUp(self):
        self._saved = {k: getattr(lv, k) for k in
                       ("_ps_snap", "agent_view", "subprocess", "IS_MAC", "_sid_transcript", "_sid_claim_stale")}
        self._cache = lv._live_cache
        lv._live_cache = (0.0, set())
        lv.IS_MAC = True
        lv._sid_transcript = lambda sid: "/t/%s.jsonl" % sid
        lv._sid_claim_stale = lambda sid, cwd: True       # the old label has a newer sibling transcript

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(lv, k, v)
        lv._live_cache = self._cache

    def run_with(self, snap, av, pmap):
        lv._ps_snap = lambda ttl=None: snap
        lv.agent_view = lambda ttl=None: av
        out = "".join("p%s\nn%s\n" % kv for kv in pmap.items())
        lv.subprocess = types.SimpleNamespace(run=lambda *a, **k: types.SimpleNamespace(stdout=out))
        return lv.live_cwds(ttl=0)

    def test_forked_terminal_pid_gives_up_slot(self):
        snap = [("100", "1", "claude --resume " + OLD),
                ("200", "1", "claude --session-id %s --fork-session --resume /p/%s.jsonl" % (NEW, OLD))]
        live = self.run_with(snap, {"200": {"sessionId": NEW, "cwd": CWD}}, {"100": CWD, "200": CWD})
        self.assertEqual(live, {})
        self.assertFalse(lv.sid_alive(OLD))
        self.assertTrue(lv.sid_alive(NEW))

    def test_unlisted_session_without_lineage_keeps_slot(self):
        # ⚠A real session missing from the official list in the same path (the 78979 case) must stay visible.
        other = "c5b6f705-0000-0000-0000-000000000000"
        snap = [("100", "1", "claude --resume " + other),
                ("200", "1", "claude --session-id %s" % NEW)]
        live = self.run_with(snap, {"200": {"sessionId": NEW, "cwd": CWD}}, {"100": CWD, "200": CWD})
        self.assertEqual(live, {CWD: 1})


if __name__ == "__main__":
    unittest.main()
