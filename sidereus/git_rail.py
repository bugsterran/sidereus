"""Timeline changes rail (`git_diff(view="rail")`): file list vs a baseline (head/start/remote), numstat, untracked
counts, branch header, commits since the base, per-file owner chips. Split from sidereus/git_view.py (2026-09-25);
git_view.git_diff dispatches here. ⚠Imports git_view, so git_view reaches it lazily (import cycle)."""
import calendar
import os
import re
import stat as _st
import time
import glob
from sidereus.agents import _agent_meta
from sidereus.claude_roots import projects_dirs
from sidereus.memo import MISS, BoundedMemo
from sidereus.gitinfo import SHA_HEX_RE
from sidereus.git_view import RAIL_READ_MAX, _commits, _git_common_dir, _read_small, _repo_root
from sidereus.ident import _cwd_from_slug, _sid8, _slug
from sidereus.sessions import sessions_snapshot
from sidereus.work import _sid_path


RAIL_FILES_MAX = 300
RAIL_COMMITS = 5
_RAIL_ST = {"A": "A", "M": "M", "D": "D", "R": "R", "C": "A", "T": "M", "U": "U"}


def _raw_numstat(out):
    """`diff --raw --numstat -z -M` -> [{path, st, add, del, bin, old?}] in raw order. st: A/M/D/R/U."""
    tok = (out or "").split("\0")
    recs, ns, i = [], {}, 0
    while i < len(tok):
        t = tok[i]
        if t.startswith(":"):
            code = (t.split() or ["M"])[-1][:1]
            if code in "RC" and i + 2 < len(tok):
                rec = {"path": tok[i + 2], "old": tok[i + 1], "st": _RAIL_ST.get(code, "M")}
                i += 3
            else:
                rec = {"path": tok[i + 1] if i + 1 < len(tok) else "", "st": _RAIL_ST.get(code, "M")}
                i += 2
            if code == "C":
                rec.pop("old", None)
            if rec["path"]:
                recs.append(rec)
        elif t.count("\t") >= 2:
            a, d, p = t.split("\t", 2)
            if not p and i + 2 < len(tok):
                p, i = tok[i + 2], i + 3        # rename: empty path, then old, new
            else:
                i += 1
            ns[p] = (a, d)
        else:
            i += 1
    for r in recs:
        a, d = ns.get(r["path"], ("0", "0"))
        r["bin"] = a == "-"
        r["add"] = int(a) if a.isdigit() else 0
        r["del"] = int(d) if d.isdigit() else 0
    return recs


def _status_branch(out):
    """`status --porcelain=v2 --branch` header -> {branch, upstream, ahead, behind}."""
    b = {"branch": "", "upstream": "", "ahead": 0, "behind": 0}
    for line in (out or "").splitlines():
        if not line.startswith("# "):
            continue
        k, _, v = line[2:].partition(" ")
        if k == "branch.head":
            b["branch"] = "" if v == "(detached)" else v
        elif k == "branch.upstream":
            b["upstream"] = v
        elif k == "branch.ab":
            for x in v.split():
                if x[1:].isdigit():
                    b["ahead" if x[0] == "+" else "behind"] = int(x[1:])
    return b


RAIL_UNTRACKED_MAX = 200


def _status_untracked(out):
    """`status --porcelain=v2 -z` -> untracked paths ("? p"). Skips the extra orig-path token of "2" (rename) records."""
    paths, skip = [], False
    for t in (out or "").split("\0"):
        if skip:
            skip = False
        elif t.startswith("2 "):
            skip = True
        elif t.startswith("? "):
            paths.append(t[2:])
    return paths


RAIL_LC_MAX = 2000
_rail_lc = BoundedMemo(RAIL_LC_MAX)    # (root, path) -> ((size, mtime_ns), (add, bin)); stamp = (size, mtime_ns)


