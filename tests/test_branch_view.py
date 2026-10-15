"""Branch tab (web/js/88-branch.js): repo list, loadBr repo choice (stale saved repo, 400/403 fallback without ping-pong),
brLanes lanes/edges, brKidSet, brGraphSvg lane cap, brMsg, brListHtml chips. One node run."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import sidereus, js_all, js_fn
from tests._node import node_e

BASE = r"""
const T = s => s, KE = (ko, en) => ko, TV = j => j && j.msg ? String(j.msg).replace(/\{(\w+)\}/g, (m, k) => j.vars && k in j.vars ? j.vars[k] : m) : '', esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const document = {documentElement: {dataset: {}}};   // real thc (00-core.js) reads the theme from here
const softErr = () => {}, strShort = p => p.split('/').pop(), agoAt = () => 'ago', brLkChip = () => '';
const UIS = {getItem(k){ return k in this && typeof this[k] === 'string' ? this[k] : null; }, removeItem(k){ delete this[k]; }};
let SESS = [], STATE_IN = true, mainView = 'br', BR = null, brRepo = '', brBusy = 0, brRetry = 0, brWaitN = 0, brSel = '', brKid = [];
let paints = 0; const paintBr = () => { paints++; };
const _st = setTimeout; let timers = 0; setTimeout = () => { timers++; };
let fetched = [], answer = {};
const fetch = url => { const cwd = decodeURIComponent(url.match(/cwd=([^&]*)/)[1]); fetched.push(cwd);
  const st = answer[cwd] || 200;
  return Promise.resolve({status: st, json: () => Promise.resolve(st === 200 ? {ok: true, repo: cwd} : {ok: false, err: 'bad'})}); };
