"""Deterministic tests for sidereus/file_owner.py and the attention 'conflict' signal.

No live data: CLAUDE_PROJECTS points at a temp dir, wt_files is monkeypatched, the index state is reset per test.
"""
import json
import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timezone

from tests._load import sidereus

fo = sidereus("file_owner")
att = sidereus("attention")


def utc(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def edit_line(ts, name, path, cwd="/w"):
    key = "notebook_path" if name == "NotebookEdit" else "file_path"
    return json.dumps({"type": "assistant", "timestamp": utc(ts), "cwd": cwd,
                       "message": {"content": [{"type": "tool_use", "name": name, "id": "t", "input": {key: path}}]}})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "projects")
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.repo, ".git"))
        os.makedirs(os.path.join(self.proj, "-repo"))
        self._saved = (fo.CLAUDE_PROJECTS, fo.wt_files)
        fo.CLAUDE_PROJECTS = self.proj
        self.dirty = ["a.py", "b.js"]
        fo.wt_files = lambda cwd: (200, {"ok": True, "cwd": cwd, "n": len(self.dirty),
                                         "files": [{"st": "M", "path": p} for p in self.dirty]})
        fo._FO.update(at=0.0, off={}, per={}, who={})
        fo._FO_GIT.clear()
        self.now = time.time()

    def tearDown(self):
        fo.CLAUDE_PROJECTS, fo.wt_files = self._saved
        fo._FO.update(at=0.0, off={}, per={}, who={})
        fo._FO_GIT.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def p(self, rel):
        return os.path.join(self.repo, rel)

    def main(self, sid, lines):
        with open(os.path.join(self.proj, "-repo", sid + ".jsonl"), "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def sub(self, sid, aid, atype, lines, desc=""):
        d = os.path.join(self.proj, "-repo", sid, "subagents")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "agent-%s.jsonl" % aid), "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        with open(os.path.join(d, "agent-%s.meta.json" % aid), "w", encoding="utf-8") as f:
            json.dump({"agentType": atype, "description": desc}, f)


class TestIndex(Base):
    def test_edit_write_multiedit_notebook(self):
        t = self.now - 60
        self.main("s1", [edit_line(t, "Edit", self.p("a.py")), edit_line(t, "Write", self.p("b.js")),
                         edit_line(t, "MultiEdit", self.p("c.md")), edit_line(t, "NotebookEdit", self.p("n.ipynb")),
                         edit_line(t, "Read", self.p("r.py"))])
        idx = fo.index(self.now)
        self.assertEqual(set(idx), {self.p("a.py"), self.p("b.js"), self.p("c.md"), self.p("n.ipynb")})
        self.assertEqual(set(idx[self.p("a.py")]), {("s1", fo.FO_MAIN)})

    def test_subagent_attributed_to_parent(self):
        self.sub("parent1", "x1", "general-purpose", [edit_line(self.now - 30, "Edit", self.p("a.py"))])
        own = fo.index(self.now)[self.p("a.py")]
        self.assertEqual(set(own), {("parent1", "x1")})
        self.assertEqual(own[("parent1", "x1")]["agent"], "general-purpose")
        self.assertEqual(fo._by_sid(own)["parent1"]["agents"], {"general-purpose"})

    def test_24h_expiry(self):
        self.main("s1", [edit_line(self.now - 25 * 3600, "Edit", self.p("old.py")),
                         edit_line(self.now - 60, "Edit", self.p("a.py"))])
        self.assertEqual(set(fo.index(self.now)), {self.p("a.py")})

    def test_incremental_append(self):
        self.main("s1", [edit_line(self.now - 60, "Edit", self.p("a.py"))])
        fo.index(self.now)
        self.main("s1", [edit_line(self.now - 10, "Edit", self.p("b.js"))])
        fo._FO["at"] = 0.0
        self.assertEqual(set(fo.index(self.now)), {self.p("a.py"), self.p("b.js")})


def live(*sids, state="run", subs=()):
    """Session rows; `subs` = aids still open (in the row's `sub` list) for every row."""
    return [{"sid": s, "cwd": "/w", "project": "p", "state": state, "ageSec": 5,
             "sub": [{"aid": a, "lab": "x", "tid": "t"} for a in subs]} for s in sids]


class WindowsEdits(unittest.TestCase):
    """Windows `file_path`s are absolute too: they used to be dropped by a `startswith("/")` test (ntpath simulated)."""

    def test_drive_paths_kept(self):
        import ntpath
        import types
        from unittest import mock
        ts = 1_700_000_000
        lines = [edit_line(ts, "Edit", "C:\\w\\repo\\a.py"), edit_line(ts, "Write", "C:/w/repo/b.js"),
                 edit_line(ts, "Edit", "repo\\rel.py")]
        with mock.patch.object(fo, "os", types.SimpleNamespace(path=ntpath, sep="\\")):
            got = fo._edits(lines)
        self.assertEqual([p for p, _ in got], ["C:\\w\\repo\\a.py", "C:\\w\\repo\\b.js"])


