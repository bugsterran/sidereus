"""Structure treemap time-series sources: git history, backup tars, .bak files and the current tree."""
import glob
import os
import re
import subprocess
from subprocess import SubprocessError     # bound at import: tests swap the `subprocess` module for a fake
import tarfile
import threading
from datetime import datetime
from sidereus.config import CODE_DIR, DATA_DIR
from sidereus.warn import warn_once
from sidereus.gitinfo import _git_slot, git_argv, git_env
from sidereus.structure_scan import (STRUCT_EXTS, STRUCT_RULES_VER, STRUCT_SKIP, STRUCT_MAX_FILES,
    STRUCT_MAX_BYTES, STRUCT_SNAPS, STRUCT_SNAPS_LOCAL, STRUCT_GIT_TIMEOUT, _struct_lock, _struct_blob_cache,
    STRUCT_BCACHE_N, _struct_wanted, _struct_build, _struct_tmode)
from sidereus.structure_cache import (_struct_disk_read, _struct_disk_write, _struct_enc_build, _struct_dec_build,
    _struct_fcache_load, _struct_fcache_save)


# ── time-series sources ───────────────────────────────────────────────────────
def _struct_git(root):
    """Pick STRUCT_SNAPS points evenly from `git log --first-parent`. [(ts, sha)] oldest first."""
    if not os.path.isdir(os.path.join(root, ".git")):
        return []
    try:
        with _git_slot():
            r = subprocess.run(git_argv(root, ["log", "--format=%H %ct", "--first-parent", "-n", "400"]),
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               timeout=STRUCT_GIT_TIMEOUT, env=git_env())
    except (OSError, SubprocessError):
        return []                        # git missing/timeout/slot busy: the working-tree point still shows
    rows = []
    for ln in r.stdout.decode("utf-8", "replace").splitlines():
        p = ln.split()
        if len(p) == 2 and p[1].isdigit():
            rows.append((int(p[1]), p[0]))
    rows.sort()
    if len(rows) <= STRUCT_SNAPS:
        return rows
    n = len(rows)
    idx = sorted(set(int(round(i * (n - 1) / (STRUCT_SNAPS - 1))) for i in range(STRUCT_SNAPS)))
    return [rows[i] for i in idx]


def _struct_git_tree(root, sha, tests=False):
    """Read and extract the target files of that commit.
    ★Get (path, blob sha) via `git ls-tree -r` and pull them in one go with `git cat-file --batch`
    (2026-09-22). ⚠Do not use `git archive` — one repo-A snapshot is 78MB, so 10 would
    stream 780MB (measured). The expensive part is parsing, and `_struct_build`'s content-hash
    cache filters that — files unchanged between commits are not parsed twice.
    ⚠Read-only commands only — `checkout`·`stash`·`reset` break the user's working tree."""
    # ⚠Extraction results depend on the classification rules and `tests` — without them in the key old results come back as-is.
    key = ("git", root, sha, STRUCT_RULES_VER, _struct_tmode(tests))
    with _struct_lock:
        if key in _struct_blob_cache:
            return _struct_blob_cache[key]
    # ★Commits are immutable — kept on disk they stay valid forever, even across restarts (2026-09-22).
    dk = "git|%s|%s|%d" % (root, sha, _struct_tmode(tests))
    got = _struct_dec_build(_struct_disk_read("blob", dk))
    if got is not None:
        with _struct_lock:
            _struct_blob_cache[key] = got
        return got
    try:
        with _git_slot():
            r = subprocess.run(git_argv(root, ["ls-tree", "-r", "-z", sha]),
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               timeout=STRUCT_GIT_TIMEOUT, env=git_env())
        want = []                          # [(relative path, blob sha)]
        for rec in r.stdout.decode("utf-8", "replace").split("\0"):
            if not rec:
                continue
            meta, _sep, path = rec.partition("\t")
            bits = meta.split()
            if len(bits) < 3 or bits[1] != "blob" or not _struct_wanted(path):
                continue
            want.append((path, bits[2]))
        items = []
        if want:
            with _git_slot():              # ⚠slot held until cat-file exits (the process is alive until then)
                pr = subprocess.Popen(git_argv(root, ["cat-file", "--batch"]),
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, env=git_env())
                # ⚠Feed stdin from a thread and kill on a deadline: writing all shas before reading deadlocks
                #   once git fills its stdout pipe (measured 18k shas / 738KB hangs forever while holding the slot).
                feed = ("\n".join(b for _p, b in want) + "\n").encode()

                def _feed():
                    try:
                        pr.stdin.write(feed)
                        pr.stdin.close()
                    except (OSError, ValueError):
                        pass            # git exited or was killed on the deadline; the reader sees EOF
                fed = threading.Thread(target=_feed, daemon=True)
                killed = []
                timer = threading.Timer(STRUCT_GIT_TIMEOUT * 3, lambda: (killed.append(1), pr.kill()))
                timer.daemon = True
                fed.start()
                timer.start()
                try:
                    for path, _b in want:
                        hdr = pr.stdout.readline().decode("utf-8", "replace").split()
                        if len(hdr) < 3 or not hdr[2].isdigit():
                            break          # `<sha> missing` — stop here (sync is broken)
                        data = pr.stdout.read(int(hdr[2]))
                        pr.stdout.read(1)  # newline after the body
                        if len(data) <= STRUCT_MAX_BYTES:
                            items.append((path, data))
                finally:
                    timer.cancel()
                    try:
                        pr.stdout.close()
                    except OSError:
                        pass            # teardown best-effort
                    try:
                        pr.wait(timeout=STRUCT_GIT_TIMEOUT)
                    except (OSError, SubprocessError):
                        pr.kill()
                        try:
                            pr.wait(timeout=5)
                        except (OSError, SubprocessError):
                            pass        # killed; do not block the slot on reaping
                    fed.join(timeout=5)
                if killed:
                    raise subprocess.TimeoutExpired("git cat-file --batch", STRUCT_GIT_TIMEOUT * 3)
        got = _struct_build(items, tests)
    except (OSError, SubprocessError):
        got = None
    except Exception as e:
        warn_once("struct-git", "Could not build a git structure snapshot ({err})", vars={"err": type(e).__name__}, soft=True)
        got = None
    if got is None:
        return None                        # ⚠failure (slot wait, deadline) is not cached — the next call retries
    if got:
        _struct_disk_write("blob", dk, _struct_enc_build(got))
    with _struct_lock:
        if len(_struct_blob_cache) > STRUCT_BCACHE_N:   # ⚠do not create a dict without expiry
            _struct_blob_cache.clear()
        _struct_blob_cache[key] = got
    return got


