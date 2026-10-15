"""Hooks pl_mark · pl_flow · pipelines_brief also see the pipelines of projects the session works in (transcript tail),
not only <cwd>/.claude/pipelines. Tmp dirs and a synthetic transcript only."""
import importlib.util
import io
import json
import os
import re
import shutil
import tempfile
import unittest
from unittest import mock

_HOOKS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks")


def _load(name):
    spec = importlib.util.spec_from_file_location("sd_" + name, os.path.join(_HOOKS, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


MARK, FLOW, BRIEF = _load("pl_mark"), _load("pl_flow"), _load("pipelines_brief")
SID = "sess-0001"
PIPE = {"v": 1, "name": "fix", "title": "버그 수정", "stages": [
    {"title": "설계", "agent": "general-purpose", "task": "secret-task"}, {"title": "구현", "agent": "general-purpose"}]}


class SessionDirs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.home = os.path.join(self.tmp, "home")
        self.bot = self._repo("bot", None)            # launch dir: no pipelines
        self.proj = self._repo("proj", "fix")        # where the work happens
        self.mbox = self._repo("mbox", "mailpipe")   # mailbox-like data dir: has pipelines, must not count
        self.tp = os.path.join(self.tmp, "t.jsonl")
        for mod in (MARK, FLOW, BRIEF):
            for k, v in (("HOME_DIR", self.home), ("DIRS_DIR", os.path.join(self.tmp, "plbrief")),
                         ("DATA_DIR", self.mbox), ("CONFIG_PATH", os.path.join(self.tmp, "cfg.json"))):
                p = mock.patch.object(mod, k, v)
                p.start()
                self.addCleanup(p.stop)
        for mod, k, v in ((MARK, "MARK_DIR", os.path.join(self.tmp, "plmark")),
                          (FLOW, "MARK_DIR", os.path.join(self.tmp, "plmark")),
                          (BRIEF, "BRIEF_DIR", os.path.join(self.tmp, "plb")),
                          (BRIEF, "CLAUDE_DIR", os.path.join(self.tmp, "cl"))):
            p = mock.patch.object(mod, k, v)
            p.start()
            self.addCleanup(p.stop)

    def _repo(self, name, pipe):
        d = os.path.join(self.home, name)
        os.makedirs(os.path.join(d, ".git"))
        if pipe:
            os.makedirs(os.path.join(d, ".claude", "pipelines"))
            with open(os.path.join(d, ".claude", "pipelines", pipe + ".json"), "w", encoding="utf-8") as f:
                json.dump(dict(PIPE, name=pipe), f, ensure_ascii=False)
        return d

    def _transcript(self, *cmds, **kw):
        with open(self.tp, "w", encoding="utf-8") as f:
            for c in cmds:
                b = c if isinstance(c, dict) else {"type": "tool_use", "name": "Bash", "input": {"command": c}}
                f.write(json.dumps({"type": kw.get("kind", "assistant"), "cwd": kw.get("cwd", self.bot),
                                    "message": {"content": [b]}}) + "\n")

    def _ev(self, tool, desc, event="PreToolUse", tp=True):
        ev = {"hook_event_name": event, "tool_name": tool, "session_id": SID, "cwd": self.bot,
              "tool_input": {"description": desc}}
        if tp:
            ev["transcript_path"] = self.tp
        if event == "PostToolUse":
            ev["tool_response"] = {"content": [{"type": "text", "text": "ok"}]}
        return ev

    def _call(self, mod, ev):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out):
            mod.main()
        v = out.getvalue()
        return json.loads(v)["hookSpecificOutput"] if v else None

    def test_blocks_identical(self):
        pat = re.compile(r"# --- session pipeline dirs.*?# --- end session pipeline dirs ---", re.S)
        blocks = []
        for n in ("pl_mark", "pl_flow", "pipelines_brief"):
            with open(os.path.join(_HOOKS, n + ".py"), encoding="utf-8") as f:
                blocks.append(pat.search(f.read()).group(0))
        self.assertEqual(blocks[0], blocks[1])
        self.assertEqual(blocks[0], blocks[2])

    def test_nudge_names_repo_pipeline_and_skips_mailbox(self):
        self._transcript("cd ~/proj && make", "cd %s && ls" % self.mbox)
        o = self._call(MARK, self._ev("Agent", "fix it"))
        self.assertEqual(o["permissionDecision"], "deny")
        self.assertIn("fix", o["permissionDecisionReason"])
        self.assertNotIn("mailpipe", o["permissionDecisionReason"])
        self.assertNotIn("fix it", o["permissionDecisionReason"])
        with open(os.path.join(self.tmp, "plbrief", SID + ".dirs"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), [self.proj])

    def test_no_transcript_is_old_behaviour(self):
        self._transcript("cd ~/proj")
        self.assertIsNone(self._call(MARK, self._ev("Agent", "x", tp=False)))
        self.assertIsNone(self._call(FLOW, self._ev("Agent", "[pl:fix/설계] x", tp=False)))
        self.assertIsNone(self._call(MARK, dict(self._ev("Agent", "x"), transcript_path=os.path.join(self.tmp, "none"))))

    def test_name_collision_shows_project(self):
        other = self._repo("other", "fix")
        self._transcript("cd ~/proj", "cd %s" % other)
        o = self._call(MARK, self._ev("Agent", "x"))
        self.assertIn("fix (proj)", o["permissionDecisionReason"])
        self.assertIn("fix (other)", o["permissionDecisionReason"])
        self._call(FLOW, self._ev("Agent", "[pl:fix/설계] x"))   # not in cwd: the most recent cd target owns it
        self.assertEqual(self._runs()["fix"]["proj"], other)

    def test_read_paths_and_output_do_not_count(self):
        self._transcript({"type": "tool_use", "name": "Read", "input": {"file_path": self.proj + "/a.py"}},
                         "cat %s/a.py ~/proj/b.py" % self.proj)
        self.assertIsNone(self._call(MARK, self._ev("Agent", "x")))
        os.remove(os.path.join(self.tmp, "plbrief", SID + ".dirs"))
        self._transcript({"type": "tool_result", "content": "cd ~/proj"}, kind="user")
        self.assertIsNone(self._call(MARK, self._ev("Agent", "x")))

    def test_event_without_cwd_does_not_raise(self):
        self._transcript("cd ~/proj")
        ev = self._ev("Agent", "[pl:fix/설계] x")
        del ev["cwd"]
        self.assertIsNone(self._call(FLOW, ev))   # _flow drops it; _project is also reached via pl_guard
        self.assertEqual(FLOW._project(ev, "Agent", "fix", "설계", None), self.proj)

    def test_transcript_cwd_counts(self):
        self._transcript("ls", cwd=os.path.join(self.proj, "sub"))
        self.assertIn("fix", self._call(MARK, self._ev("Agent", "x"))["permissionDecisionReason"])

    def test_cwd_with_pipelines_uses_cwd_only(self):
        own = self._repo("own", "mine")
        self._transcript("cd ~/proj")
        ev = dict(self._ev("Agent", "x"), cwd=own)
        r = self._call(MARK, ev)["permissionDecisionReason"]
        self.assertIn("This project has pipelines: mine.", r)
        self.assertNotIn("fix ", r.split(".")[0])
        self.assertIsNone(self._call(FLOW, dict(self._ev("Agent", "[pl:fix/설계] x"), cwd=own)))

    def _runs(self):
        with open(os.path.join(self.tmp, "plmark", SID + ".runs.json"), encoding="utf-8") as f:
            return json.load(f)["runs"]

    def _bugfix_repos(self, *names):
        def bf(stages):
            return {"v": 1, "name": "bugfix", "stages": [{"title": t, "agent": a} for t, a in stages]}
        ps = {"origin": bf([("재현", "origin-dev"), ("원인", "g"), ("실패 테스트", "g"), ("수정", "origin-dev")]),
              "api": bf([("재현", "api-bugfix"), ("원인", "g"), ("수정", "api-bugfix"), ("리뷰", "g")])}
        out = []
        for n in names:
            d = self._repo(n, None)
            os.makedirs(os.path.join(d, ".claude", "pipelines"))
            with open(os.path.join(d, ".claude", "pipelines", "bugfix.json"), "w", encoding="utf-8") as f:
                json.dump(ps[n], f, ensure_ascii=False)
            out.append(d)
        return out

    def _bf_ev(self, cwd, title, event="PreToolUse", sub=None, tool="Agent"):
        e = dict(self._ev(tool, "[pl:bugfix/%s] x" % title, event=event), cwd=cwd)
        if sub:
            e["tool_input"]["subagent_type"] = sub
        return e

    def test_flow_same_name_prefers_cwd_project(self):
        # R1: the cwd project owns <name>, so neither a later `cd` into another owner nor its agent fit takes the run
        origin, api = self._bugfix_repos("origin", "api")
        self._transcript("cd ~/api", "cd ~/api && git log")
        o = self._call(FLOW, self._bf_ev(origin, "재현", sub="api-bugfix"))
        self.assertIn("expects subagent_type origin-dev", o["permissionDecisionReason"])   # judged by cwd's file
        self.assertIsNone(self._call(FLOW, self._bf_ev(origin, "재현", sub="origin-dev")))
        self.assertEqual(self._runs()["bugfix"]["proj"], origin)
        self._call(FLOW, self._bf_ev(origin, "재현", event="PostToolUse"))
        self._call(FLOW, self._bf_ev(origin + "/src", "원인", tool="Bash"))   # cwd below the git root counts too
        self.assertEqual(self._runs()["bugfix"]["proj"], origin)

    def test_flow_same_name_outside_cwd_prefers_latest_cd(self):
        # R2: owners only outside cwd -> the most recent `cd` target, even against agent fit or list order
        origin, api = self._bugfix_repos("origin", "api")
        self._transcript("cd ~/api", "cd ~/origin")
        o = self._call(FLOW, self._bf_ev(self.bot, "재현", sub="api-bugfix"))
        self.assertIn("expects subagent_type origin-dev", o["permissionDecisionReason"])   # fit does not override
        self._call(FLOW, self._bf_ev(self.bot, "재현", tool="Bash"))
        self.assertEqual(self._runs()["bugfix"]["proj"], origin)
        os.remove(os.path.join(self.tmp, "plbrief", SID + ".dirs"))
        os.remove(os.path.join(self.tmp, "plmark", SID + ".runs.json"))
        self._transcript("cd ~/origin && cd ~/api")   # later cd of one command wins
        self._call(FLOW, self._bf_ev(self.bot, "재현"))
        self.assertEqual(self._runs()["bugfix"]["proj"], api)

    def test_flow_open_run_keeps_its_project(self):
        origin, api = self._bugfix_repos("origin", "api")
        self._transcript("cd ~/origin", "cd ~/api")
        self.assertIsNone(self._call(FLOW, self._bf_ev(self.bot, "재현", sub="api-bugfix")))
        self._call(FLOW, self._bf_ev(self.bot, "재현", event="PostToolUse"))
        self.assertIsNone(self._call(FLOW, self._bf_ev(self.bot, "원인", tool="Bash")))      # remembered project
        self.assertIsNone(self._call(FLOW, self._bf_ev(self.bot, "원인")))
        t = self._call(FLOW, self._bf_ev(self.bot, "원인", event="PostToolUse"))["additionalContext"]
        self.assertIn("PASS → next: [pl:bugfix/수정] · agent api-bugfix", t)
        self.assertIsNone(self._call(FLOW, self._bf_ev(self.bot, "수정", sub="api-bugfix")))   # no «실패 테스트» skip-deny
        self.assertEqual(self._runs()["bugfix"]["proj"], api)

    def test_flow_hand_off_via_repo(self):
        self._transcript("cd ~/proj")
        self.assertIsNone(self._call(FLOW, self._ev("Agent", "[pl:fix/설계] x")))
        t = self._call(FLOW, self._ev("Agent", "[pl:fix/설계] x", event="PostToolUse"))["additionalContext"]
        self.assertIn("PASS → next: [pl:fix/구현]", t)

    def test_brief_includes_repo_with_path(self):
        self._transcript("cd ~/proj")
        ev = {"hook_event_name": "UserPromptSubmit", "session_id": SID, "cwd": self.bot, "transcript_path": self.tp}
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out):
            BRIEF.main()
        t = json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]
        self.assertIn("- fix (~/proj) — ", t)
        self.assertNotIn("mailpipe", t)
        self.assertNotIn("secret", t)
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out):
            BRIEF.main()
        self.assertEqual(out.getvalue(), "")   # unchanged: once