def _untracked_rec(root, path):
    """Untracked file -> rail record (st A). add = line count for regular text files <= 1 MB; NUL byte = binary.
    Counts are cached by (size, mtime_ns) — the rail polls every 10 s and must not re-read 200 files each time."""
    rec = {"path": path, "st": "A", "add": 0, "del": 0, "bin": False, "new": True}
    full = os.path.join(root, path)
    try:
        s = os.lstat(full)
    except OSError:
        return rec
    if not _st.S_ISREG(s.st_mode) or s.st_size > RAIL_READ_MAX:
        return rec
    key, sig = (root, path), (s.st_size, s.st_mtime_ns)
    hit = _rail_lc.get(key, stamp=sig)
    if hit is not None:
        rec["add"], rec["bin"] = hit
        return rec
    b = _read_small(full)
    if b is None:
        return rec
    if b"\0" in b[:8192]:
        rec["bin"] = True
    else:
        rec["add"] = b.count(b"\n") + (1 if b and not b.endswith(b"\n") else 0)
    _rail_lc.put(key, (rec["add"], rec["bin"]), stamp=sig)
    return rec


RAIL_STATUS = ["status", "--porcelain=v2", "--branch", "-z", "--untracked-files=all"]
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


RAIL_BASE_COMMITS_MAX = 200     # commits listed/counted between the base and HEAD; beyond this the count says "+"
_TS_RE = re.compile(r'"timestamp"\s*:\s*"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.\d+)?Z"')
_start_cache = BoundedMemo(256)   # transcript path -> start epoch (the head of a transcript never changes)


def _ref_exists(common, ref):
    """Loose ref file or a packed-refs line — no git call (the rail keeps its git budget for diff/log)."""
    if os.path.isfile(os.path.join(common, ref)):
        return True
    try:
        with open(os.path.join(common, "packed-refs"), encoding="utf-8", errors="replace") as f:
            return any(ln.rstrip("\n").endswith(" " + ref) for ln in f)
    except OSError:
        return False


def _default_branch(cwd):
    """Default branch as a rev git accepts: origin/HEAD's target (local name if that branch exists), else main,
    else master, else "". Read from ref files only."""
    common = _git_common_dir(cwd)
    if not common:
        return ""
    try:
        with open(os.path.join(common, "refs", "remotes", "origin", "HEAD"), encoding="utf-8") as f:
            s = f.read(300).strip()
    except OSError:
        s = ""
    if s.startswith("ref: refs/remotes/origin/"):
        name = s[len("ref: refs/remotes/origin/"):]
        if name and re.match(r"^[A-Za-z0-9._/-]+$", name) and ".." not in name:
            return name if _ref_exists(common, "refs/heads/" + name) else "origin/" + name
    for name in ("main", "master"):
        if _ref_exists(common, "refs/heads/" + name):
            return name
    return ""


