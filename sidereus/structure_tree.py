"""«Source» popup: file tree + one whole file of an allowed project.
`GET /api/structure/tree?path=` and `GET /api/structure/file?path=&file=&line=`.
★2026-09-28 (source viewer): a file opens only if it is in the listing AND its realpath stays under the root.
⚠CODE_DIR (~/.mailbox-mcp) holds bus.jsonl and friends — *.jsonl is refused everywhere (conversation data, rule 1).
⚠Anything under realpath(~/.claude) is refused (transcripts, credentials); secret-looking names are locked."""
import fnmatch
import os
import stat
import subprocess
import threading
import time
from sidereus.config import claude_home
from sidereus.claude_roots import accounts as claude_accounts
from sidereus.gitinfo import _git_slot, git_argv, git_env
from sidereus.redact import redact
from sidereus.structure_scan import STRUCT_SKIP
from sidereus.structure import _struct_src_root

TREE_MAX = 20000               # listing entries cap (git and walk)
TREE_WALK_S = 1.0              # non-git walk deadline
TREE_GIT_TIMEOUT = 5
TREE_TTL = 15.0                # untracked files do not touch .git/index — re-list at least this often
FILE_MAX_BYTES = 512 * 1024
FILE_MAX_LINES = 20000
BIN_PROBE = 8192
# Inline Markdown images (R3): fixed mime per extension, never sniffed from the bytes.
IMG_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
             ".webp": "image/webp", ".svg": "image/svg+xml"}
IMG_MAX_BYTES = 5 * 1024 * 1024
SECRET_PATS = (".env*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore", "*.kdbx",
               "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*", "*credential*", "*secret*",
               ".npmrc", ".pypirc", ".netrc", ".git-credentials", "*.tfstate*", "kubeconfig", "config.local.json")
_tree_cache = {}               # root -> (sig, time, (entries, set of rels, git, truncated))
_tree_lock = threading.Lock()
TREE_CACHE_N = 16
TREE_ST_TTL = 5.0              # work-tree edits do not touch .git/index — re-run status at least this often
_st_cache = {}                 # root -> (sig, time, (status map or None, untracked dir prefixes))


def _claude_dirs():
    """realpath of ~/.claude by account home and by $HOME (either may be the real one)."""
    out = set()
    try:
        import pwd
        out.add(os.path.realpath(os.path.join(pwd.getpwuid(os.getuid()).pw_dir, ".claude")))
    except Exception:
        out.add(os.path.realpath(os.path.expanduser("~/.claude")))
    out.add(os.path.realpath(os.path.expanduser("~/.claude")))
    out.add(os.path.realpath(claude_home()))      # $CLAUDE_CONFIG_DIR holds the transcripts when set
    out.update(os.path.realpath(r["dir"]) for r in claude_accounts())   # every account dir (incl. shared-history profiles) is refused too
    return out


def _under(p, base):
    return p == base or p.startswith(base.rstrip(os.sep) + os.sep)


def _claude_hit(p):
    """True if p is inside ~/.claude or contains it."""
    return any(_under(p, c) or _under(c, p) for c in _claude_dirs())


def _is_secret(name):
    n = (name or "").lower()
    return any(fnmatch.fnmatchcase(n, pat) for pat in SECRET_PATS)


def _rel_ok(rel):
    """Normalized relative path or "" (abs, `..`, NUL, backslash, *.jsonl)."""
    if not isinstance(rel, str) or not rel or "\x00" in rel or "\\" in rel:
        return ""
    if rel.startswith("/") or os.path.isabs(rel):
        return ""
    parts = []
    for p in rel.split("/"):
        if p in ("", "."):
            continue
        if p == "..":
            return ""
        parts.append(p)
    rel = "/".join(parts)
    return "" if (not rel or rel.lower().endswith(".jsonl")) else rel


def _tree_git_ls(root):
    """Tracked + untracked-not-ignored paths, or None when git fails."""
    try:
        with _git_slot():
            r = subprocess.run(git_argv(root, ["ls-files", "-z", "--cached", "--others", "--exclude-standard"]),
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               timeout=TREE_GIT_TIMEOUT, env=git_env())
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    out = []
    for raw in r.stdout.split(b"\x00"):
        try:
            out.append(raw.decode("utf-8"))
        except UnicodeDecodeError:
            continue           # undecodable name: cannot be requested back safely
    return out


def _tree_walk(root):
    """Non-git listing: skip STRUCT_SKIP and dot-dirs, no link following, capped -> (rels, truncated)."""
    out, t0 = [], time.monotonic()
    for d, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(x for x in dirs if x not in STRUCT_SKIP and not x.startswith("."))
        rd = os.path.relpath(d, root)
        for f in sorted(files):
            out.append(f if rd == "." else rd.replace(os.sep, "/") + "/" + f)
            if len(out) >= TREE_MAX:
                return out, True
        if time.monotonic() - t0 > TREE_WALK_S:
            return out, True
    return out, False


