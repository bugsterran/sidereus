"""Aggregate scanners loop every Claude projects dir (claude_roots.projects_dirs); temp dirs only."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

T0 = 1_900_000_000   # fixed epoch: the scanners get `now` passed in, file mtimes are set with os.utime

ui = sidereus("usage_index")
ti = sidereus("toolidx")
cl = sidereus("commit_link")
fs = sidereus("failures_scan")
gv = sidereus("git_rail")
fo = sidereus("file_owner")
st = sidereus("structure_tree")
cr = sidereus("claude_roots")


def _touch(*parts):
    p = os.path.join(*parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write("{}\n")
    return p


class ScanRootsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-scanroots-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.prim = os.path.join(self.tmp, "a", "projects")
        self.extra = os.path.join(self.tmp, "b", "projects")
        self.p1 = _touch(self.prim, "-p1", "s1.jsonl")
        self.p2 = _touch(self.extra, "-p2", "s2.jsonl")
        self.a2 = _touch(self.extra, "-p2", "s2", "subagents", "agent-x1.jsonl")
        dirs = lambda primary: [primary, self.extra]
        for mod, name in ((ui, "CLAUDE_PROJECTS"), (ti, "CLAUDE_PROJECTS"), (fs, "CLAUDE_PROJECTS"),
                          (fo, "CLAUDE_PROJECTS"), (cl, "CL_ROOT")):
            self._patch(mod, name, self.prim)
        for mod in (ui, ti, cl, fs, gv, fo):
            self._patch(mod, "projects_dirs", dirs)

    def _patch(self, mod, name, val):
        p = mock.patch.object(mod, name, val)
        p.start()
        self.addCleanup(p.stop)

    def test_usage_index_paths(self):
        got = sorted(ui._uidx_paths())
        self.assertIn((self.p1, "-p1"), got)
        self.assertIn((self.p2, "-p2"), got)
        self.assertIn((self.a2, "-p2"), got)

    def test_toolidx_paths_and_primary_only_cache(self):
        self.assertEqual(set(ti._paths()), {self.p1, self.p2, self.a2})
        self._patch(ti, "TI_CACHE", os.path.join(self.tmp, "ti.json"))
        self._patch(ti, "_TI_ROOT", self.prim)
        ent = ti._new_ent(1, 1)
        self._patch(ti, "_TI_FILES", {self.p1: ent, self.p2: ent})
        self._patch(ti, "_TI_STATE", {"dirty": True, "saved": 0.0})
        # cache: a header line, then one JSON row per file whose first item is the path.
        rows = ti._snapshot(T0)[1:]
        self.assertEqual([json.loads(r)[0] for r in rows], [self.p1])   # extras are never persisted

    def test_commit_link_paths(self):
        self.assertEqual(set(cl._cl_paths()), {self.p1, self.p2, self.a2})

    def test_failures_sub_paths(self):
        self._patch(fs, "_recent_transcripts", lambda now, h: [])
        os.utime(self.a2, (T0 - 60, T0 - 60))
        got = [p for _mt, p in fs._fail_transcripts(T0, 24)]
        self.assertEqual(got, [self.a2])

    def test_rail_home_and_tid_in_extra_root(self):
        gv._rail_home_c.clear()
        self.addCleanup(gv._rail_home_c.clear)
        self.assertEqual(gv._rail_home(fo, "s2", "/elsewhere"), "-p2")
        self._patch(gv, "_agent_meta", lambda d: {"toolu_9": {"_id": "x1"}} if d.startswith(self.extra) else {})
        self.assertEqual(gv._rail_tid(fo, "s2", "x1", "-p2"), "toolu_9")

    def test_structure_refuses_extra_root(self):
        root = os.path.dirname(self.extra)
        self._patch(st, "claude_accounts", lambda: [{"dir": root, "label": "b", "primary": False}])
        self.assertTrue(st._claude_hit(os.path.realpath(os.path.join(root, "projects"))))

    def test_structure_refuses_shared_history_profile(self):
        # a profile whose projects/ is shared is not a scan root but is still an account: its config dir is refused
        alt = tempfile.mkdtemp(prefix="sidereus-scanroots-alt-")
        self.addCleanup(shutil.rmtree, alt, True)
        self._patch(cr, "roots", lambda: [])
        self._patch(cr, "accounts", lambda: [{"dir": alt, "label": "alt", "primary": False}])
        self._patch(st, "claude_accounts", cr.accounts)
        self.assertTrue(st._claude_hit(os.path.realpath(os.path.join(alt, "settings.json"))))


class SingleRootTest(unittest.TestCase):
    def test_single_root_is_unchanged(self):
        home = tempfile.mkdtemp(prefix="sidereus-scanroots-home-")
        self.addCleanup(shutil.rmtree, home, True)
        prim = os.path.join(home, ".claude")
        os.makedirs(os.path.join(prim, "projects"))
        for name, val in (("SCAN_HOME", home), ("claude_home", lambda: prim), ("effective", lambda k: [])):
            p = mock.patch.object(cr, name, val)
            p.start()
            self.addCleanup(p.stop)
        cr.reset()
        self.addCleanup(cr.reset)
        pp = os.path.join(prim, "projects")
        p1 = _touch(pp, "-p1", "s1.jsonl")
        with mock.patch.object(ui, "CLAUDE_PROJECTS", pp), mock.patch.object(ui, "projects_dirs", cr.projects_dirs):
            self.assertEqual(ui._uidx_paths(), [(p1, "-p1")])


if __name__ == "__main__":
    unittest.main()