class TestConflict(Base):
    def test_two_live_parents_within_window(self):
        self.main("s1", [edit_line(self.now - 100, "Edit", self.p("a.py")), edit_line(self.now - 100, "Edit", self.p("b.js"))])
        self.sub("s2", "x", "general-purpose", [edit_line(self.now - 50, "Edit", self.p("a.py")),
                                                edit_line(self.now - 40, "Write", self.p("b.js"))])
        cf = fo.conflicts(live("s1", "s2", subs=("x",)), self.now)
        self.assertEqual(len(cf), 1)                       # one entry per unit set, not per file
        self.assertEqual(cf[0]["sids"], ["s1", "s2"])
        self.assertEqual(len(cf[0]["files"]), 2)
        self.assertEqual(cf[0]["by"], "s2")

    def test_cross_session_finished_subagent_is_not_conflict(self):
        self.main("s1", [edit_line(self.now - 100, "Edit", self.p("a.py"))])
        self.sub("s2", "x", "general-purpose", [edit_line(self.now - 50, "Edit", self.p("a.py"))])
        self.assertEqual(fo.conflicts(live("s1", "s2"), self.now), [])     # x no longer in s2's sub list

    def test_sibling_subagents_both_live(self):
        self.sub("s1", "x", "general-purpose", [edit_line(self.now - 100, "Edit", self.p("a.py"))])
        self.sub("s1", "y", "Explore", [edit_line(self.now - 50, "Edit", self.p("a.py"))])
        cf = fo.conflicts(live("s1", subs=("x", "y")), self.now)
        self.assertEqual(len(cf), 1)
        self.assertEqual(cf[0]["sids"], ["s1"])
        self.assertEqual(cf[0]["units"], [("s1", "x"), ("s1", "y")])
        self.assertEqual(cf[0]["labs"], ["general-purpose", "Explore"])

    def test_sibling_one_done_is_not_conflict(self):
        self.sub("s1", "x", "general-purpose", [edit_line(self.now - 100, "Edit", self.p("a.py"))])
        self.sub("s1", "y", "Explore", [edit_line(self.now - 50, "Edit", self.p("a.py"))])
        self.assertEqual(fo.conflicts(live("s1", subs=("y",)), self.now), [])

    def test_main_after_own_finished_subagent_is_not_conflict(self):
        self.sub("s1", "x", "general-purpose", [edit_line(self.now - 100, "Edit", self.p("a.py"))])
        self.main("s1", [edit_line(self.now - 50, "Edit", self.p("a.py"))])
        self.assertEqual(fo.conflicts(live("s1"), self.now), [])

    def test_main_and_own_live_subagent_is_conflict(self):
        self.sub("s1", "x", "general-purpose", [edit_line(self.now - 100, "Edit", self.p("a.py"))])
        self.main("s1", [edit_line(self.now - 50, "Edit", self.p("a.py"))])
        cf = fo.conflicts(live("s1", subs=("x",)), self.now)
        self.assertEqual([c["labs"] for c in cf], [["메인", "general-purpose"]])

    def test_label_is_agent_type_never_description(self):
        lab = fo.unit_label(("s", "x"), {"desc": "Uncommitted file owners and conflict alert", "agent": "gp"})
        self.assertEqual(lab, "gp")
        lab = fo.unit_label(("s", "x"), {"desc": "secret task", "agent": "a" * 40})
        self.assertEqual(len(lab), fo.FO_LAB_MAX)
        self.assertTrue(lab.endswith("…"))

    def test_conflict_labs_carry_no_description(self):
        self.sub("s1", "x", "general-purpose", [edit_line(self.now - 100, "Edit", self.p("a.py"))], "SECRET task x")
        self.sub("s1", "y", "Explore", [edit_line(self.now - 50, "Edit", self.p("a.py"))], "SECRET task y")
        cf = fo.conflicts(live("s1", subs=("x", "y")), self.now)
        self.assertEqual(len(cf), 1)
        self.assertNotIn("SECRET", repr(cf))

    def test_done_session_or_old_edit_is_not_conflict(self):
        self.main("s1", [edit_line(self.now - 100, "Edit", self.p("a.py"))])
        self.main("s2", [edit_line(self.now - 45 * 60, "Edit", self.p("a.py"))])
        self.assertEqual(fo.conflicts(live("s1", "s2"), self.now), [])        # s2 edited 45 min ago
        self.main("s3", [edit_line(self.now - 60, "Edit", self.p("a.py"))])
        fo._FO["at"] = 0.0
        rows = live("s1") + live("s3", state="done")
        self.assertEqual(fo.conflicts(rows, self.now), [])

    def test_committed_file_is_not_conflict(self):
        self.dirty = ["b.js"]
        self.main("s1", [edit_line(self.now - 100, "Edit", self.p("a.py"))])
        self.main("s2", [edit_line(self.now - 50, "Edit", self.p("a.py"))])
        self.assertEqual(fo.conflicts(live("s1", "s2"), self.now), [])

    def test_untracked_file_is_not_conflict(self):
        # wt_files lists untracked rows as "??"; conflicts stay tracked-only like the rail
        fo.wt_files = lambda cwd: (200, {"ok": True, "cwd": cwd, "n": 1, "files": [{"st": "??", "path": "a.py"}]})
        self.main("s1", [edit_line(self.now - 100, "Edit", self.p("a.py"))])
        self.main("s2", [edit_line(self.now - 50, "Edit", self.p("a.py"))])
        self.assertEqual(fo.conflicts(live("s1", "s2"), self.now), [])

    def test_wt_owners_shape_and_warn(self):
        self.main("s1", [edit_line(self.now - 100, "Edit", self.p("a.py"))])
        self.sub("s2", "x", "Explore", [edit_line(self.now - 50, "Edit", self.p("a.py")),
                                        edit_line(self.now - 50, "Edit", self.p("b.js"))])
        code, out = fo.wt_owners(self.repo, rows=live("s1", "s2", subs=("x",)), now=self.now)
        self.assertEqual(code, 200)
        self.assertEqual(out["warn"], ["a.py"])
        self.assertEqual([o["sid8"] for o in out["owners"]["a.py"]], ["s2", "s1"])
        self.assertEqual(set(out["owners"]["a.py"][0]), {"sid8", "proj", "agent", "ago", "live"})
        self.assertEqual(out["owners"]["b.js"][0]["agent"], "Explore")


