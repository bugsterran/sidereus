"""AGENTS.md rule 1 (enforced 2026-09-25): session rows and the failures/wreckage payloads carry metadata only.

No reply text, human instruction, Bash command or raw tool output may leave the server through these payloads.
Synthetic inputs only — temp files and monkeypatched readers; no live transcript is read.
"""
import json
import os
import shutil
import tempfile
import time
import unittest

from tests._load import sidereus

parse = sidereus("parse")
sessions = sidereus("sessions")
agents = sidereus("agents")
F = sidereus("failures")
S = sidereus("failures_scan")

SECRET = "SECRET-7f3a rm -rf /w/private-notes"
CWD = "/w/repo-m"
T0 = "2026-09-24T00:58:18.937Z"


def _asst(*content):
    return json.dumps({"type": "assistant", "sessionId": "s1", "cwd": CWD, "timestamp": T0,
                       "message": {"content": list(content)}})


def _user(content):
    return json.dumps({"type": "user", "sessionId": "s1", "cwd": CWD, "timestamp": T0,
                       "message": {"content": content}})


class _Patch(unittest.TestCase):
    def patch(self, mod, name, val):
        old = getattr(mod, name)
        setattr(mod, name, val)
        self.addCleanup(setattr, mod, name, old)


class SessionRowKeys(_Patch):
    def row(self, lines):
        self.patch(parse, "_tail_lines", lambda fp, nbytes=0, limit=0: list(lines))
        self.patch(parse, "_running_bg", lambda fp: ([], [], []))
        self.patch(parse, "_cwd_from_slug", lambda s: CWD)
        p = parse._parse_transcript("/x/-w-repo-m/s1.jsonl")
        for n, v in {"_ctx_window": lambda *a: (1000000, "obs"), "_otel_state": lambda sid: None,
                     "_bg_show": lambda *a: [], "_mon_rows": lambda *a: [], "_bg_age": lambda *a: 0,
                     "session_repos": lambda *a: [], "_wt_of": lambda *a: None, "mbox_of": lambda *a: ("", ""),
                     "_projcost_of": lambda *a: 0.0, "_git_state": lambda *a: "", "_model_win": lambda *a: (0, 0),
                     "_dead": lambda *a: False}.items():
            self.patch(sessions, n, v)
        now = time.time()
        return p, sessions._session_row("/nonexistent/s1.jsonl", now - 30, now, {CWD: 1}, p)

    def test_no_reply_task_or_bash_command(self):
        p, r = self.row([_user(SECRET + " please"),
                         _asst({"type": "text", "text": SECRET + " reply"},
                               {"type": "tool_use", "id": "b1", "name": "Bash",
                                "input": {"command": SECRET, "description": "list"}})])
        self.assertTrue(p.get("targ"))                 # parse still sees it (work popup path) ...
        for k in ("reply", "task"):
            self.assertNotIn(k, r)                      # ... but the row never carries it
        self.assertEqual(r["targ"], "")
        self.assertEqual(r["tool"], "Bash")             # tool name is metadata
        self.assertNotIn("SECRET-7f3a", json.dumps(r, ensure_ascii=False))

    def test_agent_description_is_kept(self):
        _p, r = self.row([_asst({"type": "tool_use", "id": "a1", "name": "Agent",
                                 "input": {"description": "Fix the parser", "prompt": SECRET}})])
        self.assertEqual(r["targ"], "Fix the parser")
        self.assertNotIn("SECRET-7f3a", json.dumps(r, ensure_ascii=False))


class AgentLastIsToolName(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="sidereus-meta-")
        self.addCleanup(shutil.rmtree, self.d, True)
        agents._AGENT_LAST.clear()

    def last(self, block):
        fp = os.path.join(self.d, "agent-%d.jsonl" % len(os.listdir(self.d)))
        with open(fp, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "message": {"content": [block]}}) + "\n")
        return agents._agent_last(fp)

    def test_bash_command_not_shown(self):
        self.assertEqual(self.last({"type": "tool_use", "name": "Bash", "input": {"command": SECRET}}), "Bash")

    def test_nested_agent_description_shown(self):
        self.assertEqual(self.last({"type": "tool_use", "name": "Agent",
                                    "input": {"description": "Scan", "prompt": SECRET}}), "Agent · Scan")


