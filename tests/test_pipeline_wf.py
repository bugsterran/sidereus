"""«Workflow» view of the pipeline tab (web/js/48g-pipeline-wf.js) + the «Workflow» badge on workflow-agent rows (40b, 70).
Pure functions under node with stubbed helpers; SESS is a fixture, never live data."""
import json
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

STUB = ("var LANG = 'ko'; const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/\"/g, '&quot;');"
        " const T = s => s; const KE = (k, e) => k; const U = (n, u) => n + u; const ago = s => s + 's'; const wfFold = new Set();\n")


def _js(expr, sess, *fns):
    src = STUB + "var SESS = %s;\n" % json.dumps(sess) + "\n".join(js_fn(f) for f in ("plStrip",) + fns) + "\nconsole.log(JSON.stringify(" + expr + "));"
    return json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True).stdout)


def _ag(phase, st, lab, start=100, end=200):
    return {"aid": lab, "lab": lab, "phase": phase, "st": st, "start": start, "end": end, "tok": 0}


RUN = {"id": "wf_1", "name": "sidereus-ux-sample", "run": True, "start": 100, "end": 400, "tok": 342200,
       "phases": ["Scan", "Review", "Report"],
       "agents": [_ag("Scan", "done", "scan a"), _ag("Scan", "done", "scan b"), _ag("Review", "run", "review"), _ag("Review", "fail", "review 2")]}
SESS = [{"sid": "s1", "cwd": "/p", "wf": [RUN, {"id": "wf_0", "name": "pipeline", "run": True, "agents": []}]},
        {"sid": "s2", "cwd": "/q", "wf": [dict(RUN, id="wf_2")]}]


class Light(unittest.TestCase):
    def test_states(self):
        L = _js("wfLight(%s)" % json.dumps(RUN), [], "wfLight", "wfStages")
        self.assertEqual({k: v["st"] for k, v in L.items()}, {"Scan": "done", "Review": "run", "Report": "wait"})
        self.assertEqual(L["Scan"]["n"], 2)
        L = _js("wfLight(%s)" % json.dumps(dict(RUN, run=False)), [], "wfLight", "wfStages")
        self.assertEqual(L["Review"]["st"], "fail")                          # finished run: a failed agent wins

    def test_cut_agent_is_fail(self):
        run = dict(RUN, run=False, agents=[_ag("Scan", "done", "a"), _ag("Scan", "cut", "b")])
        self.assertEqual(_js("wfLight(%s).Scan.st" % json.dumps(run), [], "wfLight", "wfStages"), "fail")

    def test_phases_fallback_from_agents(self):
        run = dict(RUN, agents=[_ag("B", "done", "x"), _ag("A", "done", "y"), _ag("B", "done", "z")])
        del run["phases"]
        self.assertEqual(_js("wfStages(%s)" % json.dumps(run), [], "wfStages"), ["B", "A"])
        self.assertEqual(_js("wfStages(%s)" % json.dumps(dict(RUN, phases=["A"], agents=[_ag("C", "run", "c")])), [], "wfStages"), ["A", "C"])

    def test_pipeline_runs_excluded(self):
        out = _js("wfProjRuns('/p').map(o => [o.sid, o.run.id])", SESS, "wfProjRuns", "wfAll")
        self.assertEqual(out, [["s1", "wf_1"]])                              # other cwd and the pipeline runner left out

    def test_history_runs_listed_after_live(self):
        sess = [dict(SESS[0], wfh=[dict(RUN, id="wf_old", run=False, end=50)])]
        out = _js("wfProjRuns('/p').map(o => [o.run.id, o.run.run])", sess, "wfProjRuns", "wfAll")
        self.assertEqual(out, [["wf_1", True], ["wf_old", False]])           # `wfh` (sessions._wf_sets) shows as done

    def test_summary_done_total(self):
        s = _js("wfSum(%s, 446)" % json.dumps(RUN), [], "wfSum")
        self.assertEqual((s["done"], s["total"], s["sec"], s["tok"]), (2, 4, 346, 342200))
        s = _js("wfSum(%s, 999)" % json.dumps(dict(RUN, run=False, tok=0)), [], "wfSum")
        self.assertEqual((s["sec"], s["tok"]), (300, 0))                     # finished: end - start


class Badge(unittest.TestCase):
    def test_timeline_workflow_agent_row_has_badge(self):
        g = {"type": "Review", "items": [{"tid": "wfa:review|s1", "par": "wf:wf_1", "aid": "review", "desc": "review"}]}
        plain = {"type": "sidereus-implementer", "items": [{"tid": "toolu_1", "aid": "a1", "desc": "slice s1"}]}
        h = _js("[tlAgNm(%s, true), tlAgNm(%s, true)]" % (json.dumps(g), json.dumps(plain)), SESS, "tlAgNm", "tlAgLab", "wfBadge", "wfRunNameOf", "wfAll")
        self.assertIn('title="Workflow · sidereus-ux-sample · Review">Workflow</i>', h[0])
        self.assertNotIn("Workflow", h[1])

    def test_session_tree_workflow_agent_has_badge(self):
        h = _js("sessWfHtml([%s])" % json.dumps(RUN), [], "sessWfHtml", "wfLine", "wfBar", "fmtTok", "wfBadge")
        self.assertEqual(h.count("wfbdg"), 4)
        self.assertIn('title="Workflow · sidereus-ux-sample · Scan"', h)


if __name__ == "__main__":
    unittest.main()