_STRUCT_TS = re.compile(r"mailbox-(\d{8})-(\d{6})\.tar\.gz$")


# Date part of `chat_server.py.bak-20260902-071303`. ⚠There are also **label-style** ones like `bak-rooms-073308` —
#   they have no date, so use the file mtime (otherwise half of three weeks is discarded).
_STRUCT_BAK = re.compile(r"^(?P<orig>.+?)\.bak-(?:(?P<d>\d{8})-)?(?P<t>\d{6})$")


def _struct_spread(rows, n):
    """Thin [(ts, …)] to n **evenly along the time axis** (oldest and newest always included).
    ★Farthest-point sampling — repeatedly add the one «farthest» from the already chosen times.
    ⚠Do not cut by count (`rows[-n:]`) — Sidereus's 10 tars are all from 70 min of the same day, so
    three weeks of `old-baks` are missed and churn becomes 0 for 356/365 (measured 2026-09-22).
    ⚠Do not use «closest to evenly spaced target times» either — targets in empty spans collapse onto one point
    and duplicate, and filling those gaps from the front ends up picking only the dense spans."""
    rows = sorted(rows)
    if len(rows) <= n or n < 2:
        return rows
    idx = {0, len(rows) - 1}
    while len(idx) < n:
        best, bestd = None, -1.0
        for j in range(len(rows)):
            if j in idx:
                continue
            d = min(abs(rows[j][0] - rows[k][0]) for k in idx)
            if d > bestd:
                best, bestd = j, d
        if best is None:
            break
        idx.add(best)
    return [rows[j] for j in sorted(idx)]


def _struct_backups(root):
    """Past-point candidates for projects without git. [(ts, kind, path, original file name)] oldest first.
    ★Merges two sources (2026-09-22): `backup/*.tar.gz` (bundles) and `backup/old-baks/*.bak-*` (single plain
    file). For Sidereus, 10 tars (today's 70 min) + 37 old-baks (9/02~) = three weeks."""
    out = []
    # ⚠ backup.sh writes the viewer's own backups to DATA_DIR/backup (a git-cloned CODE_DIR must stay clean).
    bdir = os.path.join(DATA_DIR if os.path.realpath(root) == os.path.realpath(CODE_DIR) else root, "backup")
    for p in glob.glob(os.path.join(bdir, "mailbox-*.tar.gz")):
        m = _STRUCT_TS.search(p)
        if not m:
            continue
        try:
            out.append((datetime.strptime(m.group(1) + m.group(2),
                                          "%Y%m%d%H%M%S").timestamp(), "tar", p, ""))
        except ValueError:
            continue
    for p in glob.glob(os.path.join(bdir, "old-baks", "*.bak-*")):
        m = _STRUCT_BAK.match(os.path.basename(p))
        if not m or not _struct_wanted(m.group("orig")):
            continue
        ts = None
        if m.group("d"):
            try:
                ts = datetime.strptime(m.group("d") + m.group("t"),
                                       "%Y%m%d%H%M%S").timestamp()
            except ValueError:
                ts = None
        if ts is None:
            try:
                ts = os.path.getmtime(p)   # label-style (`bak-rooms-073308`) — no date in the name
            except OSError:
                continue
        out.append((ts, "bak", p, m.group("orig")))
    return _struct_spread(out, STRUCT_SNAPS_LOCAL)


