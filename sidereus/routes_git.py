"""Git GET route handlers (split out of routes_get.py) — a mixin `_GetRoutes` inherits.
Methods use `self._raw_json` from Handler."""
import os
from urllib.parse import parse_qs

from sidereus.git import BRANCH_N_DEF, _branch_ok, branch_graph, git_commit, git_diff, git_file_diff, wt_files
from sidereus.file_owner import wt_owners
from sidereus.commit_link import commit_links
from sidereus.routes_struct import _q1, _exc_err


class _GitRoutes:
    def _g_branches(self, u):
        # ★Branch graph raw data (2026-09-23). ⚠Do not attach to polling — called only when the screen clicks.
        #   Path confinement is `_branch_ok()` — only repos the screen knows (session cwd + touched repos) open.
        q = parse_qs(u.query)
        cwd = _q1(q, "cwd")
        code = 200
        if not cwd or not os.path.isdir(cwd):
            code, out = 400, {"ok": False, "err": "cwd required"}
        elif not _branch_ok(cwd):
            code, out = 403, {"ok": False, "err": "not allowed"}
        else:
            try:
                out = branch_graph(cwd, (q.get("n") or [str(BRANCH_N_DEF)])[0])
            except Exception as e:
                out = {"ok": False, "err": _exc_err(e)}
        self._raw_json(code, out)

    def _g_wtfiles(self, u):
        # Branches tab work unit: one worktree's uncommitted files (click-only). Validation lives in wt_files().
        q = parse_qs(u.query)
        try:
            code, out = wt_files(_q1(q, "cwd"))
        except Exception as e:
            code, out = 500, {"ok": False, "err": _exc_err(e)}
        self._raw_json(code, out)

    def _g_owners(self, u):
        # Branches tab work unit: which sessions edited each uncommitted file (metadata only). Validation lives in wt_files().
        q = parse_qs(u.query)
        try:
            code, out = wt_owners(_q1(q, "cwd"))
        except Exception as e:
            code, out = 500, {"ok": False, "err": _exc_err(e)}
        self._raw_json(code, out)

    def _g_commit(self, u):
        # Branches tab commit details (read-only, click-only). Validation lives in git_commit().
        q = parse_qs(u.query)
        try:
            code, out = git_commit(_q1(q, "repo"), _q1(q, "sha"),
                                   _q1(q, "path"))
        except Exception as e:
            code, out = 500, {"ok": False, "err": _exc_err(e)}
        self._raw_json(code, out)

    def _g_git_links(self, u):
        # Branch tab, after the graph paints: commit -> session/agent/cost (metadata only, sidereus/commit_link.py).
        q = parse_qs(u.query)
        try:
            code, out = commit_links(_q1(q, "repo"), _q1(q, "shas"))
        except Exception as e:
            code, out = 500, {"ok": False, "err": _exc_err(e)}
        self._raw_json(code, out)

    def _g_git_file(self, u):
        q = parse_qs(u.query)
        try:
            out = git_file_diff(_q1(q, "cwd"), _q1(q, "path"),
                                (q.get("scope") or ["all"])[0])
        except Exception as e:
            out = {"ok": False, "msg": "Failed ({err})", "vars": {"err": f"{type(e).__name__}: {e}"}}
        self._raw_json(200, out)

    def _g_git_diff(self, u):
        # ★Do not import inside the function — the name becomes a local for the whole function,
        #   and parse_qs in /api/state died with UnboundLocalError (measured 2026-08-25).
        q = parse_qs(u.query)
        cwd = _q1(q, "cwd")
        try:
            out = git_diff(cwd, (q.get("scope") or ["all"])[0],
                           (q.get("pw") or ["today"])[0], _q1(q, "view") or "", _q1(q, "new") or "",
                           _q1(q, "sid") or "", _q1(q, "base") or "", "1" if _q1(q, "untr") == "1" else "")
        except Exception as e:
            out = {"ok": False, "msg": "Failed ({err})", "vars": {"err": f"{type(e).__name__}: {e}"}}
        self._raw_json(200, out)
