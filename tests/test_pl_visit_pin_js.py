"""«Since your last visit» run click pins that session's run (48n visitGo -> 48b plViewRun/plPinRun):
an ended session's run must show even while another session runs the same pipeline live."""
import json
import shutil
import unittest

from tests.test_pipeline_run import ESC, MODEL, N, ST4, _js

X, Y = "xended00", "ylive000"
DONE = lambda a, b: {"o": "done", "n": 1, "t0": a, "t1": b, "from": {}}
X_RUN = {"name": "p", "proj": "/x/api", "sid": X, "rid": N - 3000, "cur": "리뷰", "end": N - 2000, "stop": 0, "t0": N - 3000, "t1": N - 2000,
         "stages": {t: DONE(N - 3000, N - 2000) for t in ("설계", "구현", "검증", "리뷰")},
         "past": [{"rid": N - 5000, "t0": N - 5000, "t1": N - 4000, "end": N - 4000, "cur": "설계", "stop": 0,
                   "stages": {"설계": DONE(N - 5000, N - 4000)}}]}
Y_RUN = {"name": "p", "proj": "/x/api", "sid": Y, "rid": N - 600, "cur": "구현", "end": 0, "t0": N - 600, "t1": N - 10,
         "stages": {"설계": DONE(N - 600, N - 500), "구현": {"o": "run", "n": 1, "t0": N - 500, "t1": N - 10, "from": {}}}}
SESS = [{"sid": X, "cwd": "/x/api", "state": "done", "plrun": [X_RUN]}, {"sid": Y, "cwd": "/x/api", "state": "run", "plrun": [Y_RUN]}]
HEAD = {"k": "run", "sid": X, "name": "p", "proj": "/x/api", "rid": N - 3000, "cur": N - 3000, "past": False}
PAST = dict(HEAD, rid=N - 5000, past=True)
FNS = ("visitGo", "plViewRun", "plPinRun", "plPastLv", "plRunNav", "plRunLab", "plRunPick", "plLiveHead", "plRvPick", "plRvClose",
       "plLiveRun", "plProjSess", "plMem", "plRunName", "plSubsOf", "plOvSid", "plNowLive") + MODEL


def run(body):
    stub = ("%s Date.now = () => %d; Object.assign(globalThis, {SESS: %s, mainView: 'pipe', PLRV: false, PLS: {runSel: null, nowSid: '', proj: '/x/api',"
            " data: {'/x/api': {ok: true, pipelines: [{name: 'p', stages: %s}]}}}, lsJson: () => ({}), hhmm: t => 'H' + t, sid8: s => s, ago: s => s + 's',"
            " plCur: () => ({name: 'p'}), plPaint(){}, setMainView(){}, document: {getElementById: () => null}});"
            # plOvPick stand-in: the two effects the defect rides on (48b plOvPick clears runSel, nowSid = plOvSid)
            " globalThis.plOvPick = (proj, name, sid) => { PLS.runSel = null; PLS.nowSid = plOvSid(proj, name, sid); };"
            % (ESC, N * 1000, json.dumps(SESS), json.dumps(ST4)))
    return _js("(() => { %s %s })()" % (stub, body), *FNS)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class VisitPinsEndedSessionRun(unittest.TestCase):
    def test_head_item_shows_ended_session_run(self):
        r = run("visitGo(%s); const v = plViewRun('/x/api', 'p'); return [v.sid, v.pr.rid, v.lt['리뷰'].st, (plRunNav(v) || {}).N, plLiveHead(v, v.lt)];" % json.dumps(HEAD))
        self.assertEqual(r[:4], [X, N - 3000, "done", 2])        # not Y's live run
        self.assertIn("data-plrvb", r[4])                          # «Back to current» even on the pinned head

    def test_past_item_shows_that_earlier_run(self):
        r = run("visitGo(%s); const v = plViewRun('/x/api', 'p'); return [v.sid, v.pr.rid, v.lt['설계'].st, v.lt['구현'].st, (v.nav || {}).k, !!PLS.runSel];" % json.dumps(PAST))
        self.assertEqual(r, [X, N - 5000, "done", "wait", 1, True])

    def test_picker_keeps_the_pinned_session(self):
        r = run("visitGo(%s); plRvPick(String(%d)); const a = plViewRun('/x/api', 'p'); plRvPick(String(%d)); const b = plViewRun('/x/api', 'p');"
                " return [a.sid, a.pr.rid, b.sid, b.pr.rid, PLS.runSel.pin];" % (json.dumps(HEAD), N - 5000, N - 3000))
        self.assertEqual(r, [X, N - 5000, X, N - 3000, True])

    def test_back_or_gone_session_falls_back_to_live(self):
        r = run("visitGo(%s); PLS.runSel = null; const a = plViewRun('/x/api', 'p');"
                " visitGo(%s); SESS = SESS.filter(x => x.sid !== '%s'); const b = plViewRun('/x/api', 'p');"
                " return [a.sid, b.sid, PLS.runSel];" % (json.dumps(HEAD), json.dumps(PAST), X))
        self.assertEqual(r, [Y, Y, None])

    def test_pin_kept_while_reload_loads(self):
        r = run("visitGo(%s); SESS = []; plViewRun('/x/api', 'p'); return PLS.runSel && PLS.runSel.rid;" % json.dumps(HEAD))
        self.assertEqual(r, N - 3000)


if __name__ == "__main__":
    unittest.main()
