"""Work-log refresh (web/js/35b-worklog-view.js refreshAgent): the 2.5s tick and the 15s poll both call it, so a tick is
skipped while the same URL is in flight, a switch to another log still fetches at once, and an older reply landing last
never paints over a newer one. getJSON is a set of deferred promises; no DOM."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

PRE = """
let agentTid = 'a1', agentCwd = '/w', agentData = null, wkOn = true, wtFocus = 'k', agPromptOpen = false, agTreeOpen = false;
const wtData = {}, agWroteOpen = new Set(), agWroteShut = new Set(), PAINTS = [], URLS = [], PEND = [];
function wtShown(){ return ['k']; }
function workUrl(cwd, tid){ return '/api/agent/work?tid=' + tid; }
function getJSON(url){ URLS.push(url); return new Promise((res, rej) => PEND.push({url, res, rej})); }
function agentSig(d){ return d ? d.v : ''; }
function agBox(){ return null; }
function agEditHarvest(){}
function wtKeyOf(x){ return x; }
function agentRepaint(){ PAINTS.push(agentData.v); }
const tick = async () => { for(let i = 0; i < 5; i++) await new Promise(r => process.nextTick(r)); };
"""


def run(body):
    m = re.search(r"^let agSeq = 0, agBusyUrl = '';$", js_all(), re.M)
    if m is None:
        raise AssertionError("35b-worklog-view.js: agSeq/agBusyUrl guard missing")
    src = PRE + m.group(0) + "\n" + js_fn("refreshAgent") + "\nconst R = {};\n(async () => {" + body + \
        "\nprocess.stdout.write(JSON.stringify(R)); })();"
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node missing")
class RefreshSeq(unittest.TestCase):
    def test_tick_skipped_while_same_url_in_flight(self):
        r = run("refreshAgent(); refreshAgent(); refreshAgent(); R.n = URLS.length;"
                "PEND[0].res({v: 'x'}); await tick(); refreshAgent(); R.after = URLS.length; R.paints = PAINTS;")
        self.assertEqual(r["n"], 1)
        self.assertEqual(r["after"], 2)
        self.assertEqual(r["paints"], ["x"])

    def test_failed_reply_releases_the_guard(self):
        r = run("refreshAgent(); PEND[0].rej(new Error('HTTP 500')); await tick(); refreshAgent(); R.n = URLS.length;")
        self.assertEqual(r["n"], 2)

    def test_switch_fetches_at_once_and_stale_reply_is_ignored(self):
        # a1 in flight -> switch to a2 (fetches now) -> a2 answers, then the old a1 reply lands last.
        r = run("refreshAgent(); agentTid = 'a2'; refreshAgent(); R.n = URLS.length;"
                "PEND[1].res({v: 'new'}); await tick(); agentTid = 'a1'; agentData = {v: 'new'};"
                "PEND[0].res({v: 'old'}); await tick(); R.paints = PAINTS; R.data = agentData.v;")
        self.assertEqual(r["n"], 2)
        self.assertEqual(r["paints"], ["new"])
        self.assertEqual(r["data"], "new")

    def test_older_reply_for_same_view_after_newer_is_dropped(self):
        # a1 -> a2 -> back to a1 while the first a1 request is still pending: it lands last with older data.
        r = run("refreshAgent(); agentTid = 'a2'; refreshAgent(); agentTid = 'a1'; refreshAgent(); R.n = URLS.length;"
                "PEND[2].res({v: 'new'}); await tick(); PEND[0].res({v: 'old'}); PEND[1].res({v: 'a2'}); await tick();"
                "R.paints = PAINTS; R.data = agentData.v;")
        self.assertEqual(r["n"], 3)
        self.assertEqual(r["paints"], ["new"])
        self.assertEqual(r["data"], "new")


if __name__ == "__main__":
    unittest.main()
