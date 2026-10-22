"""Single-repo git views: access guard (_repo_ok/_branch_ok), file diff, pushed/unpushed diff, commit detail
(remote freshness and git-flow config moved to sidereus/git_flow.py). Split from sidereus/git.py (2026-09-24); git.py re-exports what others import.
The changes rail (view="rail") lives in sidereus/git_rail.py (split 2026-09-25); git_diff reaches it lazily."""
import os
import re
import stat as _st                     # git_diff has a local named `stat`
import subprocess
from sidereus import config
from sidereus.config import CODE_DIR
from sidereus.gitinfo import DIFF_MAX, DIFF_TIMEOUT, SHA_HEX_RE, _git_run, _git_run_capped, _wt_main
from sidereus.sessions import sessions_rows
from sidereus.warn import warn_once
# ⚠Remote freshness + git-flow live in sidereus/git_flow.py; re-exported for git/git_rail.
from sidereus.git_flow import (BR_FETCH_STALE_H, _git_common_dir, flow_base, flow_info, flow_parse,  # noqa: F401
                            remote_info)


FULL_MAX = 400_000          # full-expand cap — a single file, so more generous than the diff cap
STAT_FILES_MAX = 2000       # numstat rows sent with the diff window (the patch itself is cut at DIFF_MAX)
DIFF_UNTR_MAX = 40          # untracked files appended with `untr=1`; each is read whole up to RAIL_READ_MAX


def _numstat(text):
    """`--numstat -z -M` → [{path, from, add, del, bin}]. ⚠A rename is `a\\td\\t\\0old\\0new\\0` (empty third field)."""
    out, recs, i = [], text.split("\0"), 0
    while i < len(recs):
        p = recs[i].split("\t", 2)
        i += 1
        if len(p) < 3:
            continue
        path, frm = p[2], ""
        if not path:
            if i + 1 >= len(recs):
                break
            frm, path = recs[i], recs[i + 1]
            i += 2
        if not path:
            continue
        binf = p[0].strip() == "-"
        out.append({"path": path, "from": frm, "add": 0 if binf else int(p[0] or 0),
                    "del": 0 if binf else int(p[1] or 0), "bin": binf})
    return out


def _repo_ok(cwd, allowed):
    if not cwd:
        return False
    if cwd in allowed:
        return True
    main = _wt_main(cwd)
    return bool(main) and main in allowed