def _struct_plain(path, orig, tests=False):
    """One plain backup file from `old-baks`. ⚠It is **not the whole project** at that point — the caller
    sets `partial` (otherwise the graph jumps in steps by file count)."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = ("bak", path, st.st_mtime, st.st_size, STRUCT_RULES_VER, _struct_tmode(tests))
    with _struct_lock:
        if key in _struct_blob_cache:
            return _struct_blob_cache[key]
    dk = "bak|%s|%s|%s|%d" % (path, st.st_mtime, st.st_size, _struct_tmode(tests))
    got = _struct_dec_build(_struct_disk_read("blob", dk))
    if got is not None:
        with _struct_lock:
            _struct_blob_cache[key] = got
        return got
    try:
        if st.st_size <= STRUCT_MAX_BYTES:
            with open(path, "rb") as f:
                got = _struct_build([(orig, f.read())], tests)
    except OSError:
        return None                        # ⚠errors are not cached (a size-cap None is — the file won't shrink)
    except Exception as e:                 # unexpected: the backup point would silently drop off the graph
        warn_once("struct-bak", "Could not read a backup file for the structure snapshot ({err})",
                  vars={"err": type(e).__name__}, soft=True)
        return None
    if got:
        _struct_disk_write("blob", dk, _struct_enc_build(got))
    with _struct_lock:
        if len(_struct_blob_cache) > STRUCT_BCACHE_N:
            _struct_blob_cache.clear()
        _struct_blob_cache[key] = got
    return got


def _struct_tar(path, tests=False):
    """Extract **only top-level files** from a backup tar — `src/...` contains another repository (`~/projects/mailbox-mcp`)
    (the second `-C` in `backup.sh`), so mixing it in makes the structure false."""
    key = ("tar", path)
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = ("tar", path, st.st_mtime, st.st_size, STRUCT_RULES_VER, _struct_tmode(tests))
    with _struct_lock:
        if key in _struct_blob_cache:
            return _struct_blob_cache[key]
    dk = "tar|%s|%s|%s|%d" % (path, st.st_mtime, st.st_size, _struct_tmode(tests))
    got = _struct_dec_build(_struct_disk_read("blob", dk))
    if got is not None:
        with _struct_lock:
            _struct_blob_cache[key] = got
        return got
    try:
        items = []
        with tarfile.open(path, "r:gz") as tf:
            for mem in tf.getmembers():
                if not mem.isfile() or "/" in mem.name or not _struct_wanted(mem.name):
                    continue
                if mem.size > STRUCT_MAX_BYTES:
                    continue
                f = tf.extractfile(mem)
                if f:
                    items.append((mem.name, f.read()))
        got = _struct_build(items, tests)
    except (OSError, EOFError, tarfile.TarError):
        return None                        # ⚠errors (tar mid-write, bad gzip) are not cached — the next call retries
    except Exception as e:
        warn_once("struct-tar", "Could not build a backup structure snapshot ({err})", vars={"err": type(e).__name__},
                  soft=True)
        return None
    if got:
        _struct_disk_write("blob", dk, _struct_enc_build(got))
    with _struct_lock:
        _struct_blob_cache[key] = got
    return got


def _struct_now(root, tests=False):
    """Current working tree.
    ★Load the disk file cache first (2026-09-22) — so in a new process, when **only one file** changed,
    the other thousands are not re-parsed. Past snapshots are handled by the blob cache."""
    _struct_fcache_load(root, tests)
    items = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in STRUCT_SKIP and not d.startswith(".")]
        for fn in fns:
            if not fn.endswith(STRUCT_EXTS):
                continue
            p = os.path.join(dp, fn)
            if not _struct_wanted(os.path.relpath(p, root)):   # ⚠vendor exclusion must be the same for past and present
                continue
            try:
                if os.path.islink(p) or os.path.getsize(p) > STRUCT_MAX_BYTES:
                    continue
                with open(p, "rb") as f:
                    items.append((os.path.relpath(p, root), f.read()))
            except OSError:
                continue
            if len(items) > STRUCT_MAX_FILES * 2:
                break
        # ⚠The inner break only left this dir; stop the walk too. _struct_build still sets `truncated` (items > cap).
        if len(items) > STRUCT_MAX_FILES * 2:
            break
    fkeys = []
    got = _struct_build(items, tests, fkeys)
    _struct_fcache_save(root, tests, fkeys)
    return got
