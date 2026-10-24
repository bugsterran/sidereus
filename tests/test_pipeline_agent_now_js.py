"""Pipelines result pane: a running stage agent shows «tool · elapsed» from its live SESS sub row (48k plAgNowLine),
tool name only — never the « · description» suffix or any tool input (rule 1)."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

PRE = """
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s, TV = o => o.msg, ago = s => s + 's', plStrip = s => s, PLNOW_QUIET = 120, PL_DESC_RE = /\\[pl:[^\\]]*\\]\\s*/g;
const PL_MK = {run: '*', wait: '-'};
let PLS = {proj: '/w/a', data: {}}, SESS = [], AGS = [];
function plgShow(t){ return t; } function plOc(s){ return s; } function plEvLine(){ return ''; } function plEvRows(){ return []; }
function plEvCommits(){ return []; } function plStageRows(){ return [{st: 'run', n: 1}]; } function plWatchDef(){ return null; }
function plgNode(){ return {title: 'S', agent: ''}; } function plAgDesc(){ return ''; }
function plStageAgents(){ return AGS; }
const pane = () => plWatchPane({sel: {k: 'n', id: 'a'}}, {}, {sid: 's1'}, {S: {}});
"""
FNS = ("plLabParts", "plLabDesc", "plLabTip", "subWorkId", "plAgNowLine", "plWatchPane")
AID = "a0123456789abcdef"


def run(body):
    src = PRE + "\n".join(js_fn(f) for f in FNS) + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));"
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def pane(subs, ags):
    return run("SESS = [{sid: 's1', sub: %s}]; AGS = %s; R.h = pane();" % (json.dumps(subs), json.dumps(ags)))["h"]


AG = {"id": AID, "tid": AID, "run": True, "lab": "general-purpose: [pl:x/y] task", "sec": 5}


@unittest.skipUnless(shutil.which("node"), "node missing")
class AgentNow(unittest.TestCase):
    def test_R1_tool_and_elapsed_by_aid(self):
        h = pane([{"aid": AID, "tid": "toolu_1", "now": "Bash", "idle": 12}], [AG])
        self.assertIn("<span class=plwan>Bash · 12s</span></button>", h)

    def test_R1_tid_only_match(self):
        ag = dict(AG, id="toolu_9", tid="toolu_9")
        h = pane([{"aid": "", "tid": "toolu_9", "now": "Bash", "idle": 12}], [ag])
        self.assertIn("<span class=plwan>Bash · 12s</span>", h)

    def test_R2_name_only_no_input_anywhere(self):
        for now in ("Agent · secret desc", "Bash · rm -rf /x"):
            h = pane([{"aid": AID, "now": now, "idle": 3}], [AG])
            self.assertIn("<span class=plwan>%s · 3s</span>" % now.split(" · ")[0], h)
            for bad in ("secret", "rm -rf", "/x"):
                self.assertNotIn(bad, h)
            self.assertNotRegex(h, r'class=plwan[^>]*title')

    def test_R3_idle_line(self):
        h = pane([{"aid": AID, "now": "Bash", "idle": 300}], [AG])
        self.assertIn("<span class=plwan>Idle · 300s</span>", h)

    def test_R3_busy_tool_is_not_idle(self):
        h = pane([{"aid": AID, "now": "Bash", "idle": 300, "busy": 1}], [AG])
        self.assertIn("<span class=plwan>Bash · 300s</span>", h)

    def test_R3_no_line_when_done_missing_or_main(self):
        sub = [{"aid": AID, "now": "Bash", "idle": 1}]
        self.assertNotIn("plwan", pane(sub, [dict(AG, run=False)]))
        self.assertNotIn("plwan", pane([], [AG]))
        self.assertNotIn("plwan", pane(sub, [dict(AG, id="main", tid="", lab="main: [pl:x/y]")]))

    def test_R4_row_attributes_unchanged(self):
        h = pane([{"aid": AID, "now": "Bash", "idle": 12}], [AG])
        m = re.search(r'<button type=button class=plwa data-plwsid="s1" data-plwtid="%s" title="[^"]*">' % AID, h)
        self.assertTrue(m, h)


if __name__ == "__main__":
    unittest.main()
