"""Work tabs (web/js/65-worktabs.js wtFetch): the poll and tab clicks can start two requests for one tab, so a slow
older reply landing last must not paint over the newer one, and the request carries a timeout instead of the 120 s
getJSON default. getJSON is a set of deferred promises; no DOM."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

PRE = """
let agentData = null, wtFocus = 'k';
const wtData = {}, PAINTS = [], OPTS = [], PEND = [];
function T(s){ return s; }
function wtShown(){ return ['k']; }
function wtKeyOf(x){ return x; }
function workUrl(cwd, tid){ return '/api/ext/work?tid=' + tid; }
function getJSON(url, opts){ OPTS.push(opts || null); return new Promise((res, rej) => PEND.push({res, rej})); }
function agentRepaint(){ PAINTS.push(agentData && agentData.v); }
function buildMv(){}
const tick = async () => { for(let i = 0; i < 5; i++) await new Promise(r => process.nextTick(r)); };
"""


def run(body):
    src = js_all()
    for name in ("wtBusy", "wtSeq"):
        if re.search(r"^const %s = " % name, src, re.M) is None:
            raise AssertionError("65-worktabs.js: %s missing" % name)
    decl = "\n".join(re.search(r"^const %s = .*$" % n, src, re.M).group(0) for n in ("wtBusy", "wtSeq"))
    js = PRE + decl + "\n" + js_fn("workGetJSON") + "\n" + js_fn("wtFetch") + "\nconst R = {};\n(async () => {" + body + \
        "\nprocess.stdout.write(JSON.stringify(R)); })();"
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node missing")
class WorkTabFetchSeq(unittest.TestCase):
    def test_older_reply_landing_last_does_not_paint(self):
        out = run("""
            const t = {key: 'k', cwd: '/w', tid: 'a1'};
            wtFetch(t); wtFetch(t);
            PEND[1].res({ok: true, v: 'new'}); await tick();
            PEND[0].res({ok: true, v: 'old'}); await tick();
            R.data = wtData.k.v; R.paints = PAINTS;
        """)
        self.assertEqual(out, {"data": "new", "paints": ["new"]})

    def test_request_has_a_timeout(self):
        out = run("""
            wtFetch({key: 'k', cwd: '/w', tid: 'a1'});
            R.opts = OPTS;
        """)
        self.assertEqual(out["opts"], [{"timeout": 15000}])


if __name__ == "__main__":
    unittest.main()
