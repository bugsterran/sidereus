"""A run lands only on the project recorded in its plrun (web/js/48-pipeline.js plHomes, 48b plLiveRun), not on another
project's same-named pipeline whose stage agents fit the tags better; recorded skip stages render as skip."""
import json
import unittest

from tests.test_pipeline_live import _live
from tests.test_pipeline_run import MODEL, N, _js

ST = [{"title": t, "agent": "o-dev"} for t in ("원인", "수정", "리뷰")]
ST_B = [{"title": t, "agent": "b-fix"} for t in ("원인", "수정", "리뷰")]
PR = {"name": "bugfix", "proj": "/a", "sid": "s", "cur": "수정", "end": 0, "t0": N - 600, "t1": N - 10, "stages": {
    "원인": {"o": "done", "n": 1, "t0": N - 600, "t1": N - 500, "from": {}, "ag": []},
    "수정": {"o": "run", "n": 1, "t0": N - 500, "t1": N - 10, "from": {}, "ag": []},
    "리뷰": {"o": "skip", "n": 0, "t0": N - 400, "t1": N - 400, "from": {}, "ag": []}}}
# cwd /a, also edits /b; the tag's type fits /b's stage agent better, but the server recorded the run under /a
SESS = [{"sid": "s", "cwd": "/a", "repos": ["/b"], "sub": [{"lab": "b-fix: [pl:bugfix/수정] c"}], "plrun": [PR]}]
KNOWN = {"/a": {"n": 1, "names": ["bugfix"]}, "/b": {"n": 1, "names": ["bugfix"]}}
DATA = {"/a": {"ok": True, "pipelines": [{"name": "bugfix", "stages": ST}]}, "/b": {"ok": True, "pipelines": [{"name": "bugfix", "stages": ST_B}]}}


def _run(sess, proj, ret):
    pls = {"projs": {"ok": True, "projects": [{"path": "/a", "n": 1}, {"path": "/b", "n": 1}]}, "data": DATA}
    stub = "Date.now = () => %d; Object.assign(globalThis, {SESS: %s, PLS: %s, lsJson: () => ({})});" % (N * 1000, json.dumps(sess), json.dumps(pls))
    return _js("(() => { %s const r = plLiveRun(%s, 'bugfix'); return %s; })()" % (stub, json.dumps(proj), ret),
               "plLiveRun", "plProjSess", "plMem", "plRunName", "plSessions", "plSubsOf", *MODEL)


class RunProject(unittest.TestCase):
    def test_dot_only_on_recorded_project(self):
        pre = "const PLS = %s;" % json.dumps({"data": DATA})
        self.assertEqual(_live(SESS, known=KNOWN, pre=pre), [{"/a": ["bugfix"]}, 1])
        self.assertEqual(_live(SESS, pre=pre), {"/a": ["bugfix"]})          # known null: the record still decides

    def test_no_stand_in_run_on_other_project(self):
        self.assertIsNone(_run(SESS, "/b", "r"))
        self.assertEqual(_run(SESS, "/a", "r && [r.sid, r.lt['원인'].st, r.lt['수정'].st, r.lt['리뷰'].st]"), ["s", "done", "run", "skip"])

    def test_record_without_proj_keeps_scoring(self):
        sess = [dict(SESS[0], plrun=[dict(PR, proj="")])]
        pre = "const PLS = %s;" % json.dumps({"data": DATA})
        self.assertEqual(_live(sess, known=KNOWN, pre=pre)[0], {"/b": ["bugfix"]})


if __name__ == "__main__":
    unittest.main()