const settle = () => new Promise(r => _st(r, 5));
"""
FNS = ("tabRead", "tabWrite", "tabStores", "tabGet", "tabDel", "brRepos", "brForget", "loadBr", "brMsg", "brLanes", "brKidSet", "brGraphSvg", "brListHtml")


def run(body):
    src = js_all()
    consts = "\n".join(re.search(p, src, re.M).group(0) for p in (r"^const BR_RH = \d+;", r"^const BR_CHIPS = \d+;", r"^const BR_ERRS = .*;$", r"^const brBad = new Set\(\);", r"^const thc = .*;$"))
    js = BASE + consts + "\n" + "\n".join(js_fn(f) for f in FNS) + "\nconst R = {};\n(async () => {\n" + body \
        + "\nprocess.stdout.write(JSON.stringify(R));\n})().catch(e => { console.error(e); process.exit(1); });"
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class BranchView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
SESS = [null, {cwd: '/a', branch: 'main', repos: ['/a', '/b']}, {cwd: '/nogit', repos: ['/c']}, {cwd: '/b', branch: 'x'}];
R.repos = brRepos();
// Saved repo no longer in any session: forgotten before any fetch, first listed repo used.
brRepo = '/old'; UIS.mbBrRepo = '/old';
loadBr(); await settle();
R.stale = {repo: brRepo, fetched: fetched.slice(), saved: UIS.mbBrRepo === undefined, ok: BR && BR.ok};
// Cached answer for the same repo: no refetch unless forced.
fetched = []; loadBr(); await settle(); R.cached = fetched.length;
loadBr(true); await settle(); R.forced = fetched.length;
// 400 on /a -> silently tries /b; 403 on /b too -> /c; all bad -> message, no endless loop.
answer = {'/a': 400, '/b': 403}; fetched = []; BR = null; brRepo = '/a';
loadBr(true); await settle(); await settle(); await settle();
R.fallback = {repo: brRepo, fetched: fetched.slice(), ok: BR && BR.ok};
answer['/c'] = 400; fetched = []; brBad.clear(); brRepo = '/a';
loadBr(true); for(let i = 0; i < 6; i++) await settle();
R.allBad = {fetched: fetched.slice(), ok: BR.ok, msg: BR.msg};
// No repo at all -> message and one retry timer; before the first state -> just loading.
SESS = []; brRepo = ''; timers = 0; loadBr(); R.none = {msg: BR.msg, timers};
STATE_IN = false; brRepo = '/x'; brWaitN = 0; timers = 0; fetched = []; loadBr(); R.preState = {BR, timers, fetched: fetched.length};
R.msgErr = [brMsg(400, {err: 'not a git repo'}), brMsg(500, {err: 'timeout'})];
R.msg = [brMsg(403, {}), brMsg(400, {err: 'nope'}), brMsg(404, {}), brMsg(500, {msg: 'boom'}), brMsg(502, {}), brMsg(0, null)];
// a(merge of b,c) -> b -> d ; c -> d ; d root
const cms = [{sha: 'a', parents: ['b', 'c'], refs: ['HEAD', 'main']}, {sha: 'b', parents: ['d']}, {sha: 'c', parents: ['d'], refs: ['origin/f']},
             {sha: 'd', parents: ['zz']}];
const lay = brLanes(cms);
R.lanes = {rows: lay.rows.map(r => [r.sha, r.lane, r.merge]), edges: lay.edges.map(e => [e.from, e.to, e.lane, e.via, e.plane, e.merge]), n: lay.lanes};
R.linear = brLanes([{sha: '1', parents: ['2']}, {sha: '2', parents: []}]);
R.empty = brLanes(null);
brKidSet(cms, lay); R.kid = brKid.slice();
const wide = []; for(let i = 0; i < 20; i++) wide.push({sha: 's' + i, parents: []});
const wl = {rows: wide.map((c, i) => ({sha: c.sha, row: i, lane: i, merge: false})), edges: [], lanes: 20};
R.svgW = +brGraphSvg(wide, wl).match(/width="(\d+)"/)[1];
R.svgH = +brGraphSvg(wide, wl).match(/height="(\d+)"/)[1];
const svg = brGraphSvg(cms, lay);
R.svgHead = (svg.match(/r="8.5"/g) || []).length;
R.svgPaths = (svg.match(/<path /g) || []).length;
BR = {head: 'main', detached: false};
R.list = brListHtml(cms, [{name: 'main', kind: 'local'}, {name: 'origin/f', kind: 'remote'}]);
BR = {head: 'abc1234', detached: true};
const many = []; for(let i = 0; i < 9; i++) many.push('t' + i);
R.listMany = brListHtml([{sha: 'f', refs: many, subject: 'subj'}], []);
R.listDet = brListHtml([{sha: 'abc1234', refs: ['HEAD', 'abc1234'], subject: 's', author: '홍길동/팀/역할'}], []);
""")

    def test_repos_union(self):
        self.assertEqual(self.R["repos"], ["/a", "/b", "/c"])   # cwd only with a branch; order kept, no dupes

    def test_stale_saved_repo(self):
        self.assertEqual(self.R["stale"], {"repo": "/a", "fetched": ["/a"], "saved": True, "ok": True})
        self.assertEqual((self.R["cached"], self.R["forced"]), (0, 1))

    def test_unreadable_repo_falls_back_once(self):
        self.assertEqual(self.R["fallback"], {"repo": "/c", "fetched": ["/a", "/b", "/c"], "ok": True})
        a = self.R["allBad"]
        self.assertEqual(a["fetched"], ["/a", "/b", "/c"])     # each repo tried once, then a message
        self.assertFalse(a["ok"])
        self.assertIn("Unreadable path — bad", a["msg"])   # English source (T is a pass-through here)

    def test_no_repo_and_before_state(self):
        self.assertEqual(self.R["none"], {"msg": "No git repository in the session list yet", "timers": 1})
        self.assertEqual(self.R["preState"], {"BR": None, "timers": 1, "fetched": 0})

    def test_messages(self):
        m = self.R["msg"]
        self.assertIn("not in the list", m[0])
        self.assertEqual(m[1], "Unreadable path — nope")
        self.assertIn("/api/branches is missing", m[2])
        self.assertEqual(m[3:], ["boom", "Could not fetch (502)", "Could not fetch"])

    def test_lanes(self):
        L = self.R["lanes"]
        self.assertEqual(L["rows"], [["a", 0, True], ["b", 0, False], ["c", 1, False], ["d", 0, False]])
        # first parent keeps lane 0; the merge's second parent opens lane 1; c's edge bends back into d's lane
        self.assertEqual(L["edges"], [[0, 1, 0, 0, 0, False], [0, 2, 0, 1, 1, True], [1, 3, 0, 0, 0, False], [2, 3, 1, 1, 0, False]])
        self.assertEqual(L["n"], 2)
        self.assertEqual([r["lane"] for r in self.R["linear"]["rows"]], [0, 0])
        self.assertEqual(self.R["empty"], {"rows": [], "edges": [], "lanes": 1})
        self.assertEqual(self.R["kid"], [-1, 0, -1, 1])   # same-lane first-parent child only

    def test_graph_svg(self):
        self.assertEqual(self.R["svgH"], 20 * 26)
        self.assertEqual(self.R["svgW"], 8 * 2 + 14 * 10)   # 20 lanes capped at 14, spacing 10
        self.assertEqual((self.R["svgHead"], self.R["svgPaths"]), (1, 4))

    def test_list_chips(self):
        h = self.R["list"]
        self.assertIn('<i class="brf brl brh" title="main">main</i>', h)
        self.assertIn('<i class="brf brm" title="origin/f">origin/f</i>', h)
        self.assertEqual(h.count("brfh"), 1)
        d = self.R["listDet"]
        self.assertNotIn("brl brh", d)                     # detached: the sha chip is not marked as head branch
        self.assertIn('<s title="홍길동/팀/역할">홍길동</s>', d)

    def test_known_server_errors_mapped(self):
        self.assertEqual(self.R["msgErr"], ["Unreadable path — Not a git repository", "Timed out"])

    def test_chip_cap(self):
        h = self.R["listMany"]
        self.assertEqual(h.count('class="brf brl'), 6)      # capped; the subject stays in the row
        self.assertIn('<i class="brf brmore" title="t6, t7, t8">+3</i>', h)
        self.assertIn("<b>subj</b>", h)


class _Res:
    def __init__(self, rc, out):
        self.returncode, self.stdout = rc, out


class BranchUnborn(unittest.TestCase):
    """sidereus/git.py _br_unborn: HEAD on a branch without commits is not detached. Fake `run`, no git."""
    def test_unborn_branch(self):
        g = sidereus("git")
        self.assertEqual(g._br_unborn(lambda a: _Res(0, "main\n")), "main")
        self.assertEqual(g._br_unborn(lambda a: _Res(1, "")), "")     # real detached HEAD

    def test_timeout_is_not_unborn(self):
        g = sidereus("git")

        def boom(a):
            raise subprocess.TimeoutExpired(a, 1)
        self.assertEqual(g._br_unborn(boom), "")


if __name__ == "__main__":
    unittest.main()
