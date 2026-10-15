"""Git basics shared below the session layer: repo root, branch state, session repos, worktrees."""
import contextlib
import json
import os
import re
import subprocess
import threading
import time
from sidereus.warn import warn_once
from sidereus.ident import _git_walk


_git_cache = {}                 # cwd -> (lookup time, marker, TTL for this entry)
# ★The unpushed count is already in the `status --branch` header — `## main...origin/main [ahead 3, behind 1]`.
#   No need for a separate `rev-list --count @{u}..HEAD` (measured 2026-09-21: across 16 repo states
#   — ahead · ahead+behind · no upstream · detached · worktree (.git is a file) · bare · non-repo — both methods'
#   output matched everywhere). Forks per session go 2 → 1.
_AHEAD_RE = re.compile(r"\[(?:[^\]]*?\bahead (\d+))")
# ★A cwd that is not a git repo is **not re-asked every time** (⚠`.mailbox-mcp` itself is one).
#   It was forking every 20 s only to get 128 and discard it. Not permanent, since `git init` may come later.
GIT_NOREPO_TTL = 300
SHA_HEX_RE = re.compile(r"^[0-9a-fA-F]{4,40}$")   # user-supplied commit id (4-40 hex, either case)


# ★One cap on concurrent git processes for every viewer path (tabs, rapid clicks, warm-ups).
# ⚠A wait past GIT_WAIT_S raises TimeoutExpired, so callers' existing "timeout" handling applies unchanged.
GIT_MAX_PROCS = 3
GIT_WAIT_S = 10
_GIT_SEM = threading.BoundedSemaphore(GIT_MAX_PROCS)
_SLOT_CMD = "git (slot wait)"   # TimeoutExpired.cmd of a slot miss (vs. a git process timeout)


@contextlib.contextmanager
def _git_slot(wait=None):
    """Hold one git slot; raises subprocess.TimeoutExpired if none frees within `wait` (default GIT_WAIT_S)."""
    wait = GIT_WAIT_S if wait is None else wait
    sem = _GIT_SEM
    if not sem.acquire(timeout=wait):
        raise subprocess.TimeoutExpired(_SLOT_CMD, wait)
    try:
        yield
    finally:
        sem.release()


def git_slot_free(wait=0.0):
    """True if a slot can be taken within `wait` (probe only; released at once). Background warm-ups skip when False."""
    sem = _GIT_SEM
    if not sem.acquire(timeout=wait):
        return False
    sem.release()
    return True


def git_env():
    """Environment for every git process the viewer spawns.
    ★GIT_OPTIONAL_LOCKS=0: `git status` otherwise refreshes `.git/index` and takes `index.lock` in the watched repo —
    measured 2026-09-25: after a stat-dirty touch, plain status changed the index mtime; with the flag it did not.
    ⚠A poll landing during an agent's `git add`/`commit` made it fail with "index.lock: File exists". Viewer is read-only."""
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    return env


