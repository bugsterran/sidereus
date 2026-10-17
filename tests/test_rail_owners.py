"""Rail owner join (git_rail._rail_owners): file_owner index -> per-file `own` chips + cross-session `conflict` flag."""
import time
import unittest

from tests._load import sidereus

gv = sidereus("git_rail")   # rail owner join moved from git_view (2026-09-25)
fo = sidereus("file_owner")


def live(*sids, subs=()):
    return [{"sid": s, "state": "run", "sub": [{"aid": a} for a in subs]} for s in sids]


class TestRailOwners(unittest.TestCase):
    def setUp(self):
        self.now = time.time()
        self._idx = fo.index
        self.fake = {}
        fo.index = lambda now=None: self.fake
        self._home, self.homes = gv._rail_home, {}
        gv._rail_home = lambda fo_, sid, *cwds: self.homes.get(sid, "")   # no live ~/.claude/projects reads

    def tearDown(self):
        fo.index = self._idx
        gv._rail_home = self._home

    def unit(self, ago, n=1, agent="", desc=""):
        return {"ts": self.now - ago, "n": n, "agent": agent, "desc": desc, "cwd": "/r"}

    def join(self, rows, *paths):
        files = [{"path": p} for p in paths]
        gv._rail_owners("/r", files, rows=rows, now=self.now)
        return {f["path"]: f for f in files}

    def test_chip_data(self):
        self.fake = {"/r/a.py": {("s1aaaaaaaa", fo.FO_MAIN): self.unit(300, 2),
                                 ("s1aaaaaaaa", "x1"): self.unit(60, 5, "general-purpose", "Fix rail " + "x" * 80)}}
        f = self.join(live("s1aaaaaaaa"), "a.py", "b.py")
        own = f["a.py"]["own"]
        self.assertEqual([o["main"] for o in own], [False, True])          # latest editor first
        self.assertEqual((own[0]["n"], own[0]["agent"], own[0]["sid8"], own[0]["ago"]), (5, "general-purpose", "s1aaaaaa", 60))
        self.assertEqual(len(own[0]["lab"]), gv.RAIL_OWN_LAB)
        self.assertEqual(own[1]["lab"], "")
        self.assertNotIn("own", f["b.py"])                                 # edited outside Claude: no chip
        self.assertNotIn("conflict", f["a.py"])

    def test_same_session_agents_not_conflict(self):
        self.fake = {"/r/a.py": {("s1", "x1"): self.unit(60), ("s1", "x2"): self.unit(30)}}
        self.assertNotIn("conflict", self.join(live("s1", subs=("x1", "x2")), "a.py")["a.py"])

    def test_two_sessions_conflict(self):
        self.fake = {"/r/a.py": {("s1", fo.FO_MAIN): self.unit(60), ("s2", "x2"): self.unit(30)}}
        self.assertTrue(self.join(live("s1", "s2", subs=("x2",)), "a.py")["a.py"]["conflict"])

    def test_stale_or_dead_session_not_conflict(self):
        self.fake = {"/r/a.py": {("s1", fo.FO_MAIN): self.unit(fo.FO_CONFLICT_S + 60), ("s2", fo.FO_MAIN): self.unit(30)}}
        self.assertNotIn("conflict", self.join(live("s1", "s2"), "a.py")["a.py"])
        self.fake = {"/r/a.py": {("s1", fo.FO_MAIN): self.unit(60), ("s2", fo.FO_MAIN): self.unit(30)}}
        self.assertNotIn("conflict", self.join(live("s2"), "a.py")["a.py"])

    def test_committed_file_not_conflict(self):
        self.fake = {"/r/a.py": {("s1", fo.FO_MAIN): self.unit(60), ("s2", "x2"): self.unit(30)}}
        rows, files = live("s1", "s2", subs=("x2",)), [{"path": "a.py"}]
        gv._rail_owners("/r", files, rows=rows, now=self.now, dirty={"b.py"})     # base=remote: committed, unpushed
        self.assertNotIn("conflict", files[0])
        gv._rail_owners("/r", files, rows=rows, now=self.now, dirty={"a.py"})
        self.assertTrue(files[0]["conflict"])

    def test_status_tracked(self):
        st = "\0".join(["# branch.oid abc", "1 .M N... 100644 100644 100644 h1 h2 dir/a b.py",
                        "2 R. N... 100644 100644 100644 h1 h2 R100 new.py", "old.py",
                        "u UU N... 100644 100644 100644 100644 h1 h2 h3 m.py", "? untracked.py", ""])
        self.assertEqual(gv._status_tracked(st), {"dir/a b.py", "new.py", "old.py", "m.py"})
        self.assertEqual(gv._status_tracked(""), set())

    def test_popup_ids(self):
        saved = gv._rail_tid
        gv._rail_tid = lambda fo_, sid, aid, home: "toolu_" + aid if aid == "x1" and home == "-r" else ""
        self.homes = {"s1aaaaaaaa": "-r"}
        try:
            self.fake = {"/r/a.py": {("s1aaaaaaaa", fo.FO_MAIN): self.unit(300),
                                     ("s1aaaaaaaa", "x1"): self.unit(60, agent="Explore"),
                                     ("s2bbbbbbbb", "x9"): self.unit(30, agent="Explore")}}
            rows = [{"sid": "s1aaaaaaaa", "state": "run", "project": "proj1"}]
            own = {(o["sid"], o["tid"], o["main"]): o for o in self.join(rows, "a.py")["a.py"]["own"]}
        finally:
            gv._rail_tid = saved
        self.assertEqual(set(own), {("s1aaaaaaaa", "", True), ("s1aaaaaaaa", "toolu_x1", False), ("s2bbbbbbbb", "", False)})
        m = own[("s1aaaaaaaa", "", True)]
        self.assertEqual((m["cwd"], m["proj"]), ("/r", "proj1"))
        self.assertEqual(own[("s2bbbbbbbb", "", False)]["proj"], "r")     # not on screen: folder name

    def test_popup_cwd_is_session_home(self):
        """Worktree agent: the edit's cwd is not the project dir, so the popup gets a cwd that slugs to it."""
        self.fake = {"/r/a.py": {("s1", "x1"): dict(self.unit(60), cwd="/wt/x"),
                                 ("s2", "x2"): dict(self.unit(30), cwd="/wt/y")}}
        self.homes = {"s1": "-r", "s2": "-r"}
        saved = gv._cwd_from_slug
        gv._cwd_from_slug = lambda name: "/r" if name == "-r" else ""
        try:
            own = {o["sid"]: o for o in self.join([{"sid": "s1", "state": "run", "cwd": "/r"}], "a.py")["a.py"]["own"]}
        finally:
            gv._cwd_from_slug = saved
        self.assertEqual(own["s1"]["cwd"], "/r")          # on screen: the session row's cwd
        self.assertEqual(own["s2"]["cwd"], "/r")          # past session: cwd rebuilt from the project dir name
        self.assertEqual(gv._rail_pcwd("", "", "/wt/x"), "/wt/x")   # dir unknown: keep the edit's cwd

    def test_rail_home_and_tid(self):
        import json, os, tempfile
        saved, real_glob = (fo.CLAUDE_PROJECTS, self._home), gv.glob.glob
        gv._rail_home = self._home
        calls = []
        gv.glob.glob = lambda p: calls.append(p) or real_glob(p)
        gv._rail_home_c.clear()
        with tempfile.TemporaryDirectory() as d:
            sub = os.path.join(d, "-r", "s1", "subagents")
            os.makedirs(sub)
            with open(os.path.join(sub, "agent-x1.meta.json"), "w", encoding="utf-8") as f:
                json.dump({"toolUseId": "toolu_1", "agentType": "Explore"}, f)
            open(os.path.join(d, "-r", "s3.jsonl"), "w", encoding="utf-8").close()          # main-only session: no <sid> dir
            fo.CLAUDE_PROJECTS = d
            try:
                self.assertEqual(gv._rail_home(fo, "s1", "", "/r"), "-r")
                self.assertEqual(calls, [])                                # slug hit: no glob
                gv._rail_home_c.clear()
                self.assertEqual(gv._rail_home(fo, "s1", "/elsewhere"), "-r")   # glob fallback
                n = len(calls)
                self.assertEqual(gv._rail_home(fo, "s1", "/elsewhere"), "-r")
                self.assertEqual(len(calls), n)                            # memo: no second glob
                self.assertEqual(gv._rail_home(fo, "s3", "/elsewhere"), "-r")
                self.assertEqual(gv._rail_home(fo, "../x", "/r"), "")
                self.assertEqual(gv._rail_tid(fo, "s1", "x1", "-r"), "toolu_1")
                self.assertEqual(gv._rail_tid(fo, "s1", "nope", "-r"), "")
            finally:
                fo.CLAUDE_PROJECTS, gv._rail_home = saved
                gv.glob.glob = real_glob
                gv._rail_home_c.clear()


class TestIndexCount(unittest.TestCase):
    def test_count_in_index(self):
        saved = dict(fo._FO), dict(fo._FO_N)
        try:
            fo._FO.update(at=time.time() + 1e6, off={"t": (0, 1)}, per={"t": {"/r/a.py": time.time() - 5}},
                          who={"t": ("s1", fo.FO_MAIN, "", "", "/r")})
            fo._FO_N.clear()
            fo._FO_N["t"] = {"/r/a.py": 3}
            self.assertEqual(fo.index()["/r/a.py"][("s1", fo.FO_MAIN)]["n"], 3)
        finally:
            fo._FO.clear(); fo._FO.update(saved[0]); fo._FO_N.clear(); fo._FO_N.update(saved[1])


if __name__ == "__main__":
    unittest.main()
