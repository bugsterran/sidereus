"""Structure/growth treemap API (GET /api/structure, /api/structure/src) and idle warm-up."""
import hashlib
import os
import re
import subprocess
import tarfile
import time
from sidereus import boot_queue, config
from sidereus.config import CODE_DIR
from sidereus.warn import warn_once
from sidereus.gitinfo import SHA_HEX_RE, _git_slot, git_argv, git_env
from sidereus.work import _allowed_cwds
from sidereus.sessions import sessions_snapshot, sessions_snapshot_wait
from sidereus.structure_scan import (STRUCT_EXTS, STRUCT_REL_EXTS, STRUCT_RULES_VER, STRUCT_SKIP, STRUCT_MAX_BYTES,
    STRUCT_MAX_FNS, STRUCT_FULL_FNS, STRUCT_MAX_FILES, STRUCT_GIT_TIMEOUT, STRUCT_CACHE_N, STRUCT_AREAS, STRUCT_ETC,
    _struct_lock, _struct_out_cache, _struct_group, _struct_label, _struct_tmode)
from sidereus.structure_cache import _struct_disk_read, _struct_disk_write, _struct_disk_prune
from sidereus.structure_snap import (_struct_git, _struct_git_tree, _struct_backups, _struct_plain, _struct_tar,
    _struct_now)
# Pairing matcher lives in structure_pairing. ⚠STRUCT_PAIR_REF_MAX/_struct_pair_ls are unused here but tests read them off sidereus("structure").
from sidereus.structure_pairing import (STRUCT_PAIR_REF_MAX, _struct_pair_ls,  # noqa: F401
    _struct_pair_match, _struct_pair_files)


def structure(path=None, tests=False, full=False, mem=True):
    """Body of `GET /api/structure?path=…&tests=0|1|only&full=0|1` — past points (git first) + current,
    oldest → newest.
    ★`tests` defaults to 0 (tests excluded) — 2026-09-22, tests showing up first was unwanted.
    ★`full` = lifts the per-area cap to `STRUCT_FULL_FNS`. Called only when the screen drills down by clicking a «Show N more»
      bundle cell — lifting it on the full screen means thousands of cells and playback lags.
    `mem=False` = disk cache only (idle warm-up), the memory cache is neither filled nor touched."""
    tests = _struct_tmode(tests)       # 0 core · 1 all · 2 tests only
    full = bool(full)
    maxf = STRUCT_FULL_FNS if full else STRUCT_MAX_FNS
    # ⚠Allow list first, before any walk — a raw realpath let `?path=/` list any dir and scan the whole disk (cross-site <img> too).
    root = _struct_src_root(path)
    if not root:
        return {"ok": False, "msg": "Only projects shown on screen can be opened."}
    if not os.path.isdir(root):
        return {"ok": False, "msg": "Not a directory: {path}", "vars": {"path": path or CODE_DIR}}

    gits = _struct_git(root)
    baks = [] if gits else _struct_backups(root)
    key, newest = _struct_key(root, gits, baks, tests, maxf)
    ck = (root, tests, maxf)
    now = time.time()
    hit, dkey = _struct_cache_get(root, ck, key, now, mem)
    if hit is not None:
        return hit

    stages, failed = _struct_stages(root, gits, baks, tests)
    try:
        cur_got = _struct_now(root, tests)
    except Exception as e:
        return {"ok": False, "msg": "%s: %s" % (type(e).__name__, e)}
    # ⚠The current one is **always last** (schema promise). The working tree mtime can be earlier than the last commit
    #   (a repository untouched after checkout — measured repo-A `cur` 8/31 < commit 9/10),
    #   so the time is raised too to keep the time axis from going backwards.
    cur_ts = newest or now
    if stages:
        cur_ts = max(cur_ts, stages[-1][0])
    stages.append((cur_ts, "cur", "", cur_got))
    # ★The basis for `partial` is **the current tree's file count** — using the max that also counts files only in old backups
    #   (deleted now) stamps the current snapshot as partial (measured Sidereus tar 10 vs current 7).
    snaps = _struct_snaps(stages, cur_got[3], maxf)
    out = {"ok": True, "at": int(now), "path": root, "tests": tests, "warm": False,
           "full": full, "maxfns": maxf,
           "areas_def": _struct_areas_def(snaps),
           "snaps": snaps}
    if failed:
        # ★Served for this request only: the key (sha·nfile·mtime) doesn't change in a quiet repo, so a cached
        #   incomplete history would stick even across restarts.
        out["incomplete"] = True
        return out
    _struct_cache_put(ck, key, dkey, out, now, mem)
    return out


