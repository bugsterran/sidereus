"""Branch graph (+ background warm-up). Work-unit layer over worktrees (signals, tokens, order) lives in sidereus/git_wt.py.
Single-repo views (diff, commit, access guard, remote, git-flow) live in sidereus/git_view.py (split 2026-09-24)."""
import json
import os
import re
import subprocess
import threading
import time
from sidereus import boot_queue
from sidereus.bus import _atomic_write
from sidereus.config import DATA_DIR
from sidereus.gitinfo import _git_run, _worktrees, git_slot_free
from sidereus.git_wt import WT_STALE_DAYS, _WT_LAST, _WT_LOCK, wt_order, wt_signals
from sidereus.warn import warn_once
# Re-exported: chat_server / commit_link / file_owner import these from sidereus.git; the rest are used below.
from sidereus.git_view import (BR_FETCH_STALE_H, _branch_ok, flow_base, flow_info, flow_parse, git_commit,  # noqa: F401
                            git_diff, git_file_diff, remote_info)


# ★Branch graph raw data (2026-09-23) — the UI draws a branch/commit graph. Read-only.
# ⚠Never hook it into polling — call on click only. Same (cwd, n) cached 20 s (`_git_state` convention).
BRANCH_TIMEOUT = 6              # same cap as DIFF_TIMEOUT — big working trees answer within it
BRANCH_TTL = 20
BRANCH_N_DEF, BRANCH_N_MAX = 80, 300
BRANCH_MAX = 500                # some repos have hundreds of branches — cut by most recent commit
_branch_cache = {}              # (cwd, n) -> (at, out)
# ★Measured 2026-09-24: cold miss 0.60 s (sessions() when the poll snapshot is stale), git-only miss 0.05 s, hit 0.000 s.
# ⇒ A background loop rebuilds keys a user asked for within BR_WARM_WANT_S just before BRANCH_TTL runs out,
#   so a tab switch hits the cache. ⚠Keys nobody requested are never built — no CPU when the tab is unused.
BR_WARM_TICK_S = 5
BR_WARM_LEAD_S = 6              # rebuild when the entry is this close to expiry (> one tick)
BR_WARM_WANT_S = 300            # "recently requested" window; a warm rebuild never extends it
BR_WARM_WAIT_S = 0.2            # ⚠warm-up never queues behind users for the git slot: skip the tick instead
BR_WARM_PROBES = 2              # ⚠boot warm gives up a busy key after ~10 s: it holds the boot gate meanwhile
_br_want = {}                  # (cwd, n) -> last user request time
_BR_WARM_THR = []
# ★2026-09-25: _br_want starts empty after a restart, so the first tab open was cold (0.57 s).
# ⇒ Requested keys are persisted; main() rebuilds the recent ones once in the background (br_boot_warm_start).
BR_WARM_FILE = os.path.join(DATA_DIR, "branch-warm.json")
BR_PERSIST_KEEP_S = 24 * 3600
BR_PERSIST_MAX = 5
BR_PERSIST_EVERY_S = 60         # same key re-saved at most once a minute (tab switches are frequent)
_br_seen = {}                   # (cwd, n) -> last user request time, persisted
_BR_SEEN_LOCK = threading.Lock()
_BR_SEP = "\x1f"
_BR_FMT = ("%(refname)" + _BR_SEP + "%(objectname:short=7)" + _BR_SEP + "%(upstream:short)"
           + _BR_SEP + "%(upstream:track)" + _BR_SEP + "%(committerdate:unix)"
           + _BR_SEP + "%(HEAD)")
# ⚠Distinct name from `_LOG_FMT` (diff view): sharing it overwrote that one and emptied unpushed/pushed lists.
_BR_LOG_FMT = ("%h" + _BR_SEP + "%p" + _BR_SEP + "%ct" + _BR_SEP + "%an"
            + _BR_SEP + "%D" + _BR_SEP + "%s")
_BR_AHEAD = re.compile(r"ahead (\d+)")
_BR_BEHIND = re.compile(r"behind (\d+)")


def _branch_refs(txt):
    """One `%D` line -> names attached to that commit. `HEAD -> main` is split in two, `tag: ` stripped."""
    out = []

    def put(x):
        x = (x or "").strip()
        if x.endswith("/HEAD"):
            return                        # ⚠`origin/HEAD` is symbolic — excluded from the branch list too
        if x and x not in out:
            out.append(x)

    for piece in (txt or "").split(", "):
        piece = piece.strip()
        if not piece:
            continue
        if " -> " in piece:
            a, b = piece.split(" -> ", 1)
            put(a)
            put(b)
            continue
        if piece.startswith("tag: "):
            piece = piece[5:]
        put(piece)
    return out