def _session_start(cwd, sid):
    """First transcript timestamp of a Claude session -> unix seconds, 0 if unknown (bad sid, no file, no stamp)."""
    fp = _sid_path(cwd, sid) if sid else ""
    if not fp:
        return 0
    hit = _start_cache.get(fp, MISS)   # ⚠0 (no stamp) is a cached value too
    if hit is not MISS:
        return hit
    at = 0
    try:
        with open(fp, "rb") as f:
            m = _TS_RE.search(f.read(65536).decode("utf-8", "replace"))
        if m:
            at = calendar.timegm(time.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S"))
    except (OSError, ValueError):
        at = 0
    return _start_cache.put(fp, at)


RAIL_MODES = ("auto", "head", "start", "remote", "upstream")   # ⚠whitelist for the `base` query param; anything else is refused


def _has_remote(cwd, upstream):
    """Auto-mode test: the branch has an upstream (from status) or origin/<default> exists (ref files, no git call)."""
    if upstream:
        return True
    dflt = _default_branch(cwd)
    common = _git_common_dir(cwd) if dflt else ""
    return bool(common) and _ref_exists(common, "refs/remotes/origin/" + dflt.split("origin/", 1)[-1])
_REF_NAME_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def _rail_base(cwd, run, branch, since, mode="head", upstream=""):
    """Baseline for the rail -> (rev, kind, ref, no_remote).
    ★Default = HEAD — uncommitted only, no git call.
    mode "start": HEAD as of the session start. mode "remote": feature branch -> merge-base with the default branch
    (kind "branch"); else merge-base with the upstream or origin/<default> (kind "remote"); no remote -> session start.
    ⚠Every sha from git is re-validated with SHA_HEX_RE before it is used as an argument."""
    def start(no_remote=False):
        if since > 0:
            sha = run(["rev-list", "-1", "--before=%d" % int(since), "HEAD", "--"]).strip()
            if SHA_HEX_RE.match(sha):
                return sha, "start", branch, no_remote
        return "HEAD", "head", "", no_remote

    def mbase(ref, kind):
        sha = run(["merge-base", "HEAD", ref, "--"]).strip()
        return (sha, kind, ref, False) if SHA_HEX_RE.match(sha) else None

    if mode == "start":
        return start()
    if mode == "upstream":   # this branch's own remote only (unpushed work), never the default branch
        up = upstream if upstream and _REF_NAME_RE.match(upstream) and ".." not in upstream else ""
        hit = mbase(up, "remote") if up else None
        return hit or start(no_remote=True)
    if mode != "remote":
        return "HEAD", "head", "", False
    dflt = _default_branch(cwd)
    on_dflt = bool(dflt) and bool(branch) and branch == dflt.split("origin/", 1)[-1]
    if dflt and not on_dflt:
        hit = mbase(dflt, "branch")
        if hit:
            return hit
    remote = upstream if upstream and _REF_NAME_RE.match(upstream) and ".." not in upstream else ""
    if not remote and dflt:
        name = dflt.split("origin/", 1)[-1]
        common = _git_common_dir(cwd)
        if common and _ref_exists(common, "refs/remotes/origin/" + name):
            remote = "origin/" + name
    hit = mbase(remote, "remote") if remote else None
    return hit or start(no_remote=True)


def _status_tracked(st):
    """Repo-relative paths of tracked uncommitted entries in `status --porcelain=v2 -z` (1/2/u records; a rename gives both
    paths). ★Matches file_owner._dirty (wt_files minus "??" rows), so the rail's «Conflict» follows the canonical rule."""
    out, it = set(), iter((st or "").split("\0"))
    for t in it:
        n = {"1 ": 8, "2 ": 9, "u ": 10}.get(t[:2])
        if n is None:
            continue
        parts = t.split(" ", n)
        if len(parts) > n:
            out.add(parts[n])
        if t.startswith("2 "):
            out.add(next(it, ""))
    out.discard("")
    return out


def _status_dirty(st):
    """Uncommitted entry count from `status --porcelain=v2 -z` (changed, renamed, unmerged, untracked)."""
    n, skip = 0, False
    for t in (st or "").split("\0"):
        if skip:
            skip = False
        elif t[:2] in ("1 ", "u ", "? "):
            n += 1
        elif t.startswith("2 "):
            n, skip = n + 1, True
    return n


RAIL_OWN_MAX = 8        # owner units kept per file row (latest first)
RAIL_OWN_LAB = 60       # agent description cap (the chip truncates further with CSS)


RAIL_HOME_TTL = 60      # s; sid -> project dir memo (the rail polls; a session's transcript dir does not move)
_rail_home_c = BoundedMemo(512)   # (CLAUDE_PROJECTS, sid) -> (checked at, project dir name or "")


def _rail_home(fo, sid, *cwds):
    """Project dir name under CLAUDE_PROJECTS that holds session `sid` ("" if none).
    Each cwd's slug is tried first; the `*/<sid>` glob runs only on a miss. Memo RAIL_HOME_TTL, re-checked on a hit."""
    if not sid or os.sep in sid or sid in (".", ".."):
        return ""
    base, now = fo.CLAUDE_PROJECTS, time.time()
    bases = projects_dirs(base)   # extra account roots after the primary one

    def has(name):
        return any(os.path.isdir(p) or os.path.isfile(p + ".jsonl") for p in (os.path.join(b, name, sid) for b in bases))
    hit = _rail_home_c.get((base, sid))
    if hit and now - hit[0] < RAIL_HOME_TTL and (not hit[1] or has(hit[1])):
        return hit[1]
    home = next((s for s in (_slug(c) for c in cwds if c) if has(s)), "")
    if not home:
        g = glob.escape(sid)
        found = next((f for b in bases for f in (glob.glob(os.path.join(b, "*", g))
                                                 or glob.glob(os.path.join(b, "*", g + ".jsonl")))), "")
        home = os.path.basename(os.path.dirname(found)) if found else ""
    _rail_home_c.put((base, sid), (now, home))
    return home


def _rail_pcwd(home, *cwds):
    """cwd for the work log: work.agent_work/_past_row only look under `_slug(cwd)`, so it must slug to `home`.
    ⚠The edit's own cwd can differ (worktree-isolated agent, cd'd session) — sending it made the popup fail."""
    cwds = [c for c in cwds if c]
    if home:
        for c in cwds:
            if _slug(c) == home:
                return c
        c = _cwd_from_slug(home)
        if c and _slug(c) == home:
            return c
    return cwds[0] if cwds else ""


def _rail_tid(fo, sid, aid, home):
    """Subagent file id -> its Agent toolUseId (what /api/agent/work takes); "" when the meta is not found.
    `home` = `_rail_home`; agents._agent_meta is TTL-cached per session dir."""
    for b in projects_dirs(fo.CLAUDE_PROJECTS) if home else ():
        d = os.path.join(b, home, sid)
        if not os.path.isdir(d):
            continue
        for tid, m in _agent_meta(d).items():
            if m.get("_id") == aid:
                return tid
    return ""


def _rail_owners(root, files, rows=None, now=None, dirty=None):
    """Adds `own` [{sid8, sid, cwd, proj, main, tid, lab, agent, n, ago}] and `conflict` to each listed file from file_owner's cached index.
    sid/cwd/tid (ids only) let the rail open the work log (cwd = `_rail_pcwd`, not the edit's own cwd); proj labels the conflict popover.
    ★Conflict = file_owner's live + FO_CONFLICT_S rule, but only across >= 2 distinct sessions (user 09-25: sibling
      agents of one session are not a conflict here).
    ★`dirty` = tracked uncommitted paths (`_status_tracked`): like file_owner.conflicts, a committed file is never a conflict
      (base=remote lists committed-but-unpushed files — without this they showed a false «Conflict»). None = no filter (tests).
    ⛔Metadata only: the description is the parent's one-line label."""
    from sidereus import file_owner as fo          # ⚠lazy: file_owner -> sidereus.git -> git_view is an import cycle
    now = time.time() if now is None else now
    idx = fo.index(now)
    if not idx:
        return
    rows = (sessions_snapshot(60) or []) if rows is None else rows
    lu = fo._live_units(rows)
    rw = {r.get("sid"): r for r in rows if isinstance(r, dict) and r.get("sid")}
    tids, homes = {}, {}                         # memo for this call: (sid, aid) -> toolUseId · sid -> (home, popup cwd)
    for f in files:
        units = idx.get(os.path.normpath(os.path.join(root, f.get("path") or "")))
        if not units:
            continue
        own = []
        for (sid, aid), o in sorted(units.items(), key=lambda kv: -kv[1]["ts"])[:RAIL_OWN_MAX]:
            lab = (o.get("desc") or "").strip()
            main, cwd = aid == fo.FO_MAIN, o.get("cwd") or ""
            if sid not in homes:
                rc = (rw.get(sid) or {}).get("cwd") or ""
                h = _rail_home(fo, sid, rc, cwd)
                homes[sid] = (h, _rail_pcwd(h, rc, cwd))
            home, pcwd = homes[sid]
            if not main and (sid, aid) not in tids:
                tids[(sid, aid)] = _rail_tid(fo, sid, aid, home) if home else ""
            own.append({"sid8": _sid8(sid), "sid": sid, "cwd": pcwd or cwd, "main": main,
                        "proj": (rw.get(sid) or {}).get("project") or os.path.basename(pcwd or cwd),
                        "tid": "" if main else tids[(sid, aid)],
                        "lab": lab if len(lab) <= RAIL_OWN_LAB else lab[:RAIL_OWN_LAB - 1] + "…",
                        "agent": o.get("agent") or "", "n": int(o.get("n") or 1), "ago": int(now - o["ts"])})
        f["own"] = own
        if (dirty is None or f.get("path") in dirty) and len({u[0] for u in fo._hot(units, lu, now)}) >= 2:
            f["conflict"] = True


def _git_rail(cwd, run, st=None, since=0, mode="auto"):
    """Timeline right rail: every file changed vs a baseline (uncommitted + untracked, plus commits since a non-HEAD base),
    per-file numstat, branch header, commits since the base.
    ★Baseline modes (`_rail_base`): head (uncommitted only) · start (session start) · remote (vs master/remote).
    ★auto (default): remote when the repo has a remote (`_has_remote`), else head. `baseMode` = resolved.
    ★git calls: status, diff, log; start/remote add 1 for the base (merge-base or rev-list); default branch from ref files.
    `st` = status output already fetched by the caller (it checks the returncode for "not a repo").
    ⚠No patch body — the rail polls; the diff window still fetches the full view."""
    if st is None:
        st = run(RAIL_STATUS)
    head = _status_branch((st or "").replace("\0", "\n"))
    # No commits yet: HEAD does not resolve, so diff the index against the empty tree (staged new files show as A).
    unborn = "# branch.oid (initial)" in (st or "")
    if mode == "auto":
        mode = "remote" if not unborn and _has_remote(cwd, head["upstream"]) else "head"
    base, kind, ref, no_remote = ((EMPTY_TREE, "head", "", False) if unborn
                                  else _rail_base(cwd, run, head["branch"], since, mode, head["upstream"]))
    # ⚠head = strictly working tree + index vs HEAD (what an IDE shows); unpushed commits are the "upstream" mode, never a fallback.
    files = _raw_numstat(run(["diff", base, "--raw", "--numstat", "-z", "-M", "--"]))
    seen = {f["path"] for f in files}
    untr = [p for p in _status_untracked(st) if p not in seen]   # `git rm --cached x`: D in diff + ? in status
    root = _repo_root(cwd)
    files += [_untracked_rec(root, p) for p in untr[:RAIL_UNTRACKED_MAX]]
    if unborn:
        commits, ncm = [], 0
    elif kind == "head":
        commits, ncm = _commits(run, "HEAD", RAIL_COMMITS), 0
    else:
        commits = _commits(run, base + "..HEAD", RAIL_BASE_COMMITS_MAX)
        ncm = len(commits)
        commits = commits[:RAIL_COMMITS] if commits else _commits(run, "HEAD", RAIL_COMMITS)
    n = len(files) + max(0, len(untr) - RAIL_UNTRACKED_MAX)
    try:
        _rail_owners(root or cwd, files[:RAIL_FILES_MAX], dirty=_status_tracked(st))
    except Exception:
        pass                                     # owners are decoration: the file list must still paint
    out = {"ok": True, "cwd": cwd, "view": "rail", "hasUp": bool(head["upstream"]),
           "n": n, "add": sum(f["add"] for f in files), "del": sum(f["del"] for f in files),
           "files": files[:RAIL_FILES_MAX], "untracked": len(untr), "commits": commits,
           "base": "" if kind == "head" else base, "baseKind": kind, "baseRef": ref, "baseMode": mode,
           "noRemote": no_remote,
           "since": int(since) if kind == "start" else 0,
           "nCommits": ncm, "commitsCut": ncm >= RAIL_BASE_COMMITS_MAX, "dirty": _status_dirty(st)}
    out.update(head)
    main = _main_name(cwd, root)
    if main:
        out["main"] = main
    return out


def _main_name(cwd, root):
    """Main repo folder name for a linked worktree ('' otherwise), from `.git`/`commondir` files only — chip label."""
    common = _git_common_dir(cwd)
    if not common or os.path.basename(common) != ".git":
        return ""
    if os.path.realpath(common) == os.path.realpath(os.path.join(root or cwd, ".git")):
        return ""
    return os.path.basename(os.path.dirname(os.path.realpath(common)))