def _struct_key(root, gits, baks, tests, maxf):
    """Cache key for one structure() call -> (key, newest source mtime in the current tree)."""
    # cache key — fingerprint of past sources + fingerprint of the current tree. Past (sha·tar·bak) is immutable, so it also lives separately.
    sig = [s for _t, s in gits]
    for _ts, _kind, p, _orig in baks:
        try:
            sig.append("%s:%s" % (p, os.path.getmtime(p)))
        except OSError:
            sig.append(p)
    newest = 0.0
    nfile = 0
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in STRUCT_SKIP and not d.startswith(".")]
        for fn in fns:
            if fn.endswith(STRUCT_EXTS):
                nfile += 1
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(dp, fn)))
                except OSError:
                    pass                # vanished mid-walk: counted, no mtime
        # ⚠Same bound as _struct_now — an unbounded walk here made the file cap there pointless.
        if nfile > STRUCT_MAX_FILES * 2:
            break
    # ⚠`tests` and the classification rules version must be in the key — otherwise toggling returns old results.
    #   ⚠0/1 stay bool — the disk key hashes repr(key), and an int would orphan every existing out-cache entry.
    return (tuple(sig), nfile, int(newest), STRUCT_RULES_VER, tests if tests == 2 else bool(tests), maxf), newest


def _struct_cache_get(root, ck, key, now, mem=True):
    """Memory then disk cache lookup -> (warm copy or None, disk key)."""
    # ⚠`warm` is put **only on the returned copy** — mutating the dict frozen in the cache makes the next cold call
    #   claim to be warm. A shallow copy is fine (read-only).
    with _struct_lock:
        hit = _struct_out_cache.get(ck)
        if hit and hit[0] == key:
            if mem:
                _struct_out_cache[ck] = (key, hit[1], now)
            return dict(hit[1], warm=True), None
    # disk — same key reuses it even after restart. The key must be **identical** to the memory cache for results to match.
    dkey = "out|%s|%s" % (root, hashlib.sha1(repr(key).encode("utf-8", "replace"), usedforsecurity=False).hexdigest())
    dout = _struct_disk_read("out", dkey)
    if isinstance(dout, dict) and dout.get("ok"):
        if mem:
            _struct_out_put(ck, key, dout, now)
        return dict(dout, warm=True), dkey
    return None, dkey


def _struct_cache_put(ck, key, dkey, out, now, mem=True):
    """Persist a complete result to disk and (unless `mem` is False) the bounded memory cache."""
    _struct_disk_write("out", dkey, out)
    if mem:
        _struct_out_put(ck, key, out, now)


def _struct_out_put(ck, key, out, now):
    """Only insert path into `_struct_out_cache` (oldest evicted past STRUCT_CACHE_N) — disk hits too."""
    with _struct_lock:
        _struct_out_cache[ck] = (key, out, now)
        if len(_struct_out_cache) > STRUCT_CACHE_N:   # ⚠do not create a dict without expiry
            old = sorted(_struct_out_cache.items(), key=lambda kv: kv[1][2])
            for k, _v in old[:len(_struct_out_cache) - STRUCT_CACHE_N]:
                _struct_out_cache.pop(k, None)


def _struct_stages(root, gits, baks, tests):
    """Past snapshots (git + backups), time-ordered -> (stages, a git stage failed)."""
    stages = []                            # (time, kind, rev, (total lines, function list, trunc, file count))
    failed = False                         # ⚠a failed git stage (None) must not be persisted — see end
    for ts, sha in gits:
        got = _struct_git_tree(root, sha, tests)
        if got is None:
            failed = True
        if got:
            stages.append((ts, "git", sha[:8], got))
    for ts, kind, p, orig in baks:
        got = _struct_tar(p, tests) if kind == "tar" else _struct_plain(p, orig, tests)
        if got:
            stages.append((ts, "backup" if kind == "tar" else "bak", "", got))
    stages.sort(key=lambda s: s[0])        # ⚠mixing sources breaks time order — churn becomes false
    return stages, failed