def git_file_diff(cwd, path, scope="all"):
    """One file with **full context**. A large `-U` yields the whole file as a diff (GitHub's expand all).

    ★Why a separate endpoint: full context is tens of KB per file and cannot go into the default response.
      Called **only on click**.
    ★Path validation: the repo against the same allow list as git_diff; for the file, ask git directly whether the repo
      **tracks** it (`ls-files --error-unmatch`). Filtering `..` by string is bypassed by symlinks or
      encodings — leaving the decision to git is safer."""
    allowed = set()
    for r in sessions_rows():   # ⚠request path: snapshot allow-list, never a cold sessions()
        if r.get("cwd"):
            allowed.add(r["cwd"])
        allowed.update(r.get("repos") or [])
    if not _repo_ok(cwd, allowed):
        return {"ok": False, "msg": "Only repositories touched by a session on screen can be viewed."}
    if not path:
        return {"ok": False, "msg": "A file path is required."}
    # ⚠A raw path is a pathspec: `:(glob)**` passed --error-unmatch and diffed the whole repo with -U1000000.
    #   Magic prefixes and NUL are refused outright, and every git call gets `:(literal)` (as _untracked_patch does).
    if not isinstance(path, str) or path.startswith(":") or "\0" in path:
        return {"ok": False, "msg": "The file path is not valid."}
    lit = ":(literal)" + path

    def run(args):
        return _git_run(cwd, args, DIFF_TIMEOUT)

    try:
        base = _base_scope(cwd, scope)
        if base is None:
            return {"ok": False, "msg": "Only ancestor commits of this branch can be used as the base."}
        chk = run(["ls-files", "--error-unmatch", "--", lit])
        if chk.returncode != 0:
            body = _untracked_patch(cwd, path) if (scope == "work" or base) else ""
            if not body:
                return {"ok": False, "msg": "This file is not tracked by the repository."}
            return {"ok": True, "path": path, "diff": body[:FULL_MAX],
                    "cutBytes": len(body) if len(body) > FULL_MAX else 0}
        # ★Use **the same base as the scope being viewed** (2026-09-01; full expand showed nothing).
        #   It was always `@{u}` — when viewing an already-pushed commit the difference against that base is 0,
        #   so full expand was blank. Expanding something other than what the screen showed is wrong.
        has_up = bool(run(["rev-parse", "--abbrev-ref", "@{u}"]).stdout.strip())
        U = f"-U{10**6}"
        if base:
            a = ["diff", base, U, "--", lit]
        elif str(scope).startswith("c:"):
            sha = str(scope)[2:]
            if not _SHA_RE.match(sha):
                return {"ok": False, "msg": "Not a commit hash."}
            # ⚠A renamed file needs -M and both paths in the pathspec, else it expands as a brand-new file.
            frm = next((s["from"] for s in _numstat(run(["show", "-M", sha, "--numstat", "-z", "--format="]).stdout)
                        if s["path"] == path and s["from"]), "")
            a = ["show", "-M", sha, "--patch", "--format=", U, "--", lit] + ([":(literal)" + frm] if frm else [])
        elif scope == "work" or not has_up:
            a = ["diff", "HEAD", U, "--", lit]
        elif scope == "commit":
            a = ["diff", "@{u}", "HEAD", U, "--", lit]
        else:
            a = ["diff", "@{u}", U, "--", lit]
        body, total = _git_run_capped(cwd, a, DIFF_TIMEOUT, FULL_MAX)
    except subprocess.TimeoutExpired:
        return {"ok": False, "msg": "git did not answer within {n} s.", "vars": {"n": DIFF_TIMEOUT}}
    except Exception as e:
        return {"ok": False, "msg": "git failed ({err})", "vars": {"err": type(e).__name__}}

    cut = total > FULL_MAX
    return {"ok": True, "path": path, "diff": body[:FULL_MAX],
            "cutBytes": total if cut else 0}


# ★The scope must be selectable (2026-08-26; review committed-but-unpushed changes before pushing).
#   all    = @{u}        unpushed commits + working tree (default)
#   commit = @{u}..HEAD  committed but not yet pushed — **for review right before push**
#   work   = HEAD        not yet committed only
DIFF_SCOPES = {"all": "Unpushed + working tree", "commit": "Committed (unpushed)", "work": "Working tree (uncommitted)"}
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")     # validates the single-commit scope `c:<sha>`
# ★Pushed commits are cut **by period, not count** (2026-08-26; dozens of pushes per day, only 5 shown).
#   Measurement backed it — repo-B 34 today · 176 in 7 days, agent-A 16 today · 119.
#   A count of 5 holds not even 1/7 of "today's work".
#   No author filter: all 305 commits in 7 days were **the same person** (agents commit under that name too).
#   Cost is one log call; each commit's diff is fetched only on click. Only a cap is set.
PUSHED_WINDOWS = {"today": ("--since=midnight", "Today"),
                  "3d": ("--since=3.days", "3 days"),
                  "7d": ("--since=7.days", "7 days")}
PUSHED_CAP = 120                              # even over a wide period, cut beyond this and **say it was cut**


# ★Commit times are **sent as unix seconds and converted to local time by the UI** (2026-08-26).
#   Why the server does not bake strings: this file already made that mistake — slicing transcript UTC strings
#   as is printed 8 AM as 22:58. Time conversion is the browser's job.
_LOG_FMT = "--format=%h%x09%ct%x09%s"


def _commits(run, rng, limit=None):
    """`[{sha, at, msg}]` — newest first (git log default). Sent as data; the UI composes the format."""
    args = ["log", _LOG_FMT]
    if limit:
        args.append(f"-{limit}")
    args.append(rng)
    out = []
    for line in run(args).splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        try:
            at = int(parts[1])
        except ValueError:
            continue
        out.append({"sha": parts[0], "at": at, "msg": parts[2]})
    return out


