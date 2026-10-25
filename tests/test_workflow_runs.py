"""Workflow-tool runs: agents under <session>/subagents/workflows/wf_<id>/ are scanned, grouped per run, counted in
token paths, and the journal's result text never reaches a payload (AGENTS.md rule 1)."""
import json
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

from tests import _clock
from tests._clock import NOW
from tests._load import load, sidereus

load()
ag = sidereus("agents")
S = sidereus("sessions")
T = sidereus("timeline")
UI = sidereus("usage_index")
CL = sidereus("commit_link")
FS = sidereus("failures_scan")

SECRET = "TOP-SECRET-REPORT-TEXT"
SID = "0f0f0f0f-1111-2222-3333-444455556666"


def _iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))


def _usage_line(t, mid, n):
    return json.dumps({"type": "assistant", "timestamp": _iso(t), "requestId": "r" + mid,
                       "message": {"id": mid, "role": "assistant", "model": "claude-opus-4-1",
                                   "usage": {"input_tokens": n, "output_tokens": 0, "cache_read_input_tokens": 0,
                                             "cache_creation_input_tokens": 0},
                                   "content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "/x"}}]}},
                      separators=(",", ":")) + "\n"   # compact, like real transcripts (the token regex expects it)


class WorkflowRuns(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sidereus-wf-")
        self.proj = os.path.join(self.root, "-Users-demo-repo")
        self.sd = os.path.join(self.proj, SID)
        self.rd = os.path.join(self.sd, "subagents", "workflows", "wf_abc123-d10")
        os.makedirs(self.rd)
        now = NOW
        with open(self.sd + ".jsonl", "w", encoding="utf-8") as f:        # parent transcript: the launch result names the script
            f.write(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "content":
                    "Transcript dir: %s\nScript file: /repo/.claude/workflows/sidereus-change.js\nRun ID: wf_abc123-d10"
                    % self.rd}]}}) + "\n")
        os.makedirs(os.path.join(self.sd, "subagents"), exist_ok=True)
        with open(os.path.join(self.sd, "subagents", "agent-aplain.jsonl"), "w", encoding="utf-8") as f:
            f.write(_usage_line(now - 50, "p1", 7))
        jr = [{"type": "launched"},
              {"type": "failed", "key": "k0", "agentId": ""},
              {"type": "started", "key": "k1", "agentId": "a1", "label": "design", "phase": "Design"},
              {"type": "result", "key": "k1", "agentId": "a1", "result": {"summary": SECRET}},
              {"type": "started", "key": "k2", "agentId": "a2", "label": "impl s1", "phase": "Implement"},
              {"type": "started", "key": "k3", "agentId": "a3", "label": "impl s2", "phase": "Implement"},
              {"type": "failed", "key": "k3", "agentId": "a3"}]
        with open(os.path.join(self.rd, "journal.jsonl"), "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(e) + "\n" for e in jr))
        for i, aid in enumerate(("a1", "a2", "a3")):
            with open(os.path.join(self.rd, "agent-%s.jsonl" % aid), "w", encoding="utf-8") as f:
                f.write(_usage_line(now - 100 + i, "m" + aid, 100 * (i + 1)))
            with open(os.path.join(self.rd, "agent-%s.meta.json" % aid), "w", encoding="utf-8") as f:
                json.dump({"agentType": "general-purpose", "description": "meta " + aid, "workflowPhase": "X"}, f)
        ag._WF_NAME.clear()
        ag._WF_JOURNAL.clear()
        self.files = {aid: os.path.join(self.rd, "agent-%s.jsonl" % aid) for aid in ("a1", "a2", "a3")}
        for dp, _, fs in os.walk(self.root):        # liveness is mtime vs now: stamp the fixture at _clock.NOW
            for n in fs:
                os.utime(os.path.join(dp, n), (NOW, NOW))
        clk = _clock.frozen(ag, S, T, UI, CL, FS, WM, sidereus("attention"))
        clk.__enter__()
        self.addCleanup(clk.__exit__, None, None, None)
        # ⚠boot_time() reads the live kern.boottime; a fixture stamped at _clock.NOW predates it and reads as orphaned
        boot, ag.boot_time = ag.boot_time, (lambda: 0.0)
        self.addCleanup(setattr, ag, "boot_time", boot)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        ag._WF_NAME.clear()
        ag._WF_JOURNAL.clear()

    def test_paths_cover_both_layouts_without_overlap(self):
        got = sorted(ag.sub_paths(self.root))
        self.assertEqual(len(got), len(set(got)))
        self.assertEqual(sorted(os.path.basename(p) for p in got),
                         ["agent-a1.jsonl", "agent-a2.jsonl", "agent-a3.jsonl", "agent-aplain.jsonl"])
        for p in got:
            self.assertEqual(ag.sub_sess_dir(p), self.sd)
        self.assertEqual(ag.sub_sess_dir(self.sd + ".jsonl"), "")

    def test_scans_include_workflow_agents(self):
        with mock.patch.object(UI, "CLAUDE_PROJECTS", self.root):
            idx = dict(UI._uidx_paths())
        self.assertEqual(idx[self.files["a2"]], "-Users-demo-repo")   # project slug, not the session id
        with mock.patch.object(CL, "CL_ROOT", self.root):
            self.assertIn(self.files["a3"], CL._cl_paths())
        self.assertEqual(FS._fail_sub_id(self.files["a1"]), (self.sd, "a1"))
        self.assertEqual(sorted(ag.wf_agent_files(self.sd)), sorted(self.files.values()))

    def test_run_grouping_progress_and_name(self):
        tok = {self.files["a1"]: 10, self.files["a2"]: 20, self.files["a3"]: 5}
        runs = ag.wf_runs(self.sd, tokf=tok.get)
        self.assertEqual(len(runs), 1)
        r = runs[0]
        self.assertEqual((r["id"], r["name"], r["phase"]), ("wf_abc123-d10", "sidereus-change", "Implement"))
        self.assertEqual((r["done"], r["fail"], r["total"], r["tok"]), (1, 1, 3, 35))
        self.assertTrue(r["run"])
        self.assertEqual([(a["lab"], a["phase"], a["st"]) for a in r["agents"]],
                         [("design", "Design", "done"), ("impl s1", "Implement", "run"), ("impl s2", "Implement", "fail")])

    def test_name_drops_run_id_suffix_of_saved_script(self):
        with open(self.sd + ".jsonl", "w", encoding="utf-8") as f:        # saved-script launch: <sess>/workflows/scripts/<name>-<run_id>.js
            f.write(json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "content":
                    "Transcript dir: %s\nScript file: %s/workflows/scripts/sidereus-wf-livecheck-wf_abc123-d10.js\nRun ID: wf_abc123-d10"
                    % (self.rd, self.sd)}]}}) + "\n")
        ag._WF_NAME.clear()
        self.assertEqual(ag.wf_runs(self.sd)[0]["name"], "sidereus-wf-livecheck")

    def test_session_payload_is_metadata_only(self):
        idx = {"files": {self.files["a1"]: {"h": {"1": {"m": [1, 2, 3, 4]}}}}}
        with mock.patch.object(S, "_uidx", idx):
            rows = S._wf_sets(self.sd + ".jsonl", NOW, False)[0]
        blob = json.dumps(rows)
        self.assertNotIn(SECRET, blob)
        self.assertNotIn("_file", blob)
        self.assertNotIn(self.rd, blob)
        self.assertEqual(rows[0]["tok"], 10)
        self.assertEqual(S._wf_sets(self.sd + ".jsonl", NOW, True)[0], [])   # dead session: nothing running

    def test_finished_run_leaves_the_tree(self):
        old = NOW - 3600
        for p in list(self.files.values()) + [os.path.join(self.rd, "journal.jsonl")]:
            os.utime(p, (old, old))
        self.assertEqual(S._wf_sets(self.sd + ".jsonl", NOW, False)[0], [])

    def _age_all(self, t):
        for dp, _, fs in os.walk(os.path.join(self.sd, "subagents", "workflows")):
            for n in fs:
                os.utime(os.path.join(dp, n), (t, t))

    def test_finished_run_moves_to_history_for_six_hours(self):
        t0 = 1700000000.0
        self._age_all(t0)
        wf, wfh = S._wf_sets(self.sd + ".jsonl", t0 + 3600, False)
        self.assertEqual(wf, [])                                   # gone from tree / «실행 중» / attention
        self.assertEqual([(r["id"], r["run"]) for r in wfh], [("wf_abc123-d10", False)])
        self.assertNotIn(SECRET, json.dumps(wfh))
        self.assertNotIn("_file", json.dumps(wfh))
        self.assertEqual(S._wf_sets(self.sd + ".jsonl", t0 + ag.WF_HIST_S + 60, False), ([], []))
        wf, wfh = S._wf_sets(self.sd + ".jsonl", t0 + 60, False)  # just finished: short window only, not duplicated
        self.assertEqual(([r["id"] for r in wf], wfh), (["wf_abc123-d10"], []))

    def test_history_is_capped_newest_first_and_never_live(self):
        t0 = 1700000000.0
        for i in range(ag.WF_HIST_N + 2):
            shutil.copytree(self.rd, self.rd + "-%02d" % i)
            for n in os.listdir(self.rd + "-%02d" % i):
                os.utime(os.path.join(self.rd + "-%02d" % i, n), (t0 + i, t0 + i))
        for n in os.listdir(self.rd):
            os.utime(os.path.join(self.rd, n), (t0 - 10, t0 - 10))
        _, wfh = S._wf_sets(self.sd + ".jsonl", t0 + 3600, False)
        self.assertEqual(len(wfh), ag.WF_HIST_N)
        self.assertEqual(wfh[0]["id"], "wf_abc123-d10-%02d" % (ag.WF_HIST_N + 1))
        self.assertEqual([r["end"] for r in wfh], sorted((r["end"] for r in wfh), reverse=True))
        # dead session: nothing live, a fresh run is history and drawn as done
        self._age_all(t0 + 3590)
        wf, wfh = S._wf_sets(self.sd + ".jsonl", t0 + 3600, True)
        self.assertEqual(wf, [])
        self.assertTrue(wfh and not any(r["run"] for r in wfh))

    def test_pipeline_runner_runs_stay_out_of_history(self):
        t0 = 1700000000.0
        self._age_all(t0)
        with mock.patch.object(ag, "_wf_name", lambda sd, rd: "pipeline"):
            self.assertEqual(S._wf_sets(self.sd + ".jsonl", t0 + 3600, False), ([], []))

    def test_running_workflow_is_not_the_humans_turn(self):
        # Parent ended its turn (`wait`) right after the Workflow launch; the run is still live -> no "done" signal.
        att = sidereus("attention")
        now = NOW
        row = {"sid": SID, "cwd": "/Users/demo/repo", "state": "wait", "ageSec": 600, "sub": [], "bgs": [],
               "wf": S._wf_sets(self.sd + ".jsonl", now, False)[0]}
        self.assertTrue(row["wf"] and row["wf"][0]["run"])
        self.assertNotIn("done", [s["k"] for s in att._row_sigs(row, now)])
        # Same row once the run went quiet long ago: it is the human's turn again.
        old = now - 3600
        for p in list(self.files.values()) + [os.path.join(self.rd, "journal.jsonl")]:
            os.utime(p, (old, old))
        row["wf"] = S._wf_sets(self.sd + ".jsonl", now, False)[0]
        self.assertIn("done", [s["k"] for s in att._row_sigs(row, now)])

    def test_timeline_rows(self):
        rows = T._tl_wf_rows(self.sd, SID[:8], NOW - 3600, "repo", "/Users/demo/repo")
        run, kids = rows[0], rows[1:]
        self.assertEqual(run["kind"], "wf")
        self.assertNotIn("_tk", run)                                    # children carry the token list
        self.assertEqual(run["wf"]["done"], 1)
        self.assertEqual([k["desc"] for k in kids], ["design", "impl s1", "impl s2"])
        self.assertTrue(all(k["par"] == run["aid"] for k in kids))
        self.assertEqual(run["tk"], sum(k["tk"] for k in kids))
        self.assertGreater(run["tk"], 0)
        self.assertNotIn(SECRET, json.dumps(rows))