def _struct_snaps(stages, nfull, maxf):
    """Per-stage grouped snapshots with churn/last-changed tracking across stages."""
    churn = {}
    # ★`lastv` = function key → **the snapshot number where it last changed** (the creation point also counts as «changed»).
    #   churn alone makes the screen one color — 0 for Sidereus 73.1%·repo-B 87.5% (measured 2026-09-22).
    lastv = {}
    prev = {}
    snaps = []
    for si, (ts, kind, rev, (total, fns, trunc, nf, nsk, nex, tfiles)) in enumerate(stages):
        cur_h = {}
        for fn in fns:
            k = "%s:%s:%s" % (fn["file"], fn["lang"], fn["name"])
            if k in cur_h:
                continue                   # for same-named ones track only the first (hash keys collide)
            cur_h[k] = fn["h"]
            if k in prev and prev[k] != fn["h"]:
                churn[k] = churn.get(k, 0) + 1
                lastv[k] = si
            elif k not in churn:
                churn[k] = 0
                lastv[k] = si
        snap = _struct_group(total, fns, trunc, churn, tfiles, lastv, maxf)
        snap.update({"at": int(ts), "label": _struct_label(ts), "src": kind, "files": nf,
                     # ★the number that answers «why is it not shown» — remove it and the same question comes again.
                     "excluded": nex})
        if nsk:
            snap["skipped"] = nsk          # number of java files the parser gave up on
        # ⚠`old-baks` is only the single file `chat_server.py`, so `total` at that point is not the whole
        #   project. Marked here so the screen does not read the steps as «growth».
        # ⚠The threshold is 90% — stamping partial even when one commit adds or removes one file (1641 vs 1642)
        #   would make almost every git repository partial (measured 2026-09-22).
        if nf < nfull * 0.9:
            snap["partial"] = True
        if rev:
            snap["rev"] = rev
        snaps.append(snap)
        prev = cur_h
    return snaps


def _struct_areas_def(snaps):
    """Areas in first-seen order across snapshots, with display names."""
    seen = []
    for s in snaps:
        for a in s["areas"]:
            if a["key"] not in seen:
                seen.append(a["key"])
    names = dict((k, n) for k, n, _p, _h in STRUCT_AREAS)
    names[STRUCT_ETC[0]] = STRUCT_ETC[1]
    return [{"key": k, "name": names.get(k, k)} for k in seen]


# ── cell source view (GET /api/structure/src) ─────────────────────────────────
# ★2026-09-22: clicking a structure cell should show its code or a sub-code list to be worth looking at
#   — a treemap cell is one function. Emit that cell's «body at that point» as-is.
#   ⚠This is **the target project's source code**. Other sessions' «conversations» are still never put up (rule 1).
# ⚠Always confine the path. `path` only for projects on screen (`_struct_warm_targets()` = session cwd +
#   repos + Sidereus itself), `file` only relative paths beneath it, extensions only those structure looks at (`STRUCT_EXTS`).
#   Without this, `?file=../../.ssh/id_rsa` becomes an arbitrary file read hole.
# ⚠git **read-only** only (`show <rev>:<file>`) — `checkout`·`reset` break the user's working tree.
# ⚠If that point's version cannot be obtained, serve the current file but **state it** with `exact:false`. Silently serving the current one
#   makes the screen pretend to show the past.
STRUCT_SRC_MAX_LINES = 400     # ★a 588-line function was measured — beyond this, serve the beginning and note it was truncated
STRUCT_SRC_CACHE_N = 120       # memory LRU (one response is at most 400 lines)
_struct_src_cache = {}         # key -> (result, last used time)


