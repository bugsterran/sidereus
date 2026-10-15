"""«파이프라인» running marker (web/js/48-pipeline.js plLiveProjs): which projects run a pipeline now.
Pure function under node; data passed as args (no SESS globals)."""
import json
import re
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e


def _live(sess, mem=None, known=None, count=False, orph=False, pre=""):
    const = re.search(r"^const PL_DESC_RE[^\n]*$", js_all(), re.M).group(0)
    fns = ("plTk", "plDescStage", "plRunName", "plLiveProjs", "plLiveN", "plLabType", "plTagNames", "plAway", "plHomes")
    src = const + "\n" + pre + "\n" + "\n".join(js_fn(f) for f in fns) \
        + "\nconst O = []; const L = plLiveProjs(%s, %s, %s, O); console.log(JSON.stringify([L, plLiveN(L, %s), O]));" % (
            json.dumps(sess), json.dumps(mem or {}), json.dumps(known), json.dumps(known))
    out = json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True).stdout)
    if orph:
        return out[0], out[2]                                           # [map, orphan tags]
    return out[:2] if known is not None or count else out[0]            # [map, tab count] when asked


def _run(run, load=None):
    ags = [{"phase": "불러오기", "lab": "load " + load}] if load else []
    return {"name": "pipeline", "run": run, "agents": ags + [{"phase": "설계", "lab": "설계"}]}