WM = sidereus("wf_meta")
BODY_SENTINEL = "SCRIPT-BODY-SENTINEL"


class WorkflowPhases(unittest.TestCase):
    """`phases` = declared meta titles of the saved script, then journal phases; nothing else from the script."""

    def setUp(self):
        WorkflowRuns.setUp(self)
        self.now = os.stat(self.files["a1"]).st_mtime + 5   # fixed relative to the fixture, not the clock
        self.sdir = os.path.join(self.sd, "workflows", "scripts")
        os.makedirs(self.sdir)
        WM._META_MEMO.clear()

    def tearDown(self):
        WorkflowRuns.tearDown(self)
        WM._META_MEMO.clear()

    def _script(self, text, name="my-flow"):
        with open(os.path.join(self.sdir, name + "-wf_abc123-d10.js"), "w", encoding="utf-8") as f:
            f.write(text)

    def _run(self):
        runs = ag.wf_runs(self.sd, now=self.now)
        self.assertEqual(len(runs), 1)
        return runs[0]

    def test_quoted_and_escaped_titles_exact(self):
        self._script("export const meta = {\n  name: 'x', // {not a brace}\n  description: 'it\\'s } tricky',\n"
                     "  phases: [\n    { title: 'Design', detail: '%s' },\n    { title: \"Ver\\\"ify `q`\" },\n"
                     "    { 'title': `Ship \\u00e9`, detail: { a: [1, 2] } },\n  ],\n}\n"
                     "const BODY = '%s'\n" % (BODY_SENTINEL, BODY_SENTINEL))
        r = self._run()
        self.assertEqual(r["phases"], ["Design", 'Ver"ify `q`', "Ship é", "Implement"])
        blob = json.dumps(ag.wf_public([r]))
        self.assertNotIn(BODY_SENTINEL, blob)
        self.assertNotIn(SECRET, blob)

    def test_doubtful_meta_falls_back_to_journal(self):
        for text in ("export const meta = { phases: [ { title: `A ${x}` } ] }",
                     "export const meta = { phases: [ { title: NAME } ] }",
                     "export const meta = { phases: [ { title: 'A' } ",
                     "const meta = { phases: [ { title: 'A' } ] }"):
            WM._META_MEMO.clear()
            self._script(text)
            self.assertEqual(self._run()["phases"], ["Design", "Implement"], text)

    def test_missing_script_uses_journal(self):
        self.assertEqual(self._run()["phases"], ["Design", "Implement"])

    def test_head_only_read(self):
        self._script("export const meta = { description: '%s', phases: [ { title: 'Late' } ] }"
                     % ("x" * (WM.HEAD_MAX + 10)))
        self.assertEqual(self._run()["phases"], ["Design", "Implement"])   # meta closes past the 16 KB head
        reads = []
        real_open = open

        class Spy(object):
            def __init__(self, f):
                self.f = f

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.f.close()

            def read(self, n=-1):
                reads.append(n)
                return self.f.read(n)

        def spy(p, mode="r", *a, **k):
            f = real_open(p, mode, *a, **k)
            return Spy(f) if str(p).endswith(".js") else f
        WM._META_MEMO.clear()
        with mock.patch("builtins.open", spy):
            WM.phase_titles(self.sd, "wf_abc123-d10")
        self.assertEqual(reads, [WM.HEAD_MAX])

    def test_titles_capped_and_redacted(self):
        ph = ", ".join("{ title: 'P%d %s' }" % (i, "y" * 50) for i in range(20))
        self._script("export const meta = { phases: [ %s ] }" % ph)
        got = WM.phase_titles(self.sd, "wf_abc123-d10")
        self.assertEqual(len(got), WM.TITLES_MAX)
        self.assertTrue(all(len(t) <= WM.TITLE_LEN for t in got))
        self.assertEqual(WM.phase_titles(self.sd, "../etc"), [])

    def test_name_from_script_basename(self):
        os.remove(self.sd + ".jsonl")                  # no launch result to name the run
        self._script("export const meta = { phases: [] }", name="sidereus-ux-sample")
        self.assertEqual(self._run()["name"], "sidereus-ux-sample")


if __name__ == "__main__":
    unittest.main()
