"""scripts/plreplay_mine.py: keeps only tool names, tags, booleans and re-numbered ids. Synthetic transcripts in tmp."""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


M = _load("plreplay_mine", os.path.join("scripts", "plreplay_mine.py"))
H = _load("pl_flow_hook_mine", os.path.join("hooks", "pl_flow.py"))

SECRETS = ("SECRET-DESC", "SECRET-PROMPT", "SECRET-CMD", "SECRET-MSG", "SECRET-RESULT", "SECRET-SUM",
           "secret-proj", "secret-agent", "secret-skill", "secretuser")
CWD = "/Users/" + "secretuser" + "/secret-proj"
SID = "1234abcd-" + "0000-4000-8000-" + "00000000beef"
AG = "a1b2c3d4" + "e5f60718"
PIPE = {"v": 1, "name": "secret-proj-change", "title": "SECRET-DESC", "rules": ["SECRET-PROMPT"], "stages": [
    {"title": "design", "agent": "secret-agent", "task": "SECRET-PROMPT", "ui": {"x": 1}},
    {"title": "impl", "agent": "general-purpose", "gate": "SECRET-CMD --fast"},
    {"title": "ship", "skill": "secret-skill", "agent": "general-purpose", "onFail": {"goto": "impl", "max": 1}}]}


def _row(ts, role, content, **kw):
    d = {"timestamp": "2026-01-01T00:00:%02d.000Z" % ts, "sessionId": SID, "cwd": CWD,
         "message": {"role": role, "content": content}}
    d.update(kw)
    return d


def _use(i, name, inp):
    return {"type": "tool_use", "id": "toolu_%d" % i, "name": name, "input": inp}


def _res(i, text, err=None):
    r = {"type": "tool_result", "tool_use_id": "toolu_%d" % i, "content": text}
    if err is not None:
        r["is_error"] = err
    return r