def _pushed_log(run, has_up, win="today"):
    """Already-pushed commits — cut by period. Without an upstream "pushed" is meaningless, so an empty list.
    Returns (list, total count, period name). At the cap, the total exceeds the list length."""
    if not has_up:
        return [], 0, ""
    since, lab = PUSHED_WINDOWS.get(win) or PUSHED_WINDOWS["today"]
    args = ["log", _LOG_FMT, since, "@{u}"]
    out = []
    for line in run(args).splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        try:
            at = int(parts[1])
        except ValueError:
            continue
        out.append({"sha": parts[0], "at": at, "msg": parts[2]})
    return out[:PUSHED_CAP], len(out), lab


# Shared with the rail (sidereus/git_rail.py imports these): untracked-file reads for the diff window and rail counts.
RAIL_READ_MAX = 1 << 20


def _repo_root(cwd):
    """Nearest ancestor holding `.git` (dir or worktree file) — status paths are root-relative. No git call."""
    d = os.path.realpath(cwd)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        up = os.path.dirname(d)
        if up == d:
            return cwd
        d = up


def _read_small(p):
    """Regular (non-symlink) file <= RAIL_READ_MAX -> bytes, else None.
    ⚠One fd, no check-then-open race: O_NOFOLLOW refuses a symlink, O_NONBLOCK keeps a FIFO from blocking."""
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    # ⚠Windows has neither flag: fall back to an islink check (racy, but still refuses a plain symlink).
    if not nofollow and os.path.islink(p):
        return None
    try:
        fd = os.open(p, os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0))
    except OSError:
        return None
    try:
        if not _st.S_ISREG(os.fstat(fd).st_mode):
            return None
        chunks, n = [], 0
        while n <= RAIL_READ_MAX:
            c = os.read(fd, RAIL_READ_MAX + 1 - n)
            if not c:
                break
            chunks.append(c)
            n += len(c)
        return None if n > RAIL_READ_MAX else b"".join(chunks)
    except OSError:
        return None
    finally:
        os.close(fd)


