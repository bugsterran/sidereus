"""A run lands only on the project recorded in its plrun (web/js/48-pipeline.js plHomes, 48b plLiveRun), not on another
project's same-named pipeline whose stage agents fit the tags better; recorded skip stages render as skip."""
import json
import unittest

from tests.test_pipeline_live import _live
from tests.test_pipeline_run import MODEL, N, _js

ST = [{"title": t, "agent": "o-dev"} for t in ("원인", "수정", "리뷰")]
ST_B = [{"title": t, "agent": "b-fix"} for t in ("원인", "수정", "리뷰")]
PR = {"name": "bugfix", "proj": "/a", "sid": "s", "cur": "수정", "end": 0, "t0": N - 600, "t1": N - 10, "stages": {
    "원인": {"o": "done", "n": 1, "t0": N - 600, "t1": N - 500, "from": {}, "ag": []},
    "수정": {"o": "run", "n": 1, "t0": N - 500, "t1": N - 10, "from": {}, "ag": []},
    "리뷰": {"o": "skip", "n": 0, "t0": N - 400, "t1": N - 400, "from": {}, "ag": []}}}
# cwd /a, also edits /b; the tag's type fits /b's stage agent better, but the server recorded the run under /a
SESS = [{"sid": "s", "cwd": "/a", "repos": ["/b"], "sub": [{"lab": "b-fix: [pl:bugfix/수정] c"}], "plrun": [PR]}]
KNOWN = {"/a": {"n": 1, "names": ["bugfix"]}, "/b": {"n": 1, "names": ["bugfix"]}}
DATA = {"/a": {"ok": True, "pipelines": [{"name": "bugfix", "stages": ST}]}, "/b": {"ok": True, "pipelines": [{"name": "bugfix", "stages": ST_B}]}}


def _run(sess, proj, ret):
    pls = {"projs": {"ok": True, "projects": [{"path": "/a", "n": 1}, {"path": "/b", "n": 1}]}, "data": DATA}
    stub = "Date.now = () => %d; Object.assign(globalThis, {SESS: %s, PLS: %s, lsJson: () => ({})});" % (N * 1000, json.dumps(sess), json.dumps(pls))
    return _js("(() => { %s const r = plLiveRun(%s, 'bugfix'); return %s; })()" % (stub, json.dumps(proj), ret),
               "plLiveRun", "plProjSess", "plMem", "plRunName", "plSessions", "plSubsOf", *MODEL)


class RunProject(unittest.TestCase):
    def test_dot_only_on_recorded_project(self):
        pre = "const PLS = %s;" % json.dumps({"data": DATA})
        self.assertEqual(_live(SESS, known=KNOWN, pre=pre), [{"/a": ["bugfix"]}, 1])
        self.assertEqual(_live(SESS, pre=pre), {"/a": ["bugfix"]})          # known null: the record still decides

    def test_no_stand_in_run_on_other_project(self):
        self.assertIsNone(_run(SESS, "/b", "r"))
        self.assertEqual(_run(SESS, "/a", "r && [r.sid, r.lt['원인'].st, r.lt['수정'].st, r.lt['리뷰'].st]"), ["s", "done", "run", "skip"])

    def test_record_without_proj_keeps_scoring(self):
        sess = [dict(SESS[0], plrun=[dict(PR, proj="")])]
        pre = "const PLS = %s;" % json.dumps({"data": DATA})
        self.assertEqual(_live(sess, known=KNOWN, pre=pre)[0], {"/b": ["bugfix"]})


# run request recipients: Codex sessions (live plat 'cx') get a shell-marker request; Claude bytes are frozen
DP = {"name": "bugfix", "defaults": {"model": "sonnet"}, "stages": [
    {"title": "원인", "agent": "o-dev", "model": "opus", "skill": "dbg"},
    {"title": "수정", "agent": "o-gone", "gate": "bash t.sh"},
    {"title": "리뷰", "agent": "o-dev", "onFail": {"goto": "수정", "max": 2}}]}
DD = {"/a": {"default_tasks": {"원인": "DEF-CAUSE"}, "agents": [{"name": "o-dev", "scope": "project"}]}}
DM_FNS = ("plDmFor", "plDmDirect", "plDmText", "plDmCodex", "plDmMissing", "plAgMissing")
DM_DIRECT = ("파이프라인 bugfix 실행 (세션 직접) — 요청: «fix it»\nRun .claude/pipelines/bugfix.json yourself with the Agent tool (not the Workflow tool). Stages in order:\n"
             "1. 원인 — agent o-dev · model opus · skill dbg\n2. 수정 — agent o-gone · model haiku · gate `bash t.sh`\n3. 리뷰 — agent o-dev · model sonnet · onFail → 수정 (max 2)\n"
             "Model overrides for this run — before the first stage run one Bash (`true`) per line, description = the line:\n[pl-model:bugfix/수정=haiku]\n"
             "Each stage: Agent(subagent_type = its agent, model unless inherit, description starting with \"[pl:bugfix/<stage title>]\" — Sidereus lights stages from it), "
             "prompt = the default instruction for the title + the stage \"task\" + the pipeline \"rules\" + this request + earlier stage summaries and changed files"
             " + for a stage with a skill: \"Follow the <skill> skill.\" (load it with the Skill tool first). Each stage returns status PASS/FAIL, summary, findings (file/line/text), changed files.\n"
             "onFail: continue the goto stage's existing agent with SendMessage (attach the findings) instead of a new Agent, then rerun the failing stage the same way — at most max times; "
             "after it passes go to \"then\" if set. retry: SendMessage to the same agent. parallel / fanout: several Agent calls in one message.\n"
             "Report each stage in ≤10 lines. Never restart or commit unless the rules say so.\n"
             "Default instructions (also .claude/pipelines/_defaults.json in the Sidereus repo):\n원인: DEF-CAUSE\n"
             "Missing agents → run as general-purpose with the same task: o-gone")