WT_FILES_MAX = 300


def wt_files(cwd):
    """Uncommitted files of one worktree for the Branches tab work-unit panel (untracked rows keep st "??")."""
    if not cwd or not os.path.isdir(cwd):
        return 400, {"ok": False, "err": "cwd required"}
    if not _branch_ok(cwd):
        return 403, {"ok": False, "err": "not allowed"}
    try:
        r = _git_run(cwd, ["status", "--porcelain", "-unormal", "-z", "--no-renames"], BRANCH_TIMEOUT)
    except subprocess.TimeoutExpired:
        return 504, {"ok": False, "err": "timeout"}
    except Exception as e:
        return 500, {"ok": False, "err": "git " + type(e).__name__}
    if r.returncode != 0:
        return 400, {"ok": False, "err": "not a git repo"}
    files = [{"st": rec[:2].strip(), "path": rec[3:]} for rec in r.stdout.split("\0") if len(rec) > 3]
    return 200, {"ok": True, "cwd": cwd, "files": files[:WT_FILES_MAX], "n": len(files)}


def _br_warm_start():
    with _WT_LOCK:
        if not _BR_WARM_THR:
            _BR_WARM_THR.append(threading.Thread(target=_br_warm_loop, name="br_warm", daemon=True))
            _BR_WARM_THR[0].start()


def _br_warm_tick(now=None):
    """One pass: drop keys not requested within BR_WARM_WANT_S, rebuild the rest near expiry. -> rebuilt keys."""
    now = time.time() if now is None else now
    done = []
    for key, at in list(_br_want.items()):
        if now - at > BR_WARM_WANT_S:
            _br_want.pop(key, None)
            continue
        hit = _branch_cache.get(key)
        if hit and now - hit[0] < BRANCH_TTL - BR_WARM_LEAD_S:
            continue
        if not git_slot_free(BR_WARM_WAIT_S):
            break                         # git slots saturated by user requests — try next tick
        try:
            branch_graph(key[0], key[1], _warm=True)
            done.append(key)
        except Exception as e:
            warn_once("br-warm-key", "branch warm-up failed ({err}) — computed on request instead",
                      vars={"err": f"{type(e).__name__}: {e}"}, soft=True)
    return done


def _br_warm_loop(_sleep=time.sleep, _ticks=None):
    """`_ticks` (tests only) bounds the loop; production runs forever.
    ⚠Catch per tick: one exception used to end this thread silently and branch warm-up stopped for the process lifetime."""
    n = 0
    while _ticks is None or n < _ticks:
        n += 1
        _sleep(BR_WARM_TICK_S)
        try:
            _br_warm_tick()
        except Exception as e:
            from sidereus.warn import warn_once
            warn_once("br-warm", "branch warm-up tick failed ({err}) — retrying next tick",
                      vars={"err": f"{type(e).__name__}: {e}"}, soft=True)


def _br_recent(d, now):
    """Keys requested within BR_PERSIST_KEEP_S, newest BR_PERSIST_MAX."""
    keep = [(at, k) for k, at in d.items() if now - at <= BR_PERSIST_KEEP_S]
    keep.sort(reverse=True)
    return {k: at for at, k in keep[:BR_PERSIST_MAX]}


def _br_seen_note(key, now):
    """Record a user request; save when the key is new or its last save is older than BR_PERSIST_EVERY_S."""
    with _BR_SEEN_LOCK:
        prev = _br_seen.get(key)
        _br_seen[key] = now
        if prev is not None and now - prev < BR_PERSIST_EVERY_S:
            return False
        keep = _br_recent(_br_seen, now)
        _br_seen.clear()
        _br_seen.update(keep)
        rows = [{"cwd": k[0], "n": k[1], "at": at} for k, at in keep.items()]
        try:                              # ⚠write under the lock: outside it an older snapshot could land last
            _atomic_write(BR_WARM_FILE, json.dumps(rows, ensure_ascii=False).encode("utf-8"))
        except Exception:
            pass                          # warm-up hint only — never fail a user request over it
    return True