class FailuresPayload(_Patch):
    def evs(self):
        base = {"at": int(time.time()) - 60, "tid": "", "cwd": CWD, "proj": "repo-m", "sid": "s1", "text": SECRET}
        return [dict(base, kind="tool", tool="Bash", sig="Exit code N " + SECRET, grade="noise", why="x"),
                dict(base, kind="tool", tool="Bash", sig="other " + SECRET, grade="noise", why="x"),
                dict(base, kind="hook", tool="Edit", sig="훅이 막음 — " + SECRET, grade="mine", why="y"),
                dict(base, kind="agent", tid="t1", sig="서브에이전트 failed", grade="check", why="")]

    def test_no_raw_text_and_fixed_tool_labels(self):
        self.patch(F, "_fail_events", lambda hours, capped=True: (self.evs(), 1, 24.0))
        out = F.failures(24)
        self.assertNotIn("SECRET-7f3a", json.dumps(out, ensure_ascii=False))
        sigs = {r["sig"]: r["n"] for r in out["rows"]}
        self.assertEqual(sigs.get("도구 오류 — Bash"), 2)      # grouped by tool name, counted
        self.assertIn("훅이 막음 — Edit", sigs)
        self.assertIn("서브에이전트 failed", sigs)            # fixed template kept as is
        for r in out["rows"]:
            for smp in r["samples"]:
                self.assertNotIn("text", smp)

    def test_fail_line_takes_tool_name_from_id(self):
        ln = json.dumps({"type": "user", "timestamp": T0, "cwd": CWD, "message": {"content": [
            {"type": "tool_result", "tool_use_id": "toolu_A1", "is_error": True, "content": "Exit code 1"}]}})
        (ev,) = S._fail_line(ln, {"toolu_A1": "Bash"})
        self.assertEqual(ev["tool"], "Bash")
        (ev,) = S._fail_line(ln)
        self.assertEqual(ev["tool"], "")

    def test_fail_read_maps_tool_use_ids(self):
        d = tempfile.mkdtemp(prefix="sidereus-meta-fr-")
        self.addCleanup(shutil.rmtree, d, True)
        fp = os.path.join(d, "s.jsonl")
        with open(fp, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "timestamp": T0, "message": {"content": [
                {"type": "tool_use", "id": "toolu_Z9", "name": "Edit", "input": {"old_string": SECRET}}]}},
                separators=(",", ":")) + "\n")
            f.write(json.dumps({"type": "user", "timestamp": T0, "cwd": CWD, "message": {"content": [
                {"type": "tool_result", "tool_use_id": "toolu_Z9", "is_error": True,
                 "content": "String to replace not found"}]}}, separators=(",", ":")) + "\n")
        self.addCleanup(lambda: [m.pop(fp, None) for m in (S._FAIL_EV, S._FAIL_OFF, S._FAIL_TNAME)])
        (ev,) = S._fail_read(fp)
        self.assertEqual(ev["tool"], "Edit")


class WreckageSteps(_Patch):
    def test_steps_have_no_tool_input(self):
        d = tempfile.mkdtemp(prefix="sidereus-meta-wr-")
        self.addCleanup(shutil.rmtree, d, True)
        fp = os.path.join(d, "agent-x.jsonl")
        open(fp, "w", encoding="utf-8").close()
        steps = [{"tool": "Bash", "arg": SECRET, "targ": SECRET, "t": "2026-09-25T10:11:12", "id": "i", "res": {"ok": 1}}]
        self.patch(F, "_open_or_tail", lambda p, tail=0: [])
        self.patch(F, "_work_scan", lambda rows, cwd: ((steps, None, None, None, "", ""), ""))
        F._WRECK_CACHE.clear()
        tr = F._agent_trace(fp, "/w")
        self.assertEqual(tr["steps"][0]["tool"], "Bash")
        self.assertNotIn("arg", tr["steps"][0])
        self.assertNotIn("SECRET-7f3a", json.dumps(tr, ensure_ascii=False))


