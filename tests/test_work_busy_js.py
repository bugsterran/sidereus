"""Work-log fetch rides out 503 (peer check undetermined under load): wtFetch shows the busy note, backs off and ends
with the data; 403 is not retried by the backoff. getJSON, timers and the tab state are faked."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

FNS = ("workGetJSON", "wtFetch")

PRE = """
const T = s => s;
let REPLIES = [], URLS = [], WAITS = [], PAINTS = [];
function getJSON(url){
  URLS.push(url);
  const r = REPLIES.shift();
  if(typeof r === 'number'){ const e = new Error('HTTP ' + r); e.status = r; return Promise.reject(e); }
  return Promise.resolve(r);
}
const TIMERS = [];
function setTimeout(f, ms){ WAITS.push(ms); TIMERS.push(f); return 0; }
let wtData = {}, agentData = null, wtFocus = 'k';
const wtBusy = new Set();
function workUrl(cwd, tid){ return '/api/session/work?cwd=' + cwd; }
function wtKeyOf(x){ return x; }
function wtShown(){ return ['k']; }
function agentRepaint(){ PAINTS.push(agentData && (agentData.msg || (agentData.ok && 'data'))); }
function buildMv(){}
async function drain(){ for(let i = 0; i < 50; i++){ await new Promise(r => process.nextTick(r)); if(TIMERS.length) TIMERS.shift()(); } }
"""


def run(body):
    src = PRE + "\n".join(js_fn(f) for f in FNS) + "\nconst R = {};\n(async () => {" + body + \
        "\nprocess.stdout.write(JSON.stringify(R)); })();"
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node missing")
class WorkBusy(unittest.TestCase):
    def test_503_then_200_shows_data(self):
        r = run("REPLIES = [503, 503, {ok: true, steps: []}]; wtFetch({key: 'k', cwd: '/w'}); await drain();"
                "R.data = wtData.k; R.waits = WAITS; R.paints = PAINTS; R.busy = wtBusy.size;")
        self.assertEqual(r["data"], {"ok": True, "steps": []})
        self.assertEqual(r["waits"], [2000, 4000])
        self.assertIn("Viewer is busy — retrying…", r["paints"])
        self.assertEqual(r["paints"][-1], "data")
        self.assertEqual(r["busy"], 0)

    def test_503_gives_up_after_four_retries(self):
        r = run("REPLIES = [503, 503, 503, 503, 503]; wtFetch({key: 'k', cwd: '/w'}); await drain();"
                "R.msg = wtData.k.msg; R.waits = WAITS; R.n = URLS.length;")
        self.assertEqual(r["waits"], [2000, 4000, 8000, 16000])
        self.assertEqual(r["n"], 5)
        self.assertIn("HTTP 503", r["msg"])

    def test_403_not_backed_off(self):
        r = run("REPLIES = [403, 403]; wtFetch({key: 'k', cwd: '/w'}); await drain();"
                "R.msg = wtData.k.msg; R.waits = WAITS;")
        self.assertEqual(r["waits"], [900])
        self.assertIn("HTTP 403", r["msg"])

    def test_second_fetch_during_backoff_is_skipped(self):
        r = run("REPLIES = [503, {ok: true}]; wtFetch({key: 'k', cwd: '/w'});"
                "for(let i = 0; i < 5; i++) await new Promise(x => process.nextTick(x));"
                "wtFetch({key: 'k', cwd: '/w'}); await drain(); R.n = URLS.length; R.data = wtData.k;")
        self.assertEqual(r["n"], 2)
        self.assertEqual(r["data"], {"ok": True})


if __name__ == "__main__":
    unittest.main()