# ⚠`.xml` opens only when it is a MyBatis mapper (config XMLs may hold secrets); STRUCT_EXTS stays without `.xml`.
_STRUCT_MB_HEAD = 4096
_STRUCT_MB_NS = re.compile(r"<mapper\b[^>]*?\bnamespace\s*=")


def _struct_mb_xml(root, rel):
    """-> True if `root/rel` is a regular file inside root whose first 4 KB hold `<mapper … namespace=`."""
    try:
        rr = os.path.realpath(root)
        fp = os.path.realpath(os.path.join(rr, rel))
        if os.path.commonpath([rr, fp]) != rr or not os.path.isfile(fp):
            return False
        with open(fp, "rb") as f:
            return bool(_STRUCT_MB_NS.search(f.read(_STRUCT_MB_HEAD).decode("utf-8", "replace")))
    except (OSError, ValueError):
        return False


def _struct_src_rel(rel, root=None):
    """Normalize a relative path. Absolute paths·`..`·extensions structure does not look at give **an empty string** (rejected).
    With `root`, a MyBatis mapper `.xml` under it is also accepted (`_struct_mb_xml`)."""
    rel = (rel or "").strip().replace("\\", "/")
    if not rel or rel.startswith("/") or os.path.isabs(rel):
        return ""
    parts = []
    for p in rel.split("/"):
        if p in ("", "."):
            continue
        if p == "..":
            return ""
        parts.append(p)
    rel = "/".join(parts)
    if rel.endswith(STRUCT_REL_EXTS):          # every scanned ext plus .vue
        return rel
    return rel if root and rel.endswith(".xml") and _struct_mb_xml(root, rel) else ""


def _struct_allowed_roots():
    """Allow list = warm-up targets + cwd/repos of EVERY row of the last `/api/state` sessions list.
    ⚠`_allowed_cwds()` keeps one row per cwd (a later row replaces an earlier one), but the structure tab
    (`strSessList`/`strProjs`) offers every row's own `repos` — a sibling repo seen only by the dropped row
    was refused with «Only projects shown on screen can be opened». `sessions_snapshot()` is exactly what the page
    got (no recompute); the warm-up targets stay in the union so a missing/old snapshot never shrinks the list.
    ⚠Warming is NOT widened to this set — more repos to warm costs CPU.
    ★2026-09-28: with a snapshot, warm targets (CODE_DIR + `_allowed_cwds()` rows, a subset of those same sessions()
      rows) add nothing but a cold `_allowed_cwds()` ran a full sessions() — 868 ms on the first «Structure» request.
      ⇒ snapshot present: CODE_DIR + snapshot rows only (never wider than before); absent: the old union."""
    cands = []
    try:
        snap = sessions_snapshot()
        if snap is None:                   # ⚠join an in-flight poll (post-restart) — a 2nd cold sessions() cost ~1 s
            snap = sessions_snapshot_wait()
        if snap is None:
            cands = list(_struct_warm_targets())
        elif config.IS_CLONE and os.path.isdir(CODE_DIR):      # same isdir filter _struct_warm_targets applies
            cands = [CODE_DIR]
        for r in snap or ():
            cands.append(r.get("cwd"))
            cands.extend(r.get("repos") or [])
    except Exception as e:
        cands = list(_struct_warm_targets()) + cands    # failure path = the old union
        warn_once("struct-allow", "structure allow-list failed ({err}) — some projects may be refused",
                  soft=True, vars={"err": f"{type(e).__name__}: {e}"})
    out = set()
    for p in cands:
        if not p:
            continue
        try:
            out.add(os.path.realpath(p))
        except Exception:
            continue
    # ⚠A session started in ~ or / would expose the whole home via /api/structure/src; repos under ~ still pass.
    return out - _struct_denied_roots()


def _struct_denied_roots():
    # ⚠Account home from pwd, not $HOME — an overridden $HOME (e.g. the data dir) must not block CODE_DIR.
    out = {os.path.realpath(os.sep)}
    try:
        import pwd
        out.add(os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir))
    except Exception:
        out.add(os.path.realpath(os.path.expanduser("~")))
    return out


