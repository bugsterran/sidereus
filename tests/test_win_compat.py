"""Windows-only gaps simulated on any OS: missing os.O_NOFOLLOW/O_NONBLOCK (git_view), `%-m` strftime (structure_scan),
and path rules (`\\` separator, case, drive roots) via a module `os` swapped for ntpath."""
import importlib.util
import json
import ntpath
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from unittest import mock

from tests._load import ROOT, sidereus

gv = sidereus("git_view")
ss = sidereus("structure_scan")


class _NoFlagOs:
    """`os` without the POSIX-only open flags, like Windows."""

    def __getattr__(self, name):
        if name in ("O_NOFOLLOW", "O_NONBLOCK"):
            raise AttributeError(name)
        return getattr(os, name)


class ReadSmallNoFlags(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)

    def test_reads_and_still_refuses_symlink(self):
        real = os.path.join(self.d, "real")
        with open(real, "w", encoding="utf-8") as fh:
            fh.write("a\n")
        with mock.patch.object(gv, "os", _NoFlagOs()):
            self.assertEqual(gv._read_small(real), b"a\n")
            if hasattr(os, "symlink"):
                ln = os.path.join(self.d, "ln")
                try:
                    os.symlink(real, ln)
                except OSError:
                    return            # no symlink privilege (Windows without developer mode)
                self.assertIsNone(gv._read_small(ln))


class StructLabel(unittest.TestCase):
    def test_portable_format(self):
        class D(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 10, 17, 12, 0)
        ts_now = datetime(2026, 3, 5, 9, 7).timestamp()
        ts_old = datetime(2024, 1, 2, 9, 7).timestamp()
        with mock.patch.object(ss, "datetime", D):
            self.assertEqual(ss._struct_label(ts_now), "3/5 09:07")
            self.assertEqual(ss._struct_label(ts_old), "2024.1.2")


class _NtOs:
    """`os` with Windows path rules (ntpath, `\\` separator); everything else is the real os."""
    sep, altsep, name, path = "\\", "/", "nt", ntpath

    def __getattr__(self, name):
        return getattr(os, name)


def _load_accounts():
    spec = importlib.util.spec_from_file_location(
        "fa_accounts_win", os.path.join(ROOT, "plugins", "orbit", "scripts", "accounts.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class WindowsPaths(unittest.TestCase):
    """Separator / case / drive-root rules, simulated by swapping a module's `os` for _NtOs."""

    def test_cmd_split_keeps_backslash_and_drops_inner_quotes(self):
        hf, hn = sidereus("hook_fields"), sidereus("harness")
        cmd = 'node "${R}"/scripts/run.cjs C:\\h\\x.mjs'
        with mock.patch.object(hf.os, "name", "nt"):
            for f in (hf.split_cmd, hn._argv):
                self.assertEqual(f(cmd), ["node", "${R}/scripts/run.cjs", "C:\\h\\x.mjs"])

    def test_work_guard_refuses_drive_root(self):
        w = sidereus("work")
        with mock.patch.object(w, "os", _NtOs()):
            with mock.patch.object(w.claude_roots, "projects_dirs", lambda prim: ["D:\\"]):
                self.assertEqual(w._under_projects("D:\\etc\\hosts"), "")
            with mock.patch.object(w.claude_roots, "projects_dirs", lambda prim: ["D:\\cl\\projects"]):
                self.assertEqual(w._under_projects("d:\\CL\\projects\\p\\s.jsonl"), "d:\\CL\\projects\\p\\s.jsonl")
                self.assertEqual(w._under_projects("D:\\cl\\projects2\\s.jsonl"), "")

    def test_subagent_paths_any_separator(self):
        ag = sidereus("agents")
        with mock.patch.object(ag, "os", _NtOs()):
            self.assertEqual(ag.sub_sess_dir("C:\\p\\s1\\subagents\\agent-a.jsonl"), "C:\\p\\s1")
            self.assertEqual(ag.sub_sess_dir("C:\\p/s1/subagents\\workflows\\wf_x\\agent-a.jsonl"), "C:\\p/s1")
            self.assertIn("/subagents/", ag.slash("C:\\p\\s1\\subagents\\a.jsonl"))
            self.assertEqual(ag.sub_sess_dir("C:\\p\\s1.jsonl"), "")

    def test_agent_cost_counts_backslash_and_mixed_paths(self):
        ac, ag = sidereus("agentcost"), sidereus("agents")
        h = {"7200": {"m": [10, 0, 0, 0]}}
        items = [("C:\\p\\s1\\subagents\\agent-a.jsonl", h), ("/p/s2/subagents\\agent-b.jsonl", h), ("C:\\p\\s1.jsonl", h)]
        with mock.patch.object(ag, "os", _NtOs()):
            runs, tot = ac._agc_top(items, 0)
        self.assertEqual((sorted(fp for _t, fp in runs), tot), (sorted(fp for fp, _h in items[:2]), 30))

    def test_workflow_name_from_escaped_windows_paths(self):
        ag = sidereus("agents")
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        sess = os.path.join(d, "s1")
        line = {"type": "user", "content": "Transcript dir: C:\\u\\s1\\subagents\\workflows\\wf_ab\n"
                                           "Script file: C:\\repo\\.claude\\workflows\\sidereus-change.js\nRun ID: wf_ab"}
        with open(sess + ".jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
        with mock.patch.object(ag, "os", _NtOs()):
            self.assertEqual(ag._wf_name(sess, "C:\\u\\s1\\subagents\\workflows\\wf_ab"), "sidereus-change")

    def test_mail_watch_prefix_ignores_case_and_separator(self):
        pf = sidereus("prefs")
        v = {"mode": "off", "projects": {"c:/P/a": "on"}}
        with mock.patch.object(pf, "os", _NtOs()):
            self.assertTrue(pf.watch_on("C:\\p\\A\\sub", v))
            self.assertFalse(pf.watch_on("C:\\p\\ab", v))

    def test_pl_runs_proj_refuses_dotdot_either_separator(self):
        pr = sidereus("pl_runs")
        for bad in ("/a/../b", "/a\\..\\b"):
            self.assertEqual(pr._proj(bad), "")
        self.assertEqual(pr._proj("/a/..b"), "/a/..b")

    def test_steps_cd_skips_cmd_d_flag(self):
        st = sidereus("steps")
        cd, _w = st._path_res(True)
        self.assertEqual(cd.search("cd /d C:\\x\\y && echo > a.py").group(1), "C:\\x\\y")
        self.assertEqual(cd.search("cd C:\\RUNNER~1\\x").group(1), "C:\\RUNNER~1\\x")

    def test_orbit_registry_paths(self):
        acc = _load_accounts()
        with mock.patch.object(acc, "os", _NtOs()), mock.patch.dict(os.environ, {"HOME": "C:\\Users\\me"}):
            self.assertEqual(acc.tilde("C:\\Users\\me\\src\\acme"), "~/src/acme")
            self.assertEqual(acc.tilde("c:\\users\\ME"), "~")
            self.assertEqual(acc.tilde("C:\\Users\\meme"), "C:\\Users\\meme")
            self.assertTrue(acc.under("c:\\users\\me\\x", "C:\\Users\\me"))
            self.assertEqual(acc.expand("~/src/acme"), "C:\\Users\\me\\src\\acme")
            uid = os.getuid() if hasattr(os, "getuid") else 0
            self.assertTrue(acc.safe_owner(os.stat_result((0o100666, 0, 0, 0, uid, 0, 0, 0, 0, 0))))   # mode bits ignored


if __name__ == "__main__":
    unittest.main()