class TestAttentionSignal(unittest.TestCase):
    def setUp(self):
        self._cf = att._conflicts
        self.now = time.time()

    def tearDown(self):
        att._conflicts = self._cf

    def test_conflict_row(self):
        g = {"sids": ["aaaaaaaa-1", "bbbbbbbb-2"], "files": ["/r/a", "/r/b"], "since": self.now - 60,
             "last": self.now - 5, "by": "bbbbbbbb-2"}
        att._conflicts = lambda rows, now: [g]
        rows = live("aaaaaaaa-1", "bbbbbbbb-2")
        out = att.attention(rows, [], read="", read_ids=[])["rows"]
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["sid"], "bbbbbbbb-2")
        self.assertEqual(out[0]["sigs"][0]["k"], "conflict")
        self.assertEqual(out[0]["why"], "충돌 위험 · 파일 2 · 세션 aaaaaaaa, bbbbbbbb")
        self.assertLess(att.ATT_PTS["conflict"], att.ATT_PTS["ask"])

    def test_within_one_session_names_agents(self):
        g = {"sids": ["aaaaaaaa-1"], "labs": ["메인", "Explore"], "files": ["/r/a"], "since": self.now - 60,
             "last": self.now - 5, "by": "aaaaaaaa-1"}
        att._conflicts = lambda rows, now: [g]
        out = att.attention(live("aaaaaaaa-1"), [], read="", read_ids=[])["rows"]
        self.assertEqual(out[0]["why"], "충돌 위험 · 파일 1 · 서브에이전트 메인, Explore")


class CacheBounds(unittest.TestCase):
    """_FO_GIT and gitinfo._GITROOT take arbitrary keys from API routes; both must stay bounded."""

    def test_fo_git_bounded(self):
        saved_git, saved_wt = dict(fo._FO_GIT), fo.wt_files
        fo._FO_GIT.clear()
        fo.wt_files = lambda root: (200, {"files": []})
        try:
            for i in range(fo.FO_GIT_MAX * 3):
                fo._dirty("/nope/r%d" % i, 1000.0)
                self.assertLessEqual(len(fo._FO_GIT), fo.FO_GIT_MAX)
            self.assertIn("/nope/r%d" % (fo.FO_GIT_MAX * 3 - 1), fo._FO_GIT)
        finally:
            fo.wt_files = saved_wt
            fo._FO_GIT.clear()
            fo._FO_GIT.update(saved_git)

    def test_gitroot_bounded(self):
        gi = sidereus("gitinfo")
        saved = dict(gi._GITROOT)
        gi._GITROOT.clear()
        try:
            base = tempfile.mkdtemp()
            for i in range(gi.GITROOT_MAX * 3):
                gi._git_root(os.path.join(base, "d%d" % i))
                self.assertLessEqual(len(gi._GITROOT), gi.GITROOT_MAX)
            os.rmdir(base)
        finally:
            gi._GITROOT.clear()
            gi._GITROOT.update(saved)


if __name__ == "__main__":
    unittest.main()