def _struct_src_root(path):
    """realpath if inside the allow list (`_struct_allowed_roots()`), "" if outside."""
    try:
        root = os.path.realpath(path or CODE_DIR)
    except (OSError, ValueError, TypeError):
        return ""               # odd request path (NUL, non-str): outside the allow list
    return root if root in _struct_allowed_roots() else ""


def _struct_src_at(root, rel, src, rev, at):
    """Full file text at that point -> (body, is it that point, note). (None, …) if unreadable anywhere."""
    if src == "git" and rev and os.path.isdir(os.path.join(root, ".git")):
        try:
            with _git_slot():
                r = subprocess.run(git_argv(root, ["show", rev + ":" + rel]),
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   timeout=STRUCT_GIT_TIMEOUT, env=git_env())
            if r.returncode == 0 and len(r.stdout) <= STRUCT_MAX_BYTES:
                return r.stdout.decode("utf-8", "replace"), True, ""
        except Exception:
            pass                  # git missing/timeout: fall through to the working-tree read below
    elif src in ("backup", "bak"):
        want = "tar" if src == "backup" else "bak"
        for ts, kind, p, orig in _struct_backups(root):
            if kind != want or int(ts) != int(at):
                continue
            try:
                if kind == "bak":
                    if orig != rel:
                        continue
                    with open(p, "rb") as f:
                        return f.read().decode("utf-8", "replace"), True, ""
                with tarfile.open(p, "r:gz") as tf:      # the tar holds only top-level files
                    mem = tf.getmember(rel)
                    if mem.isfile() and mem.size <= STRUCT_MAX_BYTES:
                        fo = tf.extractfile(mem)
                        if fo:
                            return fo.read().decode("utf-8", "replace"), True, ""
            except Exception:
                continue
    # current file — either `cur`, or the substitute when the past point could not be obtained.
    # ⚠confine again with `realpath`: if a link points outside the project it must be filtered here.
    fp = os.path.realpath(os.path.join(root, rel))
    if fp != root and not fp.startswith(root + os.sep):
        return None, False, ""
    try:
        if not os.path.isfile(fp) or os.path.getsize(fp) > STRUCT_MAX_BYTES:
            return None, False, ""
        with open(fp, "rb") as f:
            body = f.read().decode("utf-8", "replace")
    except OSError:
        return None, False, ""
    if src == "cur":
        return body, True, ""
    return body, False, "Could not get the source at that point — showing the current file"


def structure_src(path=None, file="", line=1, lines=0, src="cur", rev="", at=0):
    """Body of `GET /api/structure/src?path=…&file=…&line=…&lines=…&src=…&rev=…&at=…`.
    Emits the body of one treemap cell (= function) with **file-based line numbers**.
    ★`src`/`rev`/`at` are exactly the snapshot the screen is viewing (`cur`·`git`+rev·`backup`/`bak`+at)."""
    root = _struct_src_root(path)
    if not root:
        return {"ok": False, "msg": "Only projects shown on screen can be opened."}
    rel = _struct_src_rel(file, root)
    if not rel:
        return {"ok": False, "msg": "This path cannot be read."}
    src = src if src in ("cur", "git", "backup", "bak") else "cur"
    rev = rev if (rev and SHA_HEX_RE.match(rev)) else ""
    try:
        line = max(1, int(line))
        lines = max(1, min(int(lines) or 40, 100000))
        at = int(at or 0)
    except (TypeError, ValueError):
        return {"ok": False, "msg": "Invalid range."}
    key = "src|%s|%s|%s|%s|%d|%d|%d" % (root, rel, src, rev, at, line, lines)
    now = time.time()
    with _struct_lock:
        hit = _struct_src_cache.get(key)
        if hit:
            _struct_src_cache[key] = (hit[0], now)
    if hit:
        return dict(hit[0], warm=True)
    # ★Past points (git sha · tar · bak) are **immutable** ⇒ they follow the existing disk cache convention as-is.
    #   `cur` is not frozen — it becomes false when the file changes (no mtime in the cache key).
    frozen = (src != "cur")
    if frozen:
        d = _struct_disk_read("src", key)
        if isinstance(d, dict) and d.get("ok"):
            with _struct_lock:
                _struct_src_cache[key] = (d, now)
            return dict(d, warm=True)
    body, exact, note = _struct_src_at(root, rel, src, rev, at)
    if body is None:
        return {"ok": False, "msg": "Could not read the file at that point in time."}
    if rel.endswith(".xml") and not _STRUCT_MB_NS.search(body[:_STRUCT_MB_HEAD]):   # ⚠a past version must be a mapper too
        return {"ok": False, "msg": "This path cannot be read."}
    all_l = body.split("\n")
    seg = all_l[line - 1:line - 1 + lines]
    trunc = len(seg) > STRUCT_SRC_MAX_LINES
    if trunc:
        seg = seg[:STRUCT_SRC_MAX_LINES]
    if not seg and not note:
        note = "The file at that point has no such line range"
    out = {"ok": True, "path": root, "file": rel, "src": src, "rev": rev, "at": at,
           "line": line, "n": len(seg), "want": lines, "total": len(all_l),
           "exact": bool(exact), "note": note, "truncated": trunc,
           "code": "\n".join(seg), "warm": False}
    if frozen and exact:
        _struct_disk_write("src", key, out)
    with _struct_lock:
        _struct_src_cache[key] = (out, now)
        if len(_struct_src_cache) > STRUCT_SRC_CACHE_N:   # ⚠do not create a dict without expiry
            old = sorted(_struct_src_cache.items(), key=lambda kv: kv[1][1])
            for k, _v in old[:len(_struct_src_cache) - STRUCT_SRC_CACHE_N]:
                _struct_src_cache.pop(k, None)
    return out