def _tree_sig(root):
    g = os.path.join(root, ".git")
    sig = []
    for p in (os.path.join(g, "index"), os.path.join(g, "HEAD")):
        try:
            st = os.stat(p)
            sig.append((st.st_mtime_ns, st.st_size))
        except OSError:
            sig.append(None)
    return tuple(sig)


def _tree_build(root):
    """(entries, rel set, git, truncated) — entries are {p, sz[, sec]} sorted by path."""
    rels, git, trunc = None, False, False
    if os.path.exists(os.path.join(root, ".git")):
        rels = _tree_git_ls(root)
        git = rels is not None
    if rels is None:
        rels, trunc = _tree_walk(root)
    ents, keep = [], set()
    for r in rels:
        rel = _rel_ok(r)
        if not rel or rel in keep:
            continue
        try:
            st = os.lstat(os.path.join(root, rel))
        except OSError:
            continue           # tracked but deleted
        if not (stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode)):
            continue           # submodule dir etc.
        e = {"p": rel, "sz": int(st.st_size)}
        if _is_secret(rel.rsplit("/", 1)[-1]):
            e["sec"] = 1
        ents.append(e)
        keep.add(rel)
        if len(ents) >= TREE_MAX:
            trunc = True
            break
    ents.sort(key=lambda e: e["p"])
    return ents, keep, git, trunc


def _tree_get(root):
    sig, now = _tree_sig(root), time.time()
    with _tree_lock:
        hit = _tree_cache.get(root)
    if hit and hit[0] == sig and now - hit[1] < TREE_TTL:
        return hit[2], True
    val = _tree_build(root)
    with _tree_lock:
        _tree_cache[root] = (sig, now, val)
        if len(_tree_cache) > TREE_CACHE_N:        # ⚠bounded: drop the oldest
            old = min(_tree_cache.items(), key=lambda kv: kv[1][1])[0]
            _tree_cache.pop(old, None)
    return val, False


def _st_code(xy):
    """Porcelain v1 XY -> A/M/D/R (D wins: the file is gone from the work tree or the index)."""
    x, y = xy[0], xy[1]
    if xy == "??":
        return "A"
    if "D" in (x, y):
        return "D"
    if x in "RC":
        return "R"
    return "A" if x == "A" else "M"


def _tree_git_status(root):
    """{rel: A|M|D|R} and untracked dir prefixes from one `git status`, or None when git fails."""
    try:
        with _git_slot():
            r = subprocess.run(git_argv(root, ["status", "--porcelain=v1", "-z", "--untracked-files=normal"]),
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               timeout=TREE_GIT_TIMEOUT, env=git_env())
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    out, dirs, parts, i = {}, [], r.stdout.split(b"\x00"), 0
    while i < len(parts):
        raw, i = parts[i], i + 1
        if len(raw) < 4 or raw[2:3] != b" ":
            continue
        xy = raw[:2].decode("ascii", "replace")
        if xy[0] in "RC":
            i += 1             # -z: "XY new\0old\0" — the old path is not shown
        try:
            rel = raw[3:].decode("utf-8")
        except UnicodeDecodeError:
            continue
        if xy == "??" and rel.endswith("/"):
            dirs.append(rel)   # normal mode collapses an untracked dir to "dir/"
            continue
        rel = _rel_ok(rel)
        if rel:
            out[rel] = _st_code(xy)
    return out, tuple(dirs)


def _st_get(root):
    """Cached git status for a git root: (map, dirs) or None; same signature as the listing + TREE_ST_TTL."""
    sig, now = _tree_sig(root), time.time()
    with _tree_lock:
        hit = _st_cache.get(root)
    if hit and hit[0] == sig and now - hit[1] < TREE_ST_TTL:
        return hit[2]
    val = _tree_git_status(root)
    with _tree_lock:
        _st_cache[root] = (sig, now, val)
        if len(_st_cache) > TREE_CACHE_N:
            old = min(_st_cache.items(), key=lambda kv: kv[1][1])[0]
            _st_cache.pop(old, None)
    return val


def _with_st(ents, keep, st, trunc):
    """Listing copy with per-file st, plus rows for deleted files the listing skipped -> (files, stn, trunc)."""
    smap, dirs = st
    files, stn = [], {"A": 0, "M": 0, "D": 0}
    for e in ents:
        c = smap.get(e["p"]) or ("A" if dirs and e["p"].startswith(dirs) else "")
        if c:
            e = dict(e, st=c)
            stn["A" if c == "R" else c] += 1
        files.append(e)
    for rel, c in smap.items():
        if c != "D" or rel in keep:
            continue
        if len(files) >= TREE_MAX:
            trunc = True
            break
        e = {"p": rel, "sz": 0, "st": "D"}     # ⚠not in keep: never openable
        if _is_secret(rel.rsplit("/", 1)[-1]):
            e["sec"] = 1
        files.append(e)
        stn["D"] += 1
    files.sort(key=lambda e: e["p"])
    return files, stn, trunc


def _root_or_err(path):
    root = _struct_src_root(path)
    if not root:
        return "", {"ok": False, "msg": "Only projects shown on screen can be opened."}
    if _claude_hit(root):
        return "", {"ok": False, "msg": "This location cannot be opened."}
    return root, None