def _br_seen_load(now):
    """Persisted keys -> {(cwd, n): at}, stale/malformed rows dropped."""
    try:
        with open(BR_WARM_FILE, encoding="utf-8") as f:
            rows = json.load(f)
    except (OSError, ValueError):
        return {}                         # no or corrupt warm-up list: warm from what gets seen next
    d = {}
    for r in rows if isinstance(rows, list) else []:
        try:
            d[(str(r["cwd"]), int(r["n"]))] = float(r["at"])
        except Exception:
            continue
    return _br_recent(d, now)


def br_boot_warm(now=None):
    """Startup: build the recent persisted keys once, then keep them warm for BR_WARM_WANT_S. -> built keys.
    ⚠Only cwds that pass `_branch_ok`; never waits behind user requests for the git slot."""
    now = time.time() if now is None else now
    got = _br_seen_load(now)
    with _BR_SEEN_LOCK:
        for k, at in got.items():
            _br_seen.setdefault(k, at)
    if not got:
        boot_queue.done("br_boot_warm")     # nothing to warm: do not hold up the boot drain
        return []
    done = []
    with boot_queue.gate("br_boot_warm"):   # ⚠boot warms run one at a time (traps/server.md)
        for key in got:
            if not os.path.isdir(key[0]) or not _branch_ok(key[0]):
                continue
            for _ in range(BR_WARM_PROBES):
                if git_slot_free(BR_WARM_WAIT_S):
                    break
                time.sleep(BR_WARM_TICK_S)
            else:
                continue                    # slot stayed busy: this key warms on its first request
            try:
                branch_graph(key[0], key[1], _warm=True)
            except Exception:
                continue
            _br_want.setdefault(key, now)
            done.append(key)
    if done:
        _br_warm_start()
    return done


def br_boot_warm_start():
    """Called from chat_server.main() only — importing the module starts no thread."""
    threading.Thread(target=br_boot_warm, name="br_boot_warm", daemon=True).start()


def branch_graph(cwd, n=BRANCH_N_DEF, _warm=False):
    """Branch/commit graph raw data. 3 git calls (`for-each-ref` + `log --all` + `worktree list`).
    `_warm` = background rebuild: skips the cache and does not count as a request."""
    try:
        n = int(n)
    except Exception:
        n = BRANCH_N_DEF
    n = max(1, min(BRANCH_N_MAX, n))
    key = (cwd, n)
    if not _warm:
        _br_want[key] = time.time()
        _br_seen_note(key, _br_want[key])
        _br_warm_start()                  # lazy: the thread exists only once the tab was used
    hit = None if _warm else _branch_cache.get(key)
    if hit and time.time() - hit[0] < BRANCH_TTL:
        out = dict(hit[1])
        out["cached"] = True
        out["wtOrder"] = wt_order(out["worktrees"], out["wtSig"], _WT_LAST["sess"], _WT_LAST["attn"])
        return out
    t0 = time.time()

    wait = BR_WARM_WAIT_S if _warm else None
    miss = []                             # sub-calls that timed out (extras swallow them into fallbacks)

    def run(args):
        try:
            return _git_run(cwd, args, BRANCH_TIMEOUT, wait=wait)
        except subprocess.TimeoutExpired:
            miss.append(args[0])
            raise

    try:
        r1 = run(["for-each-ref", "--sort=-committerdate", "--count=" + str(BRANCH_MAX),
                  "--format=" + _BR_FMT, "refs/heads", "refs/remotes"])
        if r1.returncode != 0:
            return {"ok": False, "err": "not a git repo"}
        r2 = run(["log", "--all", "--date-order", "--abbrev=7", "-n", str(n + 1),
                  "--format=" + _BR_LOG_FMT])
        log_out = r2.stdout if r2.returncode == 0 else ""   # ⚠repo without commits — return an empty graph
    except subprocess.TimeoutExpired:
        return {"ok": False, "err": "timeout"}
    except Exception as e:
        return {"ok": False, "err": "git " + type(e).__name__}

    branches, head, detached = _br_refs(r1.stdout)
    unborn = _br_unborn(run) if detached else ""
    if unborn:                            # ⚠HEAD on a branch with no commit yet is not detached (empty repo / orphan)
        head, detached = unborn, False
    commits, truncated = _br_commits(log_out, n)
    if detached:                          # detached has no name — answer with the sha of the commit carrying HEAD
        for c in commits:
            if "HEAD" in c["refs"]:
                head = c["sha"]
                break
    wts, flow, sig, rem = _br_extras(cwd, run, branches, commits, wait, miss)
    out = {"ok": True, "remote": rem, "fetchStaleH": BR_FETCH_STALE_H, "cwd": cwd, "repo": os.path.basename(cwd.rstrip("/")) or cwd,
           "head": head, "detached": detached, "unborn": bool(unborn), "branches": branches, "commits": commits, "flow": flow,
           "worktrees": wts, "wtSig": sig["wtSig"], "wtTok": sig["wtTok"], "wtStaleDays": WT_STALE_DAYS,
           "truncated": truncated, "ms": int((time.time() - t0) * 1000)}
    # ⚠A timed-out sub-call means fallbacks (0 worktrees, default flow): never cache that over a good entry.
    #   Warm: previous entry kept, next tick retries. User: served once, uncached.
    if not miss:
        if len(_branch_cache) > 64:       # ⚠never accumulate unbounded — it is a 20 s cache
            _branch_cache.clear()
        _branch_cache[key] = (time.time(), out)
    # Fetch-time order from the last poll's inputs; the poll's `wtOrder` supersedes it (not stored in the cache).
    return dict(out, wtOrder=wt_order(wts, sig["wtSig"], _WT_LAST["sess"], _WT_LAST["attn"]))