_SECRET_NAMES = {".netrc", ".npmrc", ".pypirc", "credentials", "credentials.json",
                 "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}
_SECRET_EXT = (".pem", ".key", ".p12", ".pfx")
_ENV_SHARED = {".env.example", ".env.sample", ".env.template"}   # committed templates, meant to be read


def _secret_name(path):
    """True when the basename is a credential file whose body must not leave the server."""
    n = os.path.basename(path).lower()
    if n in _ENV_SHARED:
        return False
    return n == ".env" or n.startswith(".env.") or n in _SECRET_NAMES or n.endswith(_SECRET_EXT)


def _untracked_patch(cwd, path):
    """One untracked-not-ignored file as an all-added patch (like `diff --no-index /dev/null f`), or "" if refused.
    ⚠Guard: realpath must stay inside the repo root (no ../ or symlink escape) and git must list it as
    `--others --exclude-standard` — ignored or tracked paths are refused."""
    root = os.path.realpath(_repo_root(cwd))
    full = os.path.realpath(os.path.join(root, path))
    if not path or os.path.isabs(path) or not full.startswith(root + os.sep) or os.path.islink(os.path.join(root, path)):
        return ""
    ls = _git_run(root, ["ls-files", "--others", "--exclude-standard", "-z", "--", ":(literal)" + path],
                  DIFF_TIMEOUT).stdout or ""
    if path not in ls.split("\0"):
        return ""
    head = f"diff --git a/{path} b/{path}\nnew file mode 100644\n"
    if _secret_name(path):
        # ⚠never read: untracked secrets are often not ignored yet; one-line hunk so it renders as a new file
        return head + f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,1 @@\n+(contents hidden: secret file)\n"
    b = _read_small(full)
    if b is None:
        return head
    if b"\0" in b[:8192]:
        return head + f"Binary files /dev/null and b/{path} differ\n"
    if not b:
        return head
    t = b.decode("utf-8", "replace")
    lines = t.split("\n")
    tail = ""
    if t.endswith("\n"):
        lines.pop()
    else:
        tail = "\\ No newline at end of file\n"
    return (head + f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n"
            + "".join("+" + x + "\n" for x in lines) + tail)


def _base_scope(cwd, scope):
    """`b:<sha>` scope (the rail's baseline) -> validated sha; "" when scope is not b:, None when refused.
    ⚠Only a hex sha that is an ancestor of HEAD — the window must not become "diff against any object"."""
    if not str(scope).startswith("b:"):
        return ""
    sha = str(scope)[2:]
    if not SHA_HEX_RE.match(sha):
        return None
    p = _git_run(cwd, ["merge-base", "--is-ancestor", sha, "HEAD"], DIFF_TIMEOUT)
    return sha if p.returncode == 0 else None


def git_diff(cwd, scope="all", pwin="today", view="", new="", sid="", base_mode="", untr=""):
    """Changes in the session's working tree. staged + unstaged at once, plus the unpushed commit list.
    view="rail": numstat file list + branch header + last commits only (`_git_rail`, no patch body);
    `base_mode` = one of RAIL_MODES ("" = auto); `sid` = the followed session, whose start time the start mode uses.
    scope="b:<sha>": working tree vs that baseline (the rail's file click; `_base_scope` guards it).
    untr="1": with scope work or b:, append up to DIFF_UNTR_MAX untracked files as all-added patches (diff window toggle).

    ★cwd is allowed **only for paths of currently live sessions**. Accepting arbitrary paths would make this endpoint
      "a window that reads any directory" (even on loopback, a browser can reach it).
    ★Output is capped, and truncation is stated — silent truncation reads as "these are all the changes"."""
    allowed = set()
    for r in sessions_rows():   # ⚠request path: snapshot allow-list, never a cold sessions()
        if r.get("cwd"):
            allowed.add(r["cwd"])
        allowed.update(r.get("repos") or [])
    if not _repo_ok(cwd, allowed):
        return {"ok": False, "msg": "Only repositories touched by a session on screen can be viewed."}
    if not os.path.isdir(os.path.join(cwd, ".git")) and not os.path.isdir(cwd):
        return {"ok": False, "msg": "Not a git repository."}

    def run(args):
        return _git_run(cwd, args, DIFF_TIMEOUT).stdout

    # ★Tracked files only (2026-08-25; no miscellaneous files). The untracked list filled with dozens of build/·target/·
    #   logs and hid the changes worth seeing. It shows even what .gitignore failed to filter.
    # ★Base is `@{u}` — the diff against upstream catches **unpushed commits + working tree** at once.
    #   If the agent already committed, `diff HEAD` shows nothing, hiding what needed review.
    #   Without an upstream, falls back to HEAD (working tree only).
    try:
        if view == "rail":
            from sidereus.git_rail import RAIL_MODES, RAIL_STATUS, _git_rail, _session_start  # ⚠lazy: git_rail imports git_view
            # ⚠A failed call is empty stdout — without this check a non-repo cwd painted as a clean repo.
            mode = base_mode or "auto"
            if mode not in RAIL_MODES:
                return {"ok": False, "msg": "Unknown base."}
            p = _git_run(cwd, RAIL_STATUS, DIFF_TIMEOUT)
            if p.returncode != 0:
                return {"ok": False, "msg": "Not a git repository."}
            since = _session_start(cwd, sid) if mode in ("start", "remote", "upstream") else 0
            return _git_rail(cwd, run, p.stdout, since, mode)
        has_up = bool(run(["rev-parse", "--abbrev-ref", "@{u}"]).strip())
        # ★Single-commit view (2026-08-26) — the unpushed commit list was already provided, so clicking one
        #   shows only that commit's changes. `c:<sha>` rides on the scope value and **reuses the existing pipeline**
        #   (tree, filter and side-by-side all follow — no reason for a new view).
        if scope.startswith("c:"):
            sha = scope[2:]
            if not _SHA_RE.match(sha):
                return {"ok": False, "msg": "Not a commit hash."}
            if run(["cat-file", "-t", sha]).strip() != "commit":
                return {"ok": False, "msg": "Commit not in this repository ({sha}).", "vars": {"sha": sha[:10]}}
            _ps = _pushed_log(run, has_up, pwin)
            subj = run(["log", "-1", "--format=%h %s", sha]).strip()
            # -M everywhere so patch, stat, numstat and the Branches commit detail agree on renames.
            body, total = _git_run_capped(cwd, ["show", "-M", sha, "--patch", "--format="], DIFF_TIMEOUT, DIFF_MAX)
            stat = run(["show", "-M", sha, "--stat", "--format="]).strip()
            nst = _numstat(run(["show", "-M", sha, "--numstat", "-z", "--format="]))
            unpushed = _commits(run, "@{u}..HEAD") if has_up else []
            cut = total > DIFF_MAX
            # scopeCommit: "<short sha> <subject>"; the «Commit» label is built client-side so it follows the UI language.
            return {"ok": True, "cwd": cwd, "scope": "", "scopeCommit": subj or sha[:7], "scopeKey": scope,
                    "hasUp": has_up, "stat": stat, "diff": body[:DIFF_MAX],
                    "numstat": nst[:STAT_FILES_MAX], "numstatN": len(nst),
                    "cutBytes": total if cut else 0, "unpushed": unpushed[:30],
                    "pushed": _ps[0], "pushedAll": _ps[1], "pushedWin": _ps[2],
                    "pickedSha": sha}
        base = _base_scope(cwd, scope)
        if base is None:
            return {"ok": False, "msg": "Only ancestor commits of this branch can be used as the base."}
        if base:
            # scopeBase lets the client build «since base …» in the UI language; scope stays for older readers.
            args, label = [base], "Since " + base[:7]
        else:
            if scope not in DIFF_SCOPES:
                scope = "all"
            if not has_up and scope in ("all", "commit"):
                scope = "work"            # without an upstream, "unpushed" is meaningless
            args = {"all": ["@{u}"], "commit": ["@{u}", "HEAD"], "work": ["HEAD"]}[scope]
            label = DIFF_SCOPES[scope] if has_up or scope == "work" else DIFF_SCOPES["work"]
        stat = run(["diff", "-M"] + args + ["--stat"]).strip()
        nst = _numstat(run(["diff", "-M"] + args + ["--numstat", "-z"]))
        body, total = _git_run_capped(cwd, ["diff", "-M"] + args, DIFF_TIMEOUT, DIFF_MAX)
        # One untracked file the rail asked for (`new`), appended as an all-added patch. ⚠Only that file —
        # the blanket untracked list stays out of this view (2026-08-25 decision above).
        if (new or untr) and (scope == "work" or base):
            paths = [new] if new else []
            if untr:
                from sidereus.git_rail import RAIL_STATUS, _status_untracked  # ⚠lazy: git_rail imports git_view
                st = _git_run(cwd, RAIL_STATUS, DIFF_TIMEOUT)
                paths += [p for p in _status_untracked(st.stdout if st.returncode == 0 else "") if p != new][:DIFF_UNTR_MAX]
            for p in paths:
                if total > DIFF_MAX:
                    break   # body is already capped; reading more untracked files only costs memory and git calls
                extra = _untracked_patch(cwd, p)   # ⚠keeps its own literal/realpath/size guards per path
                body += extra
                total += len(extra)
        unpushed = _commits(run, "@{u}..HEAD") if has_up else []
        pushed, pushed_all, pushed_win = _pushed_log(run, has_up, pwin)
    except subprocess.TimeoutExpired:
        return {"ok": False, "msg": "git did not answer within {n} s.", "vars": {"n": DIFF_TIMEOUT}}
    except Exception as e:
        return {"ok": False, "msg": "git failed ({err})", "vars": {"err": type(e).__name__}}

    cut = total > DIFF_MAX
    return {"ok": True, "cwd": cwd, "scope": label, "scopeBase": base[:7] if base else "",
            "scopeKey": scope, "hasUp": has_up, "stat": stat,
            "diff": body[:DIFF_MAX], "cutBytes": total if cut else 0,
            "numstat": nst[:STAT_FILES_MAX], "numstatN": len(nst),
            "unpushed": unpushed[:30], "pushed": pushed,
            "pushedAll": pushed_all, "pushedWin": pushed_win}


def _branch_ok(cwd):
    """May this repo be opened? Session cwds + repos those sessions touched + Sidereus itself.
    ⚠Every row, like `git_diff` and the picker (`brRepos`) — `_allowed_cwds()` keeps one row per cwd and drops
      repos an earlier session in that cwd touched (picker listed the repo, server said «not allowed»)."""
    if not cwd or not isinstance(cwd, str):   # ⚠realpath("") = process cwd = CODE_DIR -> would pass
        return False
    allowed = {CODE_DIR} if config.IS_CLONE else set()   # installed package: not a repo
    try:
        for r in sessions_rows():   # ⚠request path: snapshot allow-list, never a cold sessions()
            if r.get("cwd"):
                allowed.add(r["cwd"])
            allowed.update(r.get("repos") or [])
    except Exception as e:
        warn_once("git-allow", "git allow-list failed ({err}) — only the Sidereus repo is allowed",
                  vars={"err": f"{type(e).__name__}: {e}"}, soft=True)
    for p in list(allowed):
        try:
            allowed.add(os.path.realpath(p))
        except (OSError, ValueError, TypeError):
            pass                  # odd entry (NUL byte, non-str): the raw path stays in the set
    if _repo_ok(cwd, allowed):
        return True
    try:
        return _repo_ok(os.path.realpath(cwd), allowed)
    except (OSError, ValueError, TypeError):
        return False              # unresolvable/odd cwd from the request: not allowed


COMMIT_FILES_MAX = 400
COMMIT_BODY_MAX = 20_000


def git_commit(cwd, sha, path=""):
    """One commit for the Branches tab: meta + numstat file list, or one file's patch when `path` is given.
    ⚠Same allow list as /api/branches (`_branch_ok`). sha must be hex; `path` is only passed to git when it is
      one of the names git itself listed for this commit — never raw user input."""
    if not cwd or not os.path.isdir(cwd):
        return 400, {"ok": False, "err": "repo required"}
    if not _branch_ok(cwd):
        return 403, {"ok": False, "err": "not allowed"}
    sha = str(sha or "")
    if not SHA_HEX_RE.match(sha):
        return 400, {"ok": False, "err": "sha must be 4-40 hex chars"}

    def run(args):
        return _git_run(cwd, args, DIFF_TIMEOUT)

    try:
        r = run(["rev-parse", "--verify", "--quiet", sha.lower() + "^{commit}"])
        full = r.stdout.strip()
        if r.returncode != 0 or not re.match(r"^[0-9a-f]{40,64}$", full):
            return 404, {"ok": False, "err": "no such commit"}
        m = run(["show", "--no-patch", "--format=%H%x1f%P%x1f%an%x1f%ae%x1f%at%x1f%B", full])
        f = m.stdout.split("\x1f", 5)
        if m.returncode != 0 or len(f) < 6:
            return 500, {"ok": False, "err": "git show failed"}
        parents = f[1].split()
        # Merges: diff against the first parent (plain `show --numstat` prints nothing for a merge).
        base = (["diff", parents[0], full] if len(parents) > 1 else ["show", "--format=", full])
        # -M like the diff window, so a rename is one row there and here.
        files = _numstat(run(base + ["--numstat", "-z", "-M"]).stdout)
        if path:
            hit = next((x for x in files if x["path"] == path), None)
            if hit is None:
                return 400, {"ok": False, "err": "file not in this commit"}
            # ⚠A rename needs both sides in the pathspec, or git sees only an added file.
            spec = [":(literal)" + p for p in (hit["from"], path) if p]
            body, total = _git_run_capped(cwd, base + ["--patch", "-M", "--"] + spec,
                                          DIFF_TIMEOUT, FULL_MAX)  # ⚠names like `a*` stay literal
            cut = total > FULL_MAX
            return 200, {"ok": True, "sha": full, "path": path, "diff": body[:FULL_MAX],
                         "cutBytes": total if cut else 0}
    except subprocess.TimeoutExpired:
        return 504, {"ok": False, "err": "timeout"}
    except Exception as e:
        return 500, {"ok": False, "err": "git " + type(e).__name__}
    msg = f[5].rstrip("\n")
    return 200, {"ok": True, "sha": full, "parents": parents, "author": f[2], "email": f[3],
                 "at": int(f[4]) if f[4].isdigit() else 0, "msg": msg[:COMMIT_BODY_MAX],
                 "files": files[:COMMIT_FILES_MAX], "nfiles": len(files)}