# ── source <-> test pairing endpoint ─────────────────────────────────────────────
# Matcher, file list and constants: sidereus/structure_pairing.py. The result cache is read only here, so it stays here.
_struct_pair_cache = {}           # (root, rel, list sig) -> (result, last used)


def structure_pair(path=None, file=""):
    """Body of `GET /api/structure/pair?path=…&file=…` — tests for a source file, or sources for a test file."""
    root = _struct_src_root(path)
    if not root:
        return {"ok": False, "msg": "Only projects shown on screen can be opened."}
    rel = _struct_src_rel(file)
    if not rel:
        return {"ok": False, "msg": "This path cannot be read."}
    files = _struct_pair_files(root)
    key = (root, rel, len(files), hash(tuple(files)))
    now = time.time()
    with _struct_lock:
        hit = _struct_pair_cache.get(key)
        if hit:
            _struct_pair_cache[key] = (hit[0], now)
    if hit:
        return dict(hit[0], warm=True)

    def read(f):
        fp = os.path.realpath(os.path.join(root, f))
        if not fp.startswith(root + os.sep):
            return ""
        try:
            if os.path.getsize(fp) > STRUCT_MAX_BYTES:
                return ""
            with open(fp, "rb") as fo:
                return fo.read().decode("utf-8", "replace")
        except OSError:
            return ""
    is_test, pairs = _struct_pair_match(rel, files, read)
    out = {"ok": True, "path": root, "file": rel, "isTest": is_test, "pairs": pairs,
           "exists": rel in files, "warm": False}
    with _struct_lock:
        _struct_pair_cache[key] = (out, now)
        if len(_struct_pair_cache) > STRUCT_SRC_CACHE_N:   # ⚠do not create a dict without expiry
            old = sorted(_struct_pair_cache.items(), key=lambda kv: kv[1][1])
            for k, _v in old[:len(_struct_pair_cache) - STRUCT_SRC_CACHE_N]:
                _struct_pair_cache.pop(k, None)
    return out