def _br_refs(stdout):
    """`for-each-ref` output -> (branches, head name, detached)."""
    branches, head, detached = [], "", True
    for line in stdout.splitlines():
        f = line.split(_BR_SEP)
        if len(f) < 6:
            continue
        full, sha, up, track, ts, mark = f[0], f[1], f[2], f[3], f[4], f[5]
        if full.startswith("refs/heads/"):
            name, kind = full[11:], "local"
        elif full.startswith("refs/remotes/"):
            name, kind = full[13:], "remote"
        else:
            continue
        if name.endswith("/HEAD"):
            continue                      # ⚠`origin/HEAD` is symbolic — the same commit would be drawn twice
        a = _BR_AHEAD.search(track or "")
        b = _BR_BEHIND.search(track or "")
        if mark.strip() == "*":
            head, detached = name, False
        branches.append({"name": name, "kind": kind, "sha": sha, "upstream": up or "",
                         "ahead": int(a.group(1)) if a else 0,
                         "behind": int(b.group(1)) if b else 0,
                         "ts": int(ts) if ts.isdigit() else 0})
    return branches, head, detached


def _br_unborn(run):
    """Branch name HEAD points at when no ref carries the `*` mark (unborn branch), else ""."""
    try:
        r = run(["symbolic-ref", "-q", "--short", "HEAD"])
    except Exception:
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def _br_commits(log_out, n):
    """`log --all` output -> (first n commits, truncated)."""
    commits = []
    for line in log_out.splitlines():
        f = line.split(_BR_SEP, 5)
        if len(f) < 6:
            continue
        subj = f[5].replace("\r", " ").replace("\n", " ").strip()
        commits.append({"sha": f[0], "parents": [p for p in f[1].split() if p],
                        "subject": subj[:200], "author": f[3],
                        "ts": int(f[2]) if f[2].isdigit() else 0,
                        "refs": _branch_refs(f[4])})
    truncated = len(commits) > n
    return commits[:n], truncated


def _br_extras(cwd, run, branches, commits, wait, miss):
    """(worktrees, flow, signals, remotes); each falls back instead of failing the graph."""
    wts = _worktrees(run)
    try:
        flow = flow_info(run, [b["name"] for b in branches if b["kind"] == "local"])
    except Exception:                     # extras — a default flow keeps the form usable
        flow = flow_parse("", [b["name"] for b in branches if b["kind"] == "local"])
    try:
        sig = wt_signals(wts, branches, commits, flow=flow, wait=wait, miss=miss)
    except Exception as e:                # ⚠signals are extras — never lose the graph over them
        if isinstance(e, subprocess.TimeoutExpired):
            miss.append("signals")
        sig = {"wtSig": {}, "wtTok": {"err": type(e).__name__}}
    try:
        rem = remote_info(cwd)
    except subprocess.TimeoutExpired:
        miss.append("remote")
        rem = []
    except Exception:                     # extras too — the graph stands without them
        rem = []
    return wts, flow, sig, rem