class Mine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.pipe = os.path.join(self.tmp, "secret-proj-change.json")
        with open(self.pipe, "w", encoding="utf-8") as fh:
            json.dump(PIPE, fh)
        tag = "[pl:secret-proj-change/design] SECRET-DESC"
        parent = [
            _row(0, "assistant", [_use(1, "Agent", {"description": tag, "prompt": "SECRET-PROMPT",
                                                    "subagent_type": "secret-agent", "model": "opus"})]),
            _row(1, "user", [_res(1, "PreToolUse:Agent hook error: You skipped x", True)]),
            _row(2, "assistant", [_use(2, "Agent", {"description": tag, "prompt": "SECRET-PROMPT",
                                                    "subagent_type": "secret-agent", "run_in_background": True})]),
            _row(3, "user", [_res(2, "Async agent launched SECRET-RESULT")],
                 toolUseResult={"agentId": AG, "status": "async_launched", "prompt": "SECRET-PROMPT"}),
            _row(8, "assistant", [_use(3, "SendMessage", {"to": AG, "summary": "[pl:secret-proj-change/design] SECRET-SUM",
                                                          "message": "SECRET-MSG"})]),
            _row(9, "user", [_res(3, "Message queued SECRET-RESULT")]),
            _row(20, "assistant", [_use(4, "Bash", {"command": "git commit --dry-run -m SECRET-CMD",
                                                    "description": "SECRET-DESC"})]),
            _row(21, "assistant", [_use(5, "Bash", {"command": "cd " + CWD + " && git commit -m SECRET-CMD",
                                                    "description": "[pl:secret-proj-change/ship] SECRET-DESC"})]),
            _row(22, "user", [_res(5, [{"type": "text", "text": "SECRET-RESULT"}], False)]),
            _row(23, "assistant", [_use(6, "Bash", {"command": "echo '[pl-end:secret-proj-change/ship|fail]'",
                                                    "description": "SECRET-DESC"})]),
            _row(24, "assistant", [_use(7, "Bash", {"command": "ls SECRET-CMD", "description": "SECRET-DESC"})]),
        ]
        self.sess = os.path.join(self.tmp, SID + ".jsonl")
        self._write(self.sess, parent)
        sub = [
            _row(4, "user", [{"type": "text", "text": "SECRET-PROMPT"}], agentId=AG),
            _row(5, "assistant", [_use(11, "Bash", {"command": "git -C " + CWD + " commit -am SECRET-CMD",
                                                    "description": "SECRET-DESC"})], agentId=AG),
            _row(6, "user", [_res(11, "SECRET-RESULT", False)], agentId=AG),
            _row(7, "assistant", [{"type": "text", "text": "SECRET-RESULT"}], agentId=AG),
            _row(12, "assistant", [{"type": "text", "text": "SECRET-RESULT"}], agentId=AG),
        ]
        d = os.path.join(self.tmp, SID, "subagents")
        os.makedirs(d)
        self._write(os.path.join(d, "agent-%s.jsonl" % AG), sub)
        self.out = M.mine(self.sess, self.pipe, name="pipe")
        self.txt = json.dumps(self.out, ensure_ascii=False)

    def _write(self, p, rows):
        with open(p, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")

    def test_no_text_or_ids_leak(self):
        for s in SECRETS + (SID, AG, "/Users/", "toolu_"):
            self.assertNotIn(s, self.txt, s)
        self.assertEqual(self.out["sid"], "sess-0001")
        self.assertEqual(self.out["cwd"], "proj")
        self.assertEqual(self.out["cp"], [])
        st = self.out["pipe"]["stages"]
        self.assertEqual([s["title"] for s in st], ["design", "impl", "ship"])
        self.assertEqual(st[0]["agent"], "ag1")
        self.assertEqual(st[1]["gate"], "gate")
        self.assertNotIn("task", st[0])

    def test_tags_and_flags(self):
        ev = self.out["ev"]
        a = [e for e in ev if e["tool"] == "Agent" and e["e"] == "pre"]
        self.assertEqual([e["tag"] for e in a], ["[pl:pipe/design]"] * 2)
        self.assertEqual(a[0]["denied"], 1)
        self.assertEqual(a[0]["sub"], "ag1")
        self.assertEqual(a[0]["model"], "opus")
        self.assertEqual(sum(1 for e in ev if e["tool"] == "Agent" and e["e"] == "post"), 1)   # denied Pre: no Post
        self.assertEqual((a[1]["bg"], a[1]["to"]), (1, "a01"))
        sm = [e for e in ev if e["tool"] == "SendMessage"]
        self.assertEqual(sm[0]["to"], "a01")
        self.assertEqual(sm[0]["tag"], "[pl:pipe/design]")
        self.assertEqual(sm[1]["bg"], 1)   # «Message queued» matched BG_RE
        done = [e for e in ev if e["e"] == "bgdone"]
        # Agent run spans 4..7, the resumed run 12: one bgdone per dispatch.
        self.assertEqual([(e["to"], e["t"]) for e in done], [("a01", 7.0), ("a01", 12.0)])
        self.assertEqual(ev[0]["t"], 0)

    def test_commit_only_real_and_subagent_carries_aid(self):
        sh = [e for e in self.out["ev"] if e["tool"] == "Bash" and e["e"] == "pre"]
        sub = [e for e in sh if e["aid"]]
        self.assertEqual([(e["aid"], e["commit"]) for e in sub], [("a01", 1)])
        main = [e for e in sh if not e["aid"]]
        self.assertEqual([(e["commit"], e["tag"]) for e in main],
                         [(1, "[pl:pipe/ship]"), (0, "")])   # dry-run and plain ls dropped
        self.assertEqual(main[1]["mark"], "[pl-end:pipe/ship|fail]")

    def test_bare_hook_deny_vs_run_failure(self):
        tag = "[pl:secret-proj-change/impl] SECRET-DESC"
        rows = [
            # Skip-guard deny: bare reason, no «PreToolUse:» prefix.
            _row(0, "assistant", [_use(1, "Agent", {"description": tag, "subagent_type": "general-purpose"})]),
            _row(1, "user", [_res(1, "You skipped design; run it, or declare each skip first", True)],
                 toolUseResult="Error: You skipped design; run it, or declare each skip first"),
            _row(2, "assistant", [_use(2, "Bash", {"command": "true", "description": tag})]),
            _row(3, "user", [_res(2, "Exit code 1\nSECRET-RESULT", True)], toolUseResult="Error: Exit code 1"),
            _row(4, "assistant", [_use(3, "Bash", {"command": "true", "description": tag})]),
            _row(5, "user", [_res(3, "The user doesn't want to proceed", True)], toolUseResult="User rejected tool use"),
        ]
        p = os.path.join(self.tmp, "two.jsonl")
        self._write(p, rows)
        ev = M.mine(p, self.pipe, subdir=os.path.join(self.tmp, "none"))["ev"]
        self.assertEqual([(e["tool"], e["e"], e["denied"], e.get("err")) for e in ev],
                         [("Agent", "pre", 1, None), ("Bash", "pre", 0, None), ("Bash", "post", 0, 1),
                          ("Bash", "pre", 0, None)])
        self.assertNotIn("SECRET", json.dumps(ev))

    def test_regex_copies_match_hook(self):
        self.assertEqual(M.COMMIT_RE.pattern, H._COMMIT_RE.pattern)
        self.assertEqual(M.BG_RE.pattern, H.BG_RE.pattern)
        self.assertEqual(M.MARK.pattern.replace("(\\[pl", "\\[pl", 1).replace(")\\])", ")\\]", 1), H.MARK.pattern)


if __name__ == "__main__":
    unittest.main()
