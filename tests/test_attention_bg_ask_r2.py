"""R2: a `claude --bg` job that ended its turn with a question keeps «Question waiting» while the official
`claude agents --json` lookup is unknown (timed out). The job's argv names only `--resume OLD.jsonl`, so its live sid
comes from the last official answer, held while the same pid runs with the same argv.
Monkeypatched ps / lsof / `claude agents` subprocess; clock frozen."""
import json
import subprocess
import types
import unittest
from unittest import mock

from tests import _clock
from tests._clock import NOW
from tests._load import load, sidereus

load()
live = sidereus("live")
lp = sidereus("live_probe")
sessions = sidereus("sessions")
notes = sidereus("notes")

CWD = "/nonexistent-sidereus/repo"
JOB = "db7d334e-0000-4000-8000-000000000001"
OLD = "34647730-0000-4000-8000-000000000002"
SIB = "adb32f2e-0000-4000-8000-000000000003"
DEAD = "0dead000-0000-4000-8000-000000000004"
JOB_ARGV = "/opt/x/bin/claude.exe --resume /acct/projects/-repo/%s.jsonl --allowed-tools foo" % OLD


class R2BgAsk(unittest.TestCase):
    def setUp(self):
        self.saved = (live._live_cache, list(lp._live_sids), set(live._live_retired[0]))
        self.addCleanup(self._restore)
        for p in (mock.patch.dict(live._av_argv, clear=True), mock.patch.dict(lp._av_held, clear=True),
                  mock.patch.dict(lp._av_sigs), mock.patch.object(lp, "_av_cache", [0.0, None]),
                  mock.patch.object(lp, "_av_fail", [0.0]), mock.patch.object(lp, "warn_once", lambda *a, **k: None),
                  mock.patch.object(lp, "bin_path", lambda n: "claude")):
            p.start()
            self.addCleanup(p.stop)

    def _restore(self):
        live._live_cache = self.saved[0]
        lp._live_sids[0], lp._live_sids[1] = self.saved[1]
        live._live_retired[0] = self.saved[2]

    def _ask(self, rows):
        """One real single-account `claude agents` lookup; rows=None means it times out. -> the view or None."""
        def run(*a, **k):
            if rows is None:
                raise subprocess.TimeoutExpired("claude", 6)
            return types.SimpleNamespace(stdout=json.dumps(rows), returncode=0)
        lp._av_fail[0] = 0.0                               # no negative cache between the scripted lookups
        with _clock.frozen(lp), mock.patch.object(lp.subprocess, "run", run):
            return lp._av_one({}, lp._av_cache, lp._av_fail, 0, None)

    def _outage(self):
        """The lookup fails past AGENTS_STALE_S: the cached answer is cut and the view is unknown."""
        lp._av_cache[0], lp._av_fail[0] = NOW - lp.AGENTS_STALE_S - 1, 0.0
        av = self._ask(None)
        self.assertIsNone(av)
        return av

    def _live(self, snap, av):
        """Run live_cwds() once on the given process snapshot and official view."""
        pmap = {str(p): CWD for p, _pp, _c in snap}
        live._live_cache = (0.0, None)
        with _clock.frozen(live, lp), \
                mock.patch.object(live, "IS_MAC", True), \
                mock.patch.object(live, "_ps_snap", lambda *a, **k: snap), \
                mock.patch.object(live, "agent_view", lambda *a, **k: av), \
                mock.patch.object(live, "_live_pid_cwds", lambda pids: {p: pmap[p] for p in pids if p in pmap}), \
                mock.patch.object(live, "_sid_transcript", lambda sid: sid in (JOB, OLD, SIB, DEAD)), \
                mock.patch.object(live, "_sid_claim_stale", lambda sid, cwd: False):
            out = live.live_cwds(ttl=0)
            alive = {s: lp.sid_alive(s) for s in (JOB, OLD, SIB, DEAD)}
        return out, alive

    def _state(self, live_map, alive, rows):
        """rows = [(sid, asking)] newest first, as sessions() walks them; -> {sid: state}."""
        slots, res = dict(live_map), {}
        for sid, asking in rows:
            lv, stale = sessions._live_slot(CWD, "", False, alive[sid], live_map, slots, set())
            if stale:
                res[sid] = "done"
                continue
            with mock.patch.object(notes, "sid_alive", lambda s: alive.get(s, False)), \
                    mock.patch.object(notes, "sid_alive_stale", lambda s: False):
                res[sid] = sessions._sess_state(CWD, "text", lv, asking, sid=sid)
        return res

    JOB_ROW = {"pid": 500, "sessionId": JOB, "cwd": CWD, "kind": "background"}

    def test_r2_bg_job_end_of_turn_question_shows(self):
        snap = [("500", "1", JOB_ARGV)]
        self._live(snap, self._ask([self.JOB_ROW]))       # T1: official answer names the job
        out, alive = self._live(snap, self._outage())      # T2: lookup unknown, same pid, same argv
        self.assertTrue(alive[JOB])
        self.assertFalse(alive[OLD])                       # the stale argv label is not what is alive
        self.assertEqual(self._state(out, alive, [(JOB, True)])[JOB], "ask")

    def test_r2_bg_job_ask_survives_sibling_same_cwd(self):
        # a newer interactive sibling in the same cwd holds the only path slot
        snap = [("500", "1", JOB_ARGV), ("600", "1", "claude")]
        self._live(snap, self._ask([self.JOB_ROW]))
        out, alive = self._live(snap, self._outage())
        self.assertEqual(out, {CWD: 1})
        self.assertEqual(self._state(out, alive, [(SIB, False), (JOB, True)]), {SIB: "wait", JOB: "ask"})
        self.assertIn(OLD, live._live_retired[0])          # pre-resume sid takes no slot either

    def test_r2_old_dead_same_cwd_still_done(self):
        self._live([("500", "1", JOB_ARGV), ("600", "1", "claude")], self._ask([self.JOB_ROW]))
        av = self._outage()
        # pid gone from the snapshot: dropped, and not revived when the pid number shows up again later
        self._live([("600", "1", "claude")], av)
        out, alive = self._live([("500", "1", JOB_ARGV), ("600", "1", "claude")], av)
        self.assertFalse(alive[JOB])
        self.assertEqual(self._state(out, alive, [(SIB, False), (JOB, True)])[JOB], "done")
        # same pid, different argv (pid reused): not revived
        self._live([("700", "1", JOB_ARGV)], self._ask([dict(self.JOB_ROW, pid=700)]))
        out, alive = self._live([("700", "1", "claude --resume " + OLD)], self._outage())
        self.assertFalse(alive[JOB])

    def test_r2_no_claude_pid_but_av_sid_alive(self):
        # the job itself is a claude argv, so `if not pids:` never hides it
        self.assertTrue(live.is_claude_argv(JOB_ARGV))
        snap = [("500", "1", JOB_ARGV), ("600", "1", "claude")]
        out, alive = self._live(snap, self._ask([self.JOB_ROW]))
        self.assertTrue(alive[JOB])
        # never answered (the lookup failed from the start): nothing beyond today's argv guess
        live._av_argv.clear()
        lp._av_held.clear()
        out, alive = self._live(snap, self._outage())
        self.assertFalse(alive[JOB])
        self.assertTrue(alive[OLD])                        # today's argv-label fallback, unchanged
        # every account answered but omitted the pid: the held answer is not used
        self._live(snap, self._ask([self.JOB_ROW]))
        out, alive = self._live(snap, self._ask([]))
        self.assertFalse(alive[JOB])


if __name__ == "__main__":
    unittest.main()