# ★Security audit 2026-09-25: the viewer runs git in repos sessions merely touched (e.g. a downloaded repo), so
#   repo-local config must not run code.
# core.quotePath=false: non-ASCII paths come out raw (not "\355..." octal) so diff headers match numstat -z paths.
GIT_SAFE_OPTS = ["-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "core.quotePath=false"]
# Worktree .gitattributes is read from the empty tree, so `filter=<x>` (clean/process) never runs; trade-off: LFS/eol
# attributes are ignored for display. ⚠Needs git >= 2.40; .git/info/attributes is still honoured (not covered).
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def _attr_opts(version_text):
    """["--attr-source=<empty tree>"] when `git --version` output is >= 2.40, else [] (older git rejects the flag)."""
    m = re.search(r"(\d+)\.(\d+)", version_text or "")
    return ["--attr-source=" + EMPTY_TREE] if m and (int(m.group(1)), int(m.group(2))) >= (2, 40) else []


def _git_version():
    """`git --version` text, "" when git is missing or fails. Probed once at import (before tests fake subprocess)."""
    try:
        return subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


GIT_SAFE_OPTS += _attr_opts(_git_version())
_DIFF_CMDS = ("diff", "show", "log")
_DIFF_SAFE = ["--no-ext-diff", "--no-textconv"]     # diff.external / diff.<drv>.command / textconv


def git_argv(cwd, args):
    """Full argv for `git -C cwd <args>` with the safe options (every viewer git spawn goes through this)."""
    args = list(args)
    if args and args[0] in _DIFF_CMDS:
        args[1:1] = _DIFF_SAFE
    return ["git"] + GIT_SAFE_OPTS + ["-C", cwd] + args


def _git_run(cwd, args, timeout, wait=None):
    """`git -C cwd <args>` as UTF-8 text (errors replaced). Returns the CompletedProcess; ⚠raises TimeoutExpired/OSError."""
    with _git_slot(wait):
        return subprocess.run(git_argv(cwd, args), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, env=git_env())


GIT_COUNT_MAX = 16_000_000      # past the cap, output is only counted (for cutBytes) up to this, then git is killed


def _git_run_capped(cwd, args, timeout, cap, wait=None):
    """stdout of `git <args>` keeping at most cap+1 chars in memory; returns (text, total_chars).
    Same text as _git_run(...).stdout when total <= cap. ⚠Past GIT_COUNT_MAX, total is a lower bound.
    Raises TimeoutExpired like _git_run."""
    with _git_slot(wait):
        p = subprocess.Popen(git_argv(cwd, args), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                             encoding="utf-8", errors="replace", env=git_env())
        fired = []
        t = threading.Timer(timeout, lambda: (fired.append(1), p.kill()))
        t.start()
        parts, kept, total = [], 0, 0
        try:
            while True:
                chunk = p.stdout.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if kept <= cap:
                    parts.append(chunk)
                    kept += len(chunk)
                if total > GIT_COUNT_MAX:
                    p.kill()
                    break
        finally:
            t.cancel()
            p.stdout.close()
            p.wait()
        if fired:
            raise subprocess.TimeoutExpired(p.args, timeout)
        text = "".join(parts)
        return (text if total <= cap else text[:cap + 1]), total


def _git_state(cwd, ttl=20):
    """Unpushed/dirty — the slot of Orca's git integration. **Cache and timeout are mandatory** (per-session calls slow the page)."""
    if not cwd or not os.path.isdir(cwd):
        return ""
    hit = _git_cache.get(cwd)
    if hit and time.time() - hit[0] < (hit[2] if len(hit) > 2 else ttl):
        return hit[1]
    val, keep = "", ttl
    try:
        # ⚠Poll path never waits for a slot: 1.5 s x N uncached cwds serialised state(). Slot miss -> previous value, uncached.
        r = _git_run(cwd, ["status", "--porcelain", "-uno", "--branch"], 1.5, wait=0)
        if r.returncode != 0:
            keep = GIT_NOREPO_TTL                 # not a repo — decide once and remember long
        else:
            lines = r.stdout.strip().splitlines()
            ahead = "0"
            if lines and lines[0].startswith("##"):
                m = _AHEAD_RE.search(lines[0])    # no upstream or detached ⇒ no match → 0
                ahead = m.group(1) if m else "0"
                lines = lines[1:]
            dirty = len([x for x in lines if x])
            bits = []
            if ahead.isdigit() and int(ahead) > 0:
                bits.append(f"↑{ahead}")
            if dirty:
                bits.append(f"~{dirty}")
            val = " ".join(bits)
    except subprocess.TimeoutExpired as e:
        prev = hit[1] if hit else ""
        if e.cmd == _SLOT_CMD:
            return prev                           # no slot now — retry next poll, keep the last answer
        val, keep = prev, ttl                     # slow repo — keep the last answer, don't re-fork every poll
    except Exception:
        val, keep = "", ttl                       # not git or slow — just leave empty (no guessing)
    _git_cache[cwd] = (time.time(), val, keep)
    return val


# ★Subagent changes are hard for a human to review (2026-08-25) — when a session launches several agents,
#   retracing what changed in the terminal is tedious. So they open straight from the session row.
# ★One session may touch several repos (2026-08-25) — looking at cwd alone hides the other changes.
#   So **paths actually touched in the transcript** are collected and folded into git roots.
#   No config list: where a session touched is already in its trace, and hand-written lists
#   go stale. The security condition holds too — **paths never touched cannot be opened.**
_REPO_CACHE = {}          # transcript path -> (mtime, [git roots]), LRU order (oldest first)
_REPO_CACHE_MAX = 128
# Home parent comes from expanduser (`/Users` on macOS, `/home` on Linux); on macOS the pattern is byte-identical to the old literal.
_PATH_RE = re.compile(re.escape(os.path.dirname(os.path.expanduser("~")) or "/Users") + r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.\-/]+")
# ⚠Sessions also write `~/repo/...` and `cd repo` (relative to cwd); absolute-only matching returned [] for them.
_HOME = os.path.expanduser("~")
_TILDE_RE = re.compile(r"(?<![\w/~.-])~/[A-Za-z0-9_.\-/]+")
_CD_RE = re.compile(r"(?:^|[\s;&|(])cd\s+[\"']?([A-Za-z0-9_.~][A-Za-z0-9_.\-/]*)")


def _extra_paths(blob, cmd, cwd):
    """`~/...` paths in any field and `cd <dir>` targets in the command, kept only inside the user's home."""
    out = [_HOME + m.group(0)[1:] for m in _TILDE_RE.finditer(blob)]
    for m in _CD_RE.finditer(cmd):
        t = m.group(1)
        if t.startswith("~"):
            continue                         # `cd ~/x` is already caught by _TILDE_RE; bare `cd ~` is just home
        d = os.path.normpath(t if t.startswith("/") else os.path.join(cwd or "", t))
        if os.path.isabs(d) and os.path.isdir(d):
            out.append(d)
    home = _HOME.rstrip(os.sep) + os.sep
    return [d for d in out if os.path.normpath(d).startswith(home)]

# ⚠`_git_root` used to live here (inferior version: `.git` directory only · 8-level climb cap · `_ROOT_CACHE`).
#   The version around :1600 redefined the same name later and **the later one won** — this one was never called.
#   Deleted 2026-09-21. The live version also accepts worktrees (`.git` is a file) and has no climb limit.


def _tool_inputs(fp, offset):
    """(items, offset reached, restarted): (path blob, command) of each tool_use in the complete lines after
    byte `offset`; a file shorter than `offset` was rewritten, so it is read from 0 and `restarted` is True."""
    out = []
    with open(fp, "rb") as f:
        restarted = os.fstat(f.fileno()).st_size < offset
        if restarted:
            offset = 0
        f.seek(offset)
        for raw in f:
            if not raw.endswith(b"\n"):
                break                        # partial last line: re-read it next scan
            offset += len(raw)
            if b'"tool_use"' not in raw:
                continue                     # cheap filter: a large transcript is mostly text/results
            try:
                c = (json.loads(raw).get("message") or {}).get("content")
            except Exception:
                continue
            if not isinstance(c, list):
                continue
            for blk in c:
                if not isinstance(blk, dict) or blk.get("type") != "tool_use":
                    continue
                inp = blk.get("input") if isinstance(blk.get("input"), dict) else {}
                blob = " ".join(str(inp.get(k) or "") for k in ("file_path", "path", "notebook_path", "command"))
                out.append((blob, str(inp.get("command") or "")))
    return out, offset, restarted


def session_repos(fp, mt, cwd):
    """Git repos this session touched. The cwd's repo goes first, then the most recently seen."""
    # ⚠Keyed by fp alone: an (fp, mtime) key grew on every write by an active session, and the bulk evict
    #   threw out stable sessions too, forcing 1.5MB tail re-reads (~11ms each, 322ms spikes with 5 active).
    hit = _REPO_CACHE.pop(fp, None)
    if hit is not None and hit[0] == mt:
        _REPO_CACHE[fp] = hit                # reinsert = most recently used
        return hit[1]
    # ⚠Incremental, not a tail window: a 1.5MB tail dropped repos edited earlier in a 27MB transcript.
    #   First scan reads the whole file; later scans only the appended bytes (from 0 if the file shrank).
    offset, recent = (hit[2], list(hit[3])) if hit is not None else (0, [])
    try:
        items, offset, restarted = _tool_inputs(fp, offset)
        if restarted:
            recent = []
        for blob, cmd in items:
            for d in [m.group(0) for m in _PATH_RE.finditer(blob)] + _extra_paths(blob, cmd, cwd):
                r = _git_root(d if os.path.isdir(d) else os.path.dirname(d))
                if r:
                    if r in recent:
                        recent.remove(r)
                    recent.insert(0, r)      # most recently seen first
        del recent[32:]                      # bound the remembered list; only 8 are shown
    except OSError:
        pass                                 # path vanished mid-scan: keep the roots found so far
    except Exception as e:
        warn_once("sessrepos", "Could not list the session's repos ({err})", vars={"err": type(e).__name__}, soft=True)
    roots = list(recent)
    # ★Put the cwd's repo first. The UI opens the first tab by default.
    own = _git_root(cwd) if cwd else ""
    if own:
        if own in roots:
            roots.remove(own)
        roots.insert(0, own)
    roots = roots[:8]                        # cap — a longer list is harder to choose from
    while len(_REPO_CACHE) >= _REPO_CACHE_MAX:
        _REPO_CACHE.pop(next(iter(_REPO_CACHE)), None)   # least recently used
    _REPO_CACHE[fp] = (mt, roots, offset, recent)
    return roots


DIFF_MAX = 220_000          # body cap — sending a huge diff whole freezes the page
DIFF_TIMEOUT = 6            # some repos have slow git (a big working tree next to an 855MB transcript)


_GITROOT = {}
GITROOT_MAX = 512


def _git_root(d):
    """Git root containing the directory. ★Working in **a subdirectory** like `cd .../frontend` is common
    (measured 2026-08-31: every TS file was such a case); passing that as the repo gets the diff request rejected
    and nothing shows. So climb to the root here, and rewrite paths relative to the root."""
    if not d:
        return ""
    if d in _GITROOT:
        return _GITROOT[d]
    hit = _git_walk(d)                      # walk lives in ident (loads earlier, _proj_name needs it); cache stays here
    if len(_GITROOT) >= GITROOT_MAX:        # API routes add arbitrary dirs — drop the oldest half
        for k in list(_GITROOT)[:GITROOT_MAX // 2]:
            _GITROOT.pop(k, None)
    _GITROOT[d] = hit
    return hit


def _wt_main(repo):
    """If the path is **a git worktree**, the main repo path; else an empty string.

    ★Why (measured 2026-09-03, from a screenshot): when an agent works in
      `repo-B/.claude/worktrees/dialog-siblings`, the file's repo is that worktree.
      But the allow list is built from paths in **session transcripts**, and the worktree path appears only in
      **agent transcripts** — so inline diffs were rejected wholesale with
      `Only repos touched by on-screen sessions can be viewed`.
    ★A worktree is part of the main repo. If the main repo is allowed, allowing its worktree is right
      (not widening scope, just recognizing another checkout of the same repo).
      Decided not by guess but by the `gitdir` path the `.git` file points to."""
    try:
        p = os.path.join(repo, ".git")
        if not os.path.isfile(p):
            return ""
        with open(p, encoding="utf-8") as f:
            s = f.read(500).strip()
        if not s.startswith("gitdir:"):
            return ""
        g = s.split(":", 1)[1].strip()
        # ⚠The .git file is untrusted text: realpath it and require <main>/.git/worktrees/<name>, else not a worktree.
        g = os.path.realpath(os.path.join(repo, g))
        i = g.find("/.git/worktrees/")
        if i <= 0:
            return ""
        main = g[:i]
        wt = os.path.join(main, ".git", "worktrees") + os.sep
        return main if g.startswith(wt) and os.path.isdir(g) and len(g) > len(wt) else ""
    except (OSError, ValueError):
        return ""                 # unreadable or odd .git file (NUL, bad UTF-8): not a worktree


WT_MAX = 40


def _worktrees(run):
    """`git worktree list --porcelain` -> [{path, head, branch, main, detached}]. First entry is the main checkout.
    ⚠Paths are realpath'd — session roots (`_wt_of`) are realpath'd too, so /tmp vs /private/tmp still match."""
    try:
        r = run(["worktree", "list", "--porcelain"])
        if r.returncode != 0:
            return []
    except (OSError, subprocess.SubprocessError):
        return []                 # git missing/timeout/slot busy: graph shows without worktrees
    out, cur = [], None
    for line in r.stdout.splitlines() + [""]:
        if line.startswith("worktree "):
            cur = {"path": os.path.realpath(line[9:].strip()), "head": "", "branch": "",
                   "main": not out, "detached": False}
        elif cur is None:
            continue
        elif line.startswith("HEAD "):
            cur["head"] = line[5:].strip()[:7]
        elif line.startswith("branch "):
            b = line[7:].strip()
            cur["branch"] = b[11:] if b.startswith("refs/heads/") else b
        elif line == "detached":
            cur["detached"] = True
        elif line == "bare":
            cur["bare"] = True
        elif line == "prunable" or line.startswith("prunable "):
            cur["prunable"] = True        # dead dir (e.g. cleaned /tmp scratchpad) - not a work unit; read-only, no prune
        elif not line.strip():
            if not cur.get("bare") and not cur.get("prunable"):
                out.append(cur)
            cur = None
            if len(out) >= WT_MAX:
                break
    return out


_WTOF = {}        # cwd -> (at, value)


def _wt_of(cwd):
    """Session cwd -> {root, main, name}: its git root (realpath) and, if that root is a linked worktree, the main repo.
    main == "" means the main checkout. None outside git. 60 s cache (one small file read per miss)."""
    if not cwd:
        return None
    hit = _WTOF.get(cwd)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    val = None
    try:
        root = _git_root(cwd)
        if root:
            m = _wt_main(root)
            rr = os.path.realpath(root)
            val = {"root": rr, "main": os.path.realpath(m) if m else "", "name": os.path.basename(rr)}
    except Exception:
        val = None
    if len(_WTOF) > 256:
        _WTOF.clear()
    _WTOF[cwd] = (time.time(), val)
    return val
