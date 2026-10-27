"""Workflow agents open their own work log: session tree rows (40b sessWfHtml), the pipeline Workflow table (48g wfBody)
and timeline `wfa:` rows (76 tlOpen) carry/forward the agent id."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

STUB = ("const esc = s => String(s); const T = s => s; const U = (n, u) => n + u; const fmtTok = n => String(n);"
        " const plStrip = s => String(s || ''); const wfFold = new Set(); const ago = s => s + 's'; const sid8 = s => s;"
        " const WF_ST = {run: ['Running', 'r'], done: ['Done', 'd']};"
        " const wfFind = () => ({r: {id: 'wf_1', name: 'n', agents: AG}}); const wfLight = () => ({});"
        " const wfSumHtml = () => ''; const wfStages = () => []; const OPEN = [];"
        " const openAgent = (c, t) => OPEN.push(['agent', c, t]); const openSession = (c, t) => OPEN.push(['sess', c, t]);"
        " const AG = [{aid: 'a1234567', lab: 'x', st: 'done', start: 1, end: 2}, {aid: '../evil', lab: 'y', st: 'done'}];\n")


def _js(body):
    src = STUB + "\n".join(js_fn(n) for n in ("wfLine", "sessWfHtml", "wfBody", "tlOpen", "subWorkId", "agRowOpen")) + "\n" + body
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class WfAgentOpen(unittest.TestCase):
    def test_session_tree_rows_clickable_by_aid(self):
        h = _js("console.log(JSON.stringify(sessWfHtml([{id: 'wf_1', start: 1, end: 2, agents: AG}])));")
        self.assertIn('agh" data-tid="a1234567"', h)
        self.assertNotIn('data-tid="../evil"', h)   # off-pattern ids get no click target

    def test_pipeline_table_rows_carry_aid(self):
        h = _js("console.log(JSON.stringify(wfBody('s1', 'wf_1')));")
        self.assertIn('data-wfw="s1" data-tid="a1234567"', h)
        self.assertNotIn('../evil', h.split('data-tid')[-1].split('>')[0])

    def test_timeline_opens_wfa_by_aid(self):
        o = _js("tlOpen('/w', 'wfa:a1234567|sid1'); tlOpen('/w', 'wf:wf_1|sid1'); console.log(JSON.stringify(OPEN));")
        self.assertEqual(o, [["agent", "/w", "a1234567|sid1"]])

    def test_tree_click_resolves_session(self):   # card text holds no session id; data-scwd/ssid or x.wf agents do
        o = _js("const SESS = [{sid: 's0', cwd: '/o', sub: []}, {sid: 's1', cwd: '/w', wf: [{agents: AG}]}];"
                "const row = {getAttribute: k => ({'data-ssid': 's1', 'data-scwd': '/w'})[k]};"
                "console.log(JSON.stringify([agRowOpen(null, 'a1234567'), agRowOpen(row, 'a1234567'), agRowOpen(null, 'a7654321')]));")
        self.assertEqual(o[0], {"cwd": "/w", "tid": "a1234567|s1"})
        self.assertEqual(o[1], {"cwd": "/w", "tid": "a1234567|s1"})
        self.assertEqual(o[2], {"cwd": "", "tid": "a7654321"})


if __name__ == "__main__":
    unittest.main()