class LiveProjs(unittest.TestCase):
    def test_tagged_sub_marks_cwd_and_repos(self):
        s = [{"sid": "a", "cwd": "/p", "repos": ["/q"], "sub": [{"lab": "sidereus-designer: [pl:sidereus-change/설계] spec"}]}]
        self.assertEqual(_live(s), {"/p": ["sidereus-change"], "/q": ["sidereus-change"]})

    def test_main_plm_marks(self):
        s = [{"sid": "a", "cwd": "/p", "sub": [], "plm": {"name": "bugfix", "title": "수정", "age": 3}}]
        self.assertEqual(_live(s), {"/p": ["bugfix"]})

    def test_main_plm_of_ended_run_marks_nothing(self):
        plm = {"name": "bugfix", "title": "라이브 검증", "age": 30}
        ended = [{"sid": "a", "cwd": "/p", "sub": [], "plm": plm, "plrun": [{"name": "bugfix", "end": 1791332594.6}]}]
        self.assertEqual(_live(ended), {})
        still = [{"sid": "a", "cwd": "/p", "sub": [], "plm": plm, "plrun": [{"name": "bugfix", "end": 0}]}]
        self.assertEqual(_live(still), {"/p": ["bugfix"]})

    def test_untagged_or_dash_marks_nothing(self):
        s = [{"sid": "a", "cwd": "/p", "sub": [{"lab": "x: [pl:-] skip"}, {"lab": "cart-api-bugfix: fix it"}]}]
        self.assertEqual(_live(s), {})

    def test_wf_run_flag(self):
        self.assertEqual(_live([{"sid": "a", "cwd": "/p", "wf": [_run(False, "bugfix")]}]), {})
        self.assertEqual(_live([{"sid": "a", "cwd": "/p", "wf": [_run(True, "bugfix")]}]), {"/p": ["bugfix"]})
        self.assertEqual(_live([{"sid": "a", "cwd": "/p", "wf": [_run(True)]}], {"a": {"name": "feat", "at": 1}}), {"/p": ["feat"]})
        self.assertEqual(_live([{"sid": "a", "cwd": "/p", "wf": [_run(True)]}]), {"/p": ["?"]})

    def test_distinct_names(self):
        one = [{"sid": "a", "cwd": "/p", "sub": [{"lab": "x: [pl:sidereus-change/구현] s1"}, {"lab": "x: [pl:sidereus-change/구현] s2"}]}]
        self.assertEqual(len(_live(one)["/p"]), 1)
        two = [{"sid": "a", "cwd": "/p", "sub": [{"lab": "x: [pl:sidereus-change/구현] s1"}]},
               {"sid": "b", "cwd": "/p", "sub": [{"lab": "y: [pl:bugfix/원인] c"}]}]
        self.assertEqual(sorted(_live(two)["/p"]), ["bugfix", "sidereus-change"])

    def test_owner_only(self):
        s = [{"sid": "a", "cwd": "/origin", "repos": ["/api", "/other"], "sub": [{"lab": "x: [pl:bugfix/원인] c"}]}]
        known = {"/origin": {"n": 0, "names": None}, "/api": {"n": 1, "names": None}}
        self.assertEqual(_live(s, known=known), [{"/api": ["bugfix"]}, 1])
        known["/api"]["names"] = ["feature"]                              # loaded list without that name
        self.assertEqual(_live(s, known=known), [{}, 0])

    def test_away_session_attaches_to_sole_owner(self):
        s = [{"sid": "abcdef0123", "cwd": "/triage", "sub": [{"lab": "x: [pl:bugfix/수정] fix"}]}]
        known = {"/agent": {"n": 1, "names": ["bugfix"]}, "/other": {"n": 1, "names": ["feature"]}}
        self.assertEqual(_live(s, known=known, orph=True), ({"/agent": ["bugfix"]}, []))
        known["/other"]["names"] = ["bugfix"]                           # two owners: ambiguous, not guessed
        self.assertEqual(_live(s, known=known, orph=True), ({}, [{"sid": "abcdef0123", "name": "bugfix"}]))
        known["/other"]["names"] = None                                 # a list still loading: undecided, no hint yet
        self.assertEqual(_live(s, known=known, orph=True), ({}, []))
        self.assertEqual(_live(s, orph=True), ({"/triage": ["bugfix"]}, []))   # known null: unchanged (no filter)

    def test_tab_count_is_project_name_pairs(self):
        s = [{"sid": "a", "cwd": "/p", "repos": ["/q"], "wf": [_run(True)], "sub": [{"lab": "x: [pl:bugfix/원인] c"}]}]
        known = {"/p": {"n": 2, "names": ["bugfix"]}, "/q": {"n": 1, "names": None}}
        L, n = _live(s, known=known)
        # the cwd project owns «bugfix», so the run stays there only (was counted under /q too: one run shown twice)
        self.assertEqual((sorted(L["/p"]), "/q" in L, n), (["?", "bugfix"], False, 2))

    def test_run_goes_to_the_project_whose_stage_agents_match(self):
        # both own «bugfix»; the tagged sub's type is the api pipeline's stage agent -> api only (cwd-first sent it to origin)
        s = [{"sid": "a", "cwd": "/o", "repos": ["/a"], "sub": [{"lab": "api-fix: [pl:bugfix/수정] c"}]}]
        js = ("const PLS = {data: {'/o': {pipelines: [{name: 'bugfix', stages: [{title: '수정', agent: 'origin-dev'}]}]},"
              " '/a': {pipelines: [{name: 'bugfix', stages: [{title: '수정', agent: 'api-fix'}]}]}}};")
        L, n = _live(s, known={"/o": {"n": 1, "names": ["bugfix"]}, "/a": {"n": 1, "names": ["bugfix"]}}, pre=js)
        self.assertEqual(L, {"/a": ["bugfix"]})

    def test_repo_project_takes_run_when_cwd_lacks_it(self):
        s = [{"sid": "a", "cwd": "/p", "repos": ["/q"], "sub": [{"lab": "x: [pl:bugfix/원인] c"}]}]
        L, n = _live(s, known={"/p": {"n": 1, "names": ["feature"]}, "/q": {"n": 1, "names": ["bugfix"]}})
        self.assertEqual((L, n), ({"/q": ["bugfix"]}, 1))

    def test_tab_count_unknown_list_counts_names(self):
        s = [{"sid": "a", "cwd": "/p", "repos": ["/q", "/r"], "sub": [{"lab": "x: [pl:bugfix/원인] c"}]}]
        self.assertEqual(_live(s, count=True)[1], 1)                    # one run, three candidate projects


if __name__ == "__main__":
    unittest.main()
