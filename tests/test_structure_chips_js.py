"""Structure tab project chips (web/js/80-structure.js): strProjList union/count/order/disambiguation,
strDefProj (most recently active session) and strPickDef picking once. One node run; SESS is a fixture."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

FNS = ("strShort", "strProjList", "strProjs", "strDefProj", "strPickDef")


def run(body):
    src = ("let SESS = [], strOn = [], strHome = '', strAuto = 1, strZoom = '', strErr = '', rebuilt = 0, PROJ_GONE = new Set();\n"
           "let LS = {}; function lsGet(k, d){ return k in LS ? LS[k] : d; }\nconst tabGet = lsGet;\n"
           "function strStop(){}\nfunction strRebuild(){ rebuilt++; }\n"
           + "\n".join(js_fn(f) for f in FNS) + "\nconst R = {};\n" + body
           + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


SESS = [
    {"id": "a", "cwd": "/u/sidereus", "repos": ["/u/sidereus"], "model": "opus", "ageSec": 300},
    {"id": "b", "cwd": "/u/x/origin", "repos": ["/u/x/origin", "/u/x/api", "/u/sidereus"], "model": "sonnet", "ageSec": 5},
    {"id": "c", "cwd": "/u/x/devil", "repos": ["/u/x/api", "/u/x/origin"], "ageSec": None},
    {"id": "c", "cwd": "/u/dup", "repos": []},                       # same id twice — counted once
    {"id": "d", "cwd": "/u/y/api", "repos": [], "ageSec": 60},       # same last folder as /u/x/api
]


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Chips(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
SESS = %s;
R.list = strProjList();
R.def = strDefProj();
strPickDef(); R.on1 = strOn.slice(); R.auto = strAuto;
SESS = [{id: 'z', cwd: '/u/zzz', ageSec: 0}].concat(SESS);
strPickDef(); R.on2 = strOn.slice(); R.reb = rebuilt;
SESS = []; strOn = []; strHome = '/u/home'; strAuto = 1;
R.empty = strProjs(); strPickDef(); R.auto0 = strAuto;
SESS = %s; strHome = ''; strOn = []; strAuto = 1; LS['sidereus.strp'] = '/u/y/api'; strPickDef(); R.saved = strOn.slice();
strOn = []; strAuto = 1; LS['sidereus.strp'] = '/u/gone'; strPickDef(); R.gone = strOn.slice();
""" % (json.dumps(SESS), json.dumps(SESS)))

    def test_union_count_order(self):
        got = [(e["p"], len(e["ss"])) for e in self.R["list"]]
        self.assertEqual(dict(got), {"/u/sidereus": 2, "/u/x/origin": 2, "/u/x/api": 2, "/u/x/devil": 1, "/u/y/api": 1})
        counts = [n for _, n in got]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_open_skips_ended_sessions(self):
        # The picker's «작업 중» group reads `open`; SESS also lists ended sessions (state 'done').
        r = run("SESS = [{id: 'a', cwd: '/u/p', state: 'done'}, {id: 'b', cwd: '/u/q', state: 'idle'}, {id: 'c', cwd: '/u/q'}];"
                " R.l = strProjList().map(e => [e.p, e.ss.length, e.open]);")
        self.assertEqual(sorted(map(tuple, r["l"])), [("/u/p", 1, 0), ("/u/q", 2, 2)])

    def test_names_and_who(self):
        by = {e["p"]: e for e in self.R["list"]}
        self.assertEqual(by["/u/x/api"]["name"], "x/api")
        self.assertEqual(by["/u/y/api"]["name"], "y/api")
        self.assertEqual(by["/u/sidereus"]["name"], "sidereus")
        self.assertEqual(by["/u/sidereus"]["ss"], ["sidereus · opus", "origin · sonnet"])
        names = [e["name"] for e in self.R["list"] if len(e["ss"]) == 2]
        self.assertEqual(names, sorted(names))

    def test_default_most_recent_once(self):
        self.assertEqual(self.R["def"], "/u/x/origin")
        self.assertEqual(self.R["on1"], ["/u/x/origin"])
        self.assertEqual(self.R["auto"], 0)
        self.assertEqual(self.R["on2"], ["/u/x/origin"])   # a newer session later does not move the selection
        self.assertEqual(self.R["reb"], 1)

    def test_saved_project_wins_only_while_listed(self):
        self.assertEqual(self.R["saved"], ["/u/y/api"])
        self.assertEqual(self.R["gone"], ["/u/x/origin"])

    def test_no_sessions_falls_back_to_home(self):
        self.assertEqual(self.R["empty"], ["/u/home"])
        self.assertEqual(self.R["auto0"], 1)

    def test_deleted_folders_get_no_chip_and_selection_falls_back(self):
        # state `projGone`: a deleted worktree keeps its session rows but loses its chip; a selected one re-picks the default.
        r = run("SESS = [{id: 'a', cwd: '/u/keep', ageSec: 50}, {id: 'b', cwd: '/u/wt', repos: ['/u/wt', '/u/keep'], ageSec: 1}];"
                " PROJ_GONE = new Set(['/u/wt']); R.l = strProjs(); R.def = strDefProj();"
                " strOn = ['/u/wt']; strAuto = 0; strPickDef(); R.on = strOn.slice(); R.l2 = strProjs();")
        self.assertEqual(r["l"], ["/u/keep"])
        self.assertEqual(r["def"], "/u/keep")
        self.assertEqual(r["on"], ["/u/keep"])
        self.assertEqual(r["l2"], ["/u/keep"])


if __name__ == "__main__":
    unittest.main()