class WindowsCd(unittest.TestCase):
    CASES = [("cd ~/a && x", ["~/a"]), ("cd /abs/p; ls", ["/abs/p"]), ("(cd sub/dir)", ["sub/dir"]),
             ("cd 'x y'", ["x"]), ("cd /dev", ["/dev"]), ("cd -", []),
             (r"cd C:\x\y", [r"C:\x\y"]), (r"cd /d C:\x", [r"C:\x"]), (r'cd /D "C:\a b\c"', [r"C:\a b\c"]),
             (r"Set-Location C:\r", [r"C:\r"]), (r"sl -Path 'D:\q r'", [r"D:\q r"]), ("set-location -path C:/w", ["C:/w"])]

    def test_cd_targets(self):
        for mod in (MARK, FLOW, BRIEF):
            for cmd, want in self.CASES:
                got = [next(g for g in m.groups() if g) for m in mod._CD_RE.finditer(cmd)]
                self.assertEqual(got, want, cmd)

    def test_scan_dirs_with_ntpath(self):
        import ntpath
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        tp = os.path.join(tmp, "t.jsonl")
        home, cwd = r"C:\Users\me", r"C:\Users\me\bot"
        with open(tp, "w", encoding="utf-8") as f:
            for c in (r"cd /d C:\Users\me\proj", r"Set-Location -Path 'c:\users\ME\Other dir'", r"cd D:\elsewhere",
                      r"cd sub\x"):
                f.write(json.dumps({"type": "assistant", "cwd": cwd, "message": {"content": [
                    {"type": "tool_use", "name": "PowerShell", "input": {"command": c}}]}}) + "\n")
        with mock.patch.object(FLOW.os, "path", ntpath), mock.patch.object(FLOW.os, "sep", "\\"), \
                mock.patch.object(ntpath, "isdir", lambda p: True), \
                mock.patch.object(FLOW, "HOME_DIR", home), mock.patch.object(FLOW, "DATA_DIR", r"C:\mbox"), \
                mock.patch.object(FLOW, "_git_root", lambda p: p), mock.patch.object(FLOW, "_has_pl", lambda d: True):
            got = FLOW._scan_dirs(tp, cwd)
        self.assertEqual(got, [r"C:\Users\me\bot\sub\x", r"c:\users\ME\Other dir", r"C:\Users\me\proj"])


if __name__ == "__main__":
    unittest.main()