def structure_tree(path=None):
    """Body of GET /api/structure/tree — file list (paths and sizes only)."""
    root, err = _root_or_err(path)
    if err:
        return err
    (ents, keep, git, trunc), warm = _tree_get(root)
    st = _st_get(root) if git else None
    out = {"ok": True, "path": root, "git": git, "files": ents, "n": len(ents), "truncated": trunc, "warm": warm}
    if st is not None:
        out["files"], out["stn"], out["truncated"] = _with_st(ents, keep, st, trunc)
        out["n"] = len(out["files"])
    return out


def _decode(data):
    for enc in ("utf-8", "cp949"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace"), "replace"


def structure_file(path=None, file="", line=1):
    """Body of GET /api/structure/file — one whole file (capped), secrets masked."""
    root, err = _root_or_err(path)
    if err:
        return err
    rel = _rel_ok(file)
    if not rel:
        return {"ok": False, "msg": "This path cannot be read."}
    try:
        line = max(1, int(line or 1))
    except (TypeError, ValueError):
        line = 1
    (_e, keep, git, _t), _w = _tree_get(root)
    st = _st_get(root) if git else None
    if st is not None and st[0].get(rel) == "D":
        return {"ok": False, "msg": "This file was deleted.", "gone": True}
    if rel not in keep:
        return {"ok": False, "msg": "This file is not in the list."}
    fp = os.path.realpath(os.path.join(root, rel))
    if not _under(fp, root) or fp == root or _claude_hit(fp) or fp.lower().endswith(".jsonl"):
        return {"ok": False, "msg": "This path cannot be read."}
    if _is_secret(rel.rsplit("/", 1)[-1]) or _is_secret(os.path.basename(fp)):
        return {"ok": False, "locked": True, "msg": "This file cannot be opened."}
    try:
        if not os.path.isfile(fp):
            return {"ok": False, "msg": "This path cannot be read."}
        size = os.path.getsize(fp)
        with open(fp, "rb") as f:
            data = f.read(FILE_MAX_BYTES + 1)
    except OSError:
        return {"ok": False, "msg": "Could not read the file."}
    if b"\x00" in data[:BIN_PROBE]:
        return {"ok": False, "bin": True, "bytes": size, "msg": "This is a binary file."}
    if b"PRIVATE KEY-----" in data:
        return {"ok": False, "locked": True, "msg": "This file cannot be opened."}
    trunc = size > FILE_MAX_BYTES or len(data) > FILE_MAX_BYTES
    if trunc:
        data = data[:FILE_MAX_BYTES]
        cut = data.rfind(b"\n")
        data = data[:cut] if cut > 0 else data    # ⚠cut on a line end so utf-8/cp949 never sees half a char
    body, enc = _decode(data)
    lines = body.split("\n")
    if len(lines) > FILE_MAX_LINES:
        lines, trunc = lines[:FILE_MAX_LINES], True
    red = [redact(x) for x in lines]
    masked = sum(1 for a, b in zip(lines, red) if a != b)
    note = "" if enc != "replace" else "Characters not readable as UTF-8/CP949 show as replacement characters"
    return {"ok": True, "path": root, "file": rel, "line": min(line, len(red)), "n": len(red),
            "code": "\n".join(red), "truncated": trunc, "bytes": size, "enc": enc,
            "masked": masked, "note": note}


def _img_ext(p):
    return os.path.splitext(p)[1].lower()


def structure_img(path=None, file=""):
    """Body of GET /api/structure/img — (bytes, mime) of one listed image, or an error dict (R2/R3)."""
    root, err = _root_or_err(path)
    if err:
        return err
    rel = _rel_ok(file)
    if not rel:
        return {"ok": False, "msg": "This path cannot be read."}
    (_e, keep, _g, _t), _w = _tree_get(root)
    if rel not in keep:
        return {"ok": False, "msg": "This file is not in the list."}
    fp = os.path.realpath(os.path.join(root, rel))
    if not _under(fp, root) or fp == root or _claude_hit(fp):
        return {"ok": False, "msg": "This path cannot be read."}
    if _is_secret(rel.rsplit("/", 1)[-1]) or _is_secret(os.path.basename(fp)):
        return {"ok": False, "locked": True, "msg": "This file cannot be opened."}
    # ⚠Extension checked on the realpath too: a.png symlinked to a text/secret file must not be served.
    if _img_ext(rel) not in IMG_TYPES or _img_ext(fp) not in IMG_TYPES:
        return {"ok": False, "msg": "Not an image."}
    try:
        if not os.path.isfile(fp):
            return {"ok": False, "msg": "This path cannot be read."}
        if os.path.getsize(fp) > IMG_MAX_BYTES:
            return {"ok": False, "big": True, "msg": "Image too large."}
        with open(fp, "rb") as f:
            data = f.read(IMG_MAX_BYTES + 1)
    except OSError:
        return {"ok": False, "msg": "Could not read the file."}
    if len(data) > IMG_MAX_BYTES:                 # ⚠grew between stat and read
        return {"ok": False, "big": True, "msg": "Image too large."}
    return data, IMG_TYPES[_img_ext(fp)]
