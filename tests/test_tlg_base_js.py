"""Timeline «Changes» chip baseline (77 tlgBase · tlgBaseSet · tlgBaseTip · tlgFetch, 90 cfgPaneTl «Changes baseline»):
default base=head in the fetch URL, the setting's options, a change busts the per-cwd cache and refetches at the new base."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

PRE = r"""
const T = s => s, TV = j => j.msg.replace(/\{(\w+)\}/g, (a, k) => String(j.vars[k]));
const R = {urls: [], saved: {}, paints: 0};
let STORE = {}, mainView = 'time';
const lsGet = (k, d) => k in STORE ? STORE[k] : d, lsSet = (k, v) => { R.saved[k] = v; };
const TG = {cwd: '/r/a', ck: '/r/a', sid: 's1'};
function tlgTarget(){ return TG; } function tlgPaint(){ R.paints++; }
function getJSON(u){ R.urls.push(u); return {then: () => ({then: () => 0})}; }
"""


def run(body, store=None):
    src = js_all()
    consts = "\n".join(re.search(p, src, re.M).group(0) for p in (r"^const TLG_TTL_S = .*$", r"^const tlgC = .*$",
                                                                  r"^const TLG_BASES = .*$", r"^let tlgBase = .*$"))
    fns = "\n".join(js_fn(n) for n in ("tlgBaseSet", "tlgBaseTip", "tlgFetch"))
    js = (PRE + "STORE = " + json.dumps(store or {}) + ";\n" + consts + "\n" + fns + "\n" + body
          + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlgBase(unittest.TestCase):
    def test_default_fetch_is_head_with_sid(self):
        r = run("tlgFetch(TG, true); R.base = tlgBase;")
        self.assertEqual(r["base"], "head")
        self.assertEqual(r["urls"], ["/api/git/diff?view=rail&cwd=%2Fr%2Fa&base=head&sid=s1"])

    def test_stored_and_invalid_pref(self):
        self.assertEqual(run("R.base = tlgBase;", {"sidereus.tlgbase": "remote"})["base"], "remote")
        self.assertEqual(run("R.base = tlgBase;", {"sidereus.tlgbase": "x;evil"})["base"], "head")

    def test_options_match_rail_modes(self):
        r = run("R.opts = TLG_BASES.map(x => x[0]);")
        self.assertEqual(r["opts"], ["head", "upstream", "start", "remote", "auto"])
        pane = js_fn("cfgPaneTl")
        self.assertIn("sel('tgb', T('Changes baseline'), TLG_BASES.map(", pane)
        self.assertIn("tgb:  v => tlgBaseSet(v)", js_all())

    def test_change_busts_cache_and_refetches(self):
        r = run("tlgFetch(TG, true); tlgC['/r/a'].busy = false; tlgC['/r/a'].at = Date.now(); tlgFetch(TG);"   # cached: no second call
                "tlgBaseSet('upstream'); R.keys = Object.keys(tlgC); tlgBaseSet('bogus'); R.base = tlgBase;")
        self.assertEqual(r["urls"], ["/api/git/diff?view=rail&cwd=%2Fr%2Fa&base=head&sid=s1",
                                     "/api/git/diff?view=rail&cwd=%2Fr%2Fa&base=upstream&sid=s1"])
        self.assertEqual((r["base"], r["saved"], r["keys"]), ("upstream", {"sidereus.tlgbase": "upstream"}, ["/r/a"]))

    def test_tip_names_baseline(self):
        r = run("R.t = [tlgBaseTip({ok: true, baseKind: 'head', baseMode: 'head', branch: 'dev'}),"
                "tlgBaseTip({ok: true, baseKind: 'branch', baseMode: 'remote', baseRef: 'origin/main', base: 'abc1234def', nCommits: 3}),"
                "tlgBaseTip({ok: true, baseKind: 'head', baseMode: 'start', branch: 'dev'}), tlgBaseTip({ok: false})];")
        self.assertEqual(r["t"][0], "Compared with: uncommitted changes on dev")
        self.assertEqual(r["t"][1], "Compared with: the default branch origin/main (merge-base abc1234), 3 commits")
        self.assertIn("No such baseline here", r["t"][2])
        self.assertEqual(r["t"][3], "")


if __name__ == "__main__":
    unittest.main()