DM_WF = ("파이프라인 bugfix 실행 — 요청: «fix it»\nWorkflow 도구로 실행: scriptPath .claude/workflows/pipeline.js · args "
         "{\"pipeline\":\"bugfix\",\"request\":\"fix it\",\"models\":{\"수정\":\"haiku\"}}\n"
         "단계: 원인(o-dev·opus)→수정(o-gone·haiku)→리뷰(o-dev·sonnet)\nMissing agents → run as general-purpose with the same task: o-gone")
CLAUDE_ONLY = ("Agent tool", "subagent_type", "SendMessage", "Workflow", "pl-model", "AskUserQuestion")


def _dm(mode, cx):
    stub = "Object.assign(globalThis, {PLS: {proj: '/a', data: %s}, PLRUN: {mode: '%s'}});" % (json.dumps(DD), mode)
    return _js("(() => { %s return plDmFor(%s, 'fix it', {수정: 'haiku'}, %s); })()" % (stub, json.dumps(DP), "true" if cx else "false"), *DM_FNS)


class CodexRecipient(unittest.TestCase):
    def test_sessions_include_codex(self):
        sess = [{"sid": "s1", "cwd": "/a"}, {"sid": "s2", "cwd": "/a", "plat": "cc"}, {"sid": "s3", "cwd": "/a", "plat": "cx", "mbox": "cx", "mboxSrc": "identity"},
                {"sid": "s4", "cwd": "/a", "plat": "gm"}, {"sid": "s5", "cwd": "/a", "plat": "cx", "state": "done"}]
        stub = "Object.assign(globalThis, {SESS: %s, PLS: {data: {}}, lsJson: () => ({})});" % json.dumps(sess)
        r = _js("(() => { %s return plSessions('/a').map(x => [x.sid, x.cx, x.login]); })()" % stub, "mboxIn", "plSessions", "plProjSess", "plMem", "plSubsOf")
        self.assertEqual(r, [["s1", False, False], ["s2", False, False], ["s3", True, True]])

    def test_codex_launcher_env_id_is_logged_in(self):
        # cx env = launcher id with a read cursor (server-checked); a Claude env (MAILBOX_ME guess) stays off
        sess = [{"sid": "c1", "cwd": "/a", "plat": "cx", "mbox": "a-codex", "mboxSrc": "env"},
                {"sid": "c2", "cwd": "/a", "plat": "cx", "mbox": "a-codex", "mboxSrc": "folder"},
                {"sid": "c3", "cwd": "/a", "plat": "cc", "mbox": "me", "mboxSrc": "env"}]
        stub = "Object.assign(globalThis, {SESS: %s, PLS: {data: {}}, lsJson: () => ({})});" % json.dumps(sess)
        r = _js("(() => { %s return plSessions('/a').map(x => [x.sid, x.login]); })()" % stub, "mboxIn", "plSessions", "plProjSess", "plMem", "plSubsOf")
        self.assertEqual(r, [["c1", True], ["c2", False], ["c3", False]])

    def test_claude_bytes_frozen(self):
        self.assertEqual(_dm("direct", False), DM_DIRECT)
        self.assertEqual(_dm("wf", False), DM_WF)

    def test_codex_shell_markers_any_mode(self):
        for mode in ("direct", "wf"):
            t = _dm(mode, True)
            self.assertTrue(t.startswith("파이프라인 bugfix 실행 (세션 직접) — 요청: «fix it»\n"))
            self.assertIn('echo "[pl:bugfix/<stage title>]"', t)
            self.assertIn('echo "[pl-end:bugfix/<stage title>]"', t)
            self.assertIn("2. 수정 · gate `bash t.sh`", t)
            self.assertIn("3. 리뷰 · onFail → 수정 (max 2)", t)
            self.assertIn("원인: DEF-CAUSE", t)
            self.assertNotIn("haiku", t)              # model overrides do not apply to a Codex session
            for w in CLAUDE_ONLY:
                self.assertNotIn(w, t)

    def test_codex_turn_end_hint(self):
        # UI-only hint for a Codex recipient; none for Claude; the panel shows it after the preview, never in plDmFor
        r = _js("(globalThis.esc = s => String(s), [plCxHint({cx: true, id: 'x'}), plCxHint({cx: false, id: 'y'}), plCxHint(null)])", "plCxHint")
        self.assertIn("data-cxhint", r[0])
        self.assertIn("이 세션은 지금 턴이나 다음 턴이 끝날 때 받습니다", r[0])
        self.assertEqual(r[1:], ["", ""])
        from tests._load import js_all, js_fn
        self.assertIn("+ plCxHint(cur)", js_all())
        for f in DM_FNS:
            self.assertNotIn("plCxHint", js_fn(f))


if __name__ == "__main__":
    unittest.main()