class RetroSigs(unittest.TestCase):
    def test_tool_sigs_are_fixed_label_plus_tool(self):
        R = sidereus("retro")
        now = time.time()
        evs = [{"at": now - 60, "kind": "tool", "tool": "Bash", "sig": "Exit code N " + SECRET, "grade": "noise",
                "proj": "p", "text": SECRET},
               {"at": now - 50, "kind": "hook", "tool": "", "sig": "훅이 막음 — " + SECRET, "grade": "mine",
                "proj": "p", "text": SECRET}]
        o = R._retro_build(7, now, {"list": []}, evs, {}, {})
        blob = json.dumps(o, ensure_ascii=False, default=list)
        self.assertNotIn("SECRET-7f3a", blob)
        sigs = {s["sig"] for w in [o] for s in self._sigs(o)}
        self.assertEqual(sigs, {"도구 오류 — Bash", "훅이 막음"})

    def _sigs(self, o):
        out = []
        def walk(x):
            if isinstance(x, dict):
                if "sigs" in x and isinstance(x["sigs"], list):
                    out.extend(x["sigs"])
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(o)
        return out


class TransitionCardsNoText(_Patch):
    def test_ask_abort_cards_have_empty_body(self):
        notes = sidereus("notes")
        added = []
        self.patch(notes, "_card_add", lambda *a, **k: added.append(a))
        for end in ("ask", "abort"):
            notes._prev_state.clear()
            base = {"sid": "s1", "cwd": CWD, "project": "repo-m", "task": SECRET, "reply": SECRET}
            notes._note_transition(dict(base, state="tool"))
            notes._note_transition(dict(base, state=end))
        notes._prev_state.clear()
        self.assertEqual(len(added), 2)
        for a in added:
            self.assertEqual(a[3], "")
            self.assertNotIn("SECRET-7f3a", json.dumps(a, ensure_ascii=False))


class OldStoredCards(_Patch):
    def test_old_transition_card_body_is_sent_empty(self):
        C = sidereus("cards")
        now = time.time()
        stored = [json.dumps({"at": "2026-09-25T10:00:00", "kind": k, "project": "p", "title": "t",
                              "text": "지시: " + SECRET, "cwd": CWD}) for k in ("ask", "abort", "wait")]
        stored.append(json.dumps({"at": "2026-09-25T10:01:00", "kind": "agent", "project": "p", "title": "t",
                                  "text": "Explore: Scan", "cwd": CWD}))
        self.patch(C, "_tail_lines", lambda fp, nbytes=0, limit=0: list(stored))
        out = C.cards(10, now=now)
        self.assertNotIn("SECRET-7f3a", json.dumps(out, ensure_ascii=False))
        self.assertEqual([c["text"] for c in out if c["kind"] != "agent"], ["", "", ""])
        self.assertEqual([c["text"] for c in out if c["kind"] == "agent"], ["Explore: Scan"])


class DemoRows(unittest.TestCase):
    def test_demo_sessions_and_cards_carry_no_text(self):
        demo = sidereus("demo")
        w = demo.World(anchor=1_790_000_000, page_build="x", now=1_790_000_000)

        class _U:
            query = "since=0"
        code, st = demo.respond(w, "/api/state", _U())
        self.assertEqual(code, 200)
        for s in st["sessions"]:
            self.assertNotIn("task", s)
            self.assertNotIn("reply", s)
            if s.get("tool") not in ("Agent", "Task"):
                self.assertEqual(s.get("targ") or "", "")
        for c in st["cards"]:
            if c["kind"] in ("ask", "abort"):
                self.assertEqual(c["text"], "")


if __name__ == "__main__":
    unittest.main()
