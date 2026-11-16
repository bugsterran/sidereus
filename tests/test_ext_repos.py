"""External CLI rows carry the cwd's git fields (branch · git · repos · wt) like Claude rows, so the Branches picker lists them."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

ext = sidereus("ext")
pr = sidereus("ext_presence")
gi = sidereus("gitinfo")

NOW = 1790000000.0


class ExtRepos(unittest.TestCase):
    def patch(self, mod, name, val):
        old = getattr(mod, name)
        setattr(mod, name, val)
        self.addCleanup(setattr, mod, name, old)

    def setUp(self):
        self.base = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-extbase-"))   # stands in for the home parent
        self.addCleanup(shutil.rmtree, self.base, True)
        self.repo, self.plain, self.other = (os.path.join(self.base, "u", n) for n in ("repo", "plain", "other"))
        for d in (self.repo, self.plain, self.other):
            os.makedirs(d)
        self.calls = []
        wt = {"root": self.repo, "main": "", "name": os.path.basename(self.repo)}

        def git_state(cwd, ttl=20):               # fake `status --branch`: fills the branch cache like the real one
            self.calls.append(cwd)
            if cwd == self.repo:
                gi._git_branch_cache[cwd] = "feature/x"
                return "~1"
            return ""
        self.patch(gi, "_git_state", git_state)
        self.patch(gi, "_git_root", lambda d: next((r for r in (self.repo, self.other)
                                                    if d == r or d.startswith(r + os.sep)), ""))
        self.patch(gi, "_PATH_RE", gi._path_re(self.base))
        self.patch(gi, "_HOME", os.path.join(self.base, "u"))
        self.pi_root = os.path.join(self.base, "pi")
        self.patch(ext.plat_pi, "root", lambda: self.pi_root)
        self.patch(ext.plat_pi, "session_msgs", lambda p: {})
        self.patch(ext.plat_pi, "credit", lambda m: None)
        self.patch(gi, "_wt_of", lambda c: wt if c == self.repo else None)
        self.patch(gi, "_git_branch_cache", {})
        self.patch(gi, "_REPO_CACHE", {})            # keyed by file path: fixtures reuse one name
        for n, v in {"ext_gone_check": lambda now: None, "_ext_prune_locked": lambda now: None,
                     "ext_tok_refresh": lambda *a: None, "ext_tok": lambda *a: {}}.items():
            self.patch(ext, n, v)
        self.patch(ext.plat_pi, "ext_rev", lambda tpl=None: "0123456789ab")
        self.patch(ext.plat_pi, "installed_rev", lambda: "0123456789ab")
        self.patch(ext.plat_pi, "sid_path", lambda sid, cwd: "")

    def _pi_row(self, cwd, tpath=""):
        v = {"cwd": cwd, "state": "wait", "firstSeen": NOW - 60, "lastSeen": NOW, "transcript_path": tpath}
        self.patch(ext, "_ext", {("pi", "p-sid-1"): v})
        (row,) = ext.ext_rows()
        return row

    def _pi_file(self, calls):
        d = os.path.join(self.pi_root, "sessions", "--w--")
        os.makedirs(d, exist_ok=True)
        fp = os.path.join(d, "2026-11-16_p-sid-1.jsonl")
        lines = [{"type": "session", "id": "p-sid-1", "cwd": self.repo}]
        for name, path in calls:
            lines.append({"type": "message", "message": {"role": "assistant", "content": [
                {"type": "toolCall", "id": "c1", "name": name, "arguments": {"path": path, "content": "x"}}]}})
        with open(fp, "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(x) + "\n" for x in lines))
        return fp

    def test_pi_edit_outside_cwd_adds_repo(self):
        fp = self._pi_file([("edit", os.path.join(self.other, "a.py"))])
        r = self._pi_row(self.repo, fp)
        self.assertEqual(r["repos"], [self.repo, self.other])   # cwd root first

    def test_pi_relative_write_and_read_only(self):
        # a cwd-relative write reaches the sibling repo; a read of another repo is not an edit
        fp = self._pi_file([("read", os.path.join(self.other, "b.py")), ("write", "../other/c.py")])
        self.assertEqual(self._pi_row(self.repo, fp)["repos"], [self.repo, self.other])
        fp = self._pi_file([("read", os.path.join(self.other, "b.py"))])
        gi._REPO_CACHE.pop(fp, None)
        self.assertEqual(self._pi_row(self.repo, fp)["repos"], [self.repo])

    def test_pi_file_outside_sessions_ignored(self):
        fp = os.path.join(self.base, "x.jsonl")
        with open(fp, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "message", "message": {"role": "assistant", "content": [
                {"type": "toolCall", "name": "edit", "arguments": {"path": os.path.join(self.other, "a.py")}}]}}) + "\n")
        self.assertEqual(self._pi_row(self.repo, fp)["repos"], [self.repo])

    def test_pi_presence_row_reads_session_file(self):
        fp = self._pi_file([("edit", os.path.join(self.other, "a.py"))])
        r = pr._row("pi", {"sid": "p-4", "cwd": self.repo, "path": fp, "start": NOW - 60, "mtime": NOW}, NOW)
        self.assertEqual(r["repos"], [self.repo, self.other])

    def test_pi_hook_row_in_git_repo(self):
        r = self._pi_row(self.repo)
        self.assertEqual((r["branch"], r["git"], r["repos"]), ("feature/x", "~1", [self.repo]))
        self.assertEqual(r["wt"]["root"], self.repo)

    def test_pi_hook_row_outside_git(self):
        r = self._pi_row(self.plain)
        self.assertEqual((r["branch"], r["git"], r["repos"], r["wt"]), ("", "", [], None))

    def test_missing_cwd_forks_no_git(self):
        r = self._pi_row(os.path.join(self.plain, "gone"))
        self.assertEqual((r["branch"], r["repos"], r["wt"]), ("", [], None))
        self.assertEqual(self.calls, [])

    def test_codex_rollout_row(self):
        c = {"sid": "cx-1", "cwd": self.repo, "start": NOW - 100, "mtime": NOW - 10, "live": True, "kind": ""}
        self.patch(ext, "_rollouts", lambda now: [c])
        self.patch(ext, "_codex_running", lambda: True)
        self.patch(ext, "_ext", {})
        self.patch(ext, "_runs", {})
        self.patch(ext, "ext_ended", lambda plat, now: set())
        (r,) = ext.ext_rollout_rows(NOW)
        self.assertEqual((r["branch"], r["repos"]), ("feature/x", [self.repo]))

    def test_pi_presence_row(self):
        r = pr._row("pi", {"sid": "p-2", "cwd": self.repo, "start": NOW - 60, "mtime": NOW, "branch": "stale"}, NOW)
        self.assertEqual((r["branch"], r["repos"]), ("feature/x", [self.repo]))
        r = pr._row("pi", {"sid": "p-3", "cwd": self.plain, "start": NOW - 60, "mtime": NOW}, NOW)
        self.assertEqual((r["branch"], r["repos"], r["wt"]), ("", [], None))


if __name__ == "__main__":
    unittest.main()
