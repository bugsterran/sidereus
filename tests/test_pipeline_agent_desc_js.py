"""Pipelines agent descriptions: result-pane agent buttons show the task line (48k plWatchPane, 48b plLabParts/plLabDesc),
the card and pane header show the agent file's `desc` (48d plAgDesc · plNodeHtml) only when present, always escaped."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

PRE = """
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s, TV = o => o.msg, ago = s => s + 's', plStrip = s => s, PL_DESC_RE = /\\[pl:[^\\]]*\\]\\s*/g;
const PL_MK = {run: '*', wait: '-'}, PL_JUDGED = [], PL_LOW = [], PL_OUTCOME = {};
let PLS = {proj: '/w/a', data: {'/w/a': {agents: [{name: 'impl', desc: 'Writes <b>x code'}, {name: 'bare'}]}}};
function plgShow(t){ return t; } function plgFam(){ return 'x'; } function plgHue(){ return ''; } function plFlagChips(){ return []; }
function plOc(s){ return s; } function plEvLine(){ return ''; } function plEvRows(){ return []; } function plEvCommits(){ return []; }
function plStageRows(){ return [{st: 'run', n: 2}]; } function plWatchDef(){ return null; }
const NODES = {};
function plgNode(G, id){ return NODES[id]; }
function plStageAgents(){ return [{tid: 't1', lab: 'sidereus-implementer: [pl:x/y] fix <b>x', run: 1, sec: 5}, {tid: 't2', lab: 'main: [pl:x/y]'}]; }
"""
FNS = ("plLabParts", "plLabDesc", "plLabTip", "plAgDesc", "plWatchPane", "plNodeHtml")


def run(body):
    src = PRE + "\n".join(js_fn(f) for f in FNS) + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));"
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


PANE = ("NODES.a = {title: 'S', agent: 'impl', model: 'opus'}; NODES.b = {title: 'S', agent: 'bare'};"
        "const lt = {S: {}}, lv = {sid: 's1'};"
        "R.a = plWatchPane({sel: {k: 'n', id: 'a'}}, {}, lv, lt); R.b = plWatchPane({sel: {k: 'n', id: 'b'}}, {}, lv, lt);")
CARD = ("const E = {G: {defaults: {model: 'sonnet'}, loops: []}};"
        "R.a = plNodeHtml(E, {id: 'a', title: 'S', agent: 'impl', ui: {x: 0, y: 0}}, false, null);"
        "R.b = plNodeHtml(E, {id: 'b', title: 'S', agent: 'bare', ui: {x: 0, y: 0}}, false, null);")


@unittest.skipUnless(shutil.which("node"), "node missing")
class AgentDesc(unittest.TestCase):
    def test_R1_agent_button_shows_task_escaped(self):
        a = run(PANE)["a"]
        self.assertIn("sidereus-implementer<span class=plwad>fix &lt;b>x</span>", a)
        self.assertIn("main<span class=plwad>orchestrator</span>", a)
        self.assertNotIn("<b>x", a)

    def test_R2_pane_header_desc_only_when_present(self):
        R = run(PANE)
        self.assertIn('<small class=plphd title="Writes &lt;b>x code">Writes &lt;b>x code</small>', R["a"])
        self.assertNotIn("plphd", R["b"])

    def test_R2_card_desc_only_when_present(self):
        R = run(CARD)
        self.assertIn('<div class=plnad title="Writes &lt;b>x code">Writes &lt;b>x code</div>', R["a"])
        self.assertNotIn("plnad", R["b"])

    def test_no_pls_no_desc(self):
        self.assertEqual(run("PLS = undefined; R.d = plAgDesc('impl');")["d"], "")


if __name__ == "__main__":
    unittest.main()