# ── idle warm-up ─────────────────────────────────────────────────────────────────
# ★With only the disk cache, «a project opened for the first time» is still cold. The server already knows sessions' `cwd`·`repos`
#   (`sessions[].repos` in `/api/state`) — their union is the warm-up target.
# ⚠Do not run in parallel — **one at a time**. Eating CPU while the user works is worse.
# ⚠From «requests» in "only when there were no recent requests", **exclude automatic polling** (`_STRUCT_POLL`). The screen hits
#   `/api/state` every 2.5s, so including it means idle **never comes** while a tab is open.
# ⚠Follow the existing background thread convention — one daemon thread from `main()`, swallow exceptions and sleep.
STRUCT_WARM_BOOT_S = 10        # hands off for this long after startup (the page's first load comes first; the idle check below still yields to it)
# ★2026-09-25: 60 s left the full post-restart rescan (~2.7 s per project when struct-cache/ is invalidated) to the user's first click.
STRUCT_WARM_IDLE_S = 30        # skip if there was a «human-initiated» request within this time
STRUCT_WARM_TICK_S = 10        # attempt period per cell
STRUCT_WARM_CYCLE_S = 900      # until the same target is looked at again — if unchanged the cache returns immediately
STRUCT_PRUNE_EVERY_S = 3600    # disk cleanup period (only inside the warm-up thread)
# ⚠`/api/quota/burn`: saver.py hits it on every prompt, and the page only fetches it from the poll (`burnTick`, 30s throttle).
_STRUCT_POLL = ("/api/state", "/api/live", "/api/hookstate", "/api/quota/burn")    # timer/hook polls = do not break idle
_struct_act = [0.0]            # last «human» request time
_struct_warm_seen = {}         # (realpath, tests) -> last warm-up time
_struct_prune_at = [0.0]


def _struct_warm_targets():
    """Warm-up targets = union of sessions' `cwd` + `repos` (+ Sidereus itself). ⚠Not recomputed —
    it is the value `_allowed_cwds()` already holds with a 5s cache."""
    cands = [CODE_DIR] if config.IS_CLONE else []   # installed package: not a repo to warm
    try:
        for cwd, row in _allowed_cwds().items():
            cands.append(cwd)
            cands.extend(row.get("repos") or [])
    except Exception as e:
        warn_once("struct-warm", "structure warm-up targets failed ({err}) — warming Sidereus only",
                  soft=True, vars={"err": f"{type(e).__name__}: {e}"})
    out, seen = [], set()
    for p in cands:
        if not p:
            continue
        try:
            rp = os.path.realpath(p)
        except Exception:
            continue
        if rp in seen or not os.path.isdir(rp):
            continue
        seen.add(rp)
        out.append(rp)
    return out


def _struct_warm_loop():
    t0 = time.time()
    while True:
        time.sleep(STRUCT_WARM_TICK_S)
        try:
            now = time.time()
            if now - t0 < STRUCT_WARM_BOOT_S:
                continue
            if now - _struct_act[0] < STRUCT_WARM_IDLE_S:
                if boot_queue.others_done("struct_warm"):
                    boot_queue.done("struct_warm")   # ⚠user active and last in line: let the boot queue drain
                continue
            tgt = None
            # ★2026-09-25: the «Include tests» toggle (tests=True) was never warmed — its first request cost 2.0 s vs 0.03 s.
            #   ⇒ Warm both variants, still one cell per tick.
            for root in _struct_warm_targets():
                for tests in (0, 1, 2):    # 2 = «Tests» only filter (2026-09-25), its own server variant
                    if now - _struct_warm_seen.get((root, tests), 0.0) >= STRUCT_WARM_CYCLE_S:
                        tgt = (root, tests)
                        break
                if tgt:
                    break
            if tgt is None:                # finished a full round — cleanup happens only here
                boot_queue.done("struct_warm")     # no target: nothing to queue for
                if now - _struct_prune_at[0] >= STRUCT_PRUNE_EVERY_S:
                    _struct_prune_at[0] = now
                    _struct_disk_prune()
                continue
            _struct_warm_seen[tgt] = now
            # ★Disk only: warm results in the memory cache held ~55 MB live (bound ~126 MB, one repo pair 25.0 + 20.8 MB)
            #   and warm-loop order, not the screen, decided which cells stayed. A later screen request is a disk hit.
            with boot_queue.gate("struct_warm"):   # ⚠first cell waits its boot turn (traps/server.md)
                structure(*tgt, mem=False)     # ⚠one cell only — idle is rechecked on the next tick
        except Exception as e:
            warn_once("struct-warm", "Structure warm-up failed ({err})", vars={"err": type(e).__name__}, soft=True)
