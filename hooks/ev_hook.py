#!/usr/bin/python3
"""Claude Code Bash hook: records test/build/check/lint runs as harness evidence (one `evidence.jsonl` row each).
`gh run watch|view <id> --exit-status` writes a kind "ci" row (rc · repo · head only).

Events: PreToolUse (start time) · PostToolUse (rc 0) · PostToolUseFailure (rc from «Exit code N»), matcher "Bash".
Matched commands only (anchored allow-list, or a pipeline `gate` string of the repo); everything else exits at once.
⚠Metadata only: the row never holds the command text, stdout/stderr or the error text — rc comes from a regex match.
⚠check.sh is skipped: it writes its own row. Interrupted or background runs write nothing.
Fail-open: prints nothing, always exits 0. Stdlib only, Python 3.9.
"""
import json
import os
import re
import subprocess
import sys
import time

try:
    import fcntl
except ImportError:   # Windows: msvcrt sidecar lock instead (_win_append); same code as scripts/evidence_rec.py
    fcntl = None
try:
    import msvcrt
except ImportError:
    msvcrt = None
WIN_LOCK_TRIES, WIN_LOCK_STEP = 10, 0.1   # msvcrt lock wait: 1 s at most, then no row (ev_hook timeout is 3 s)

# Same derivation as sidereus/config.py DATA_DIR; EV_FILE honours SIDEREUS_EVIDENCE like scripts/check.sh.
DATA_DIR = os.path.expanduser(os.environ.get("MAILBOX_DIR") or "~/.mailbox-mcp")
EV_FILE = os.environ.get("SIDEREUS_EVIDENCE") or os.path.join(DATA_DIR, "evidence.jsonl")
START_DIR = os.path.join(DATA_DIR, "evstart")
EV_CAP = 400    # same as scripts/evidence_rec.py
EV_KEEP = 200
START_TTL = 3600
GIT_TIMEOUT = 0.4
NOW = time.time   # patched in tests

_CD = re.compile(r"""^\s*cd\s+(?:"([^"]+)"|'([^']+)'|([^\s"'&|;]+))\s*&&\s*""")
_ARGS = r"(?:\s+[^|;]*)?$"
# (regex on the command after an optional `cd X &&`, kind or {sub-command: kind}); anchored at the start.
ALLOW = (
    (re.compile(r"^(?:\./gradlew|gradlew|gradle)\s+(test|build|check)\b" + _ARGS), None),
    (re.compile(r"^mvnw?\s+(test|verify)\b" + _ARGS), {"verify": "check"}),
    (re.compile(r"^(?:npm|pnpm|yarn)\s+(?:run\s+)?(test|build|lint)\b" + _ARGS), None),
    (re.compile(r"^(?:pytest|python3?\s+-m\s+pytest|/usr/bin/python3\s+-m\s+pytest)()\b" + _ARGS), "test"),
    (re.compile(r"^go\s+(test)\b" + _ARGS), None),
    (re.compile(r"^cargo\s+(test|build)\b" + _ARGS), None),
)
_KIND_WORD = re.compile(r"\b(test|build|check|lint)\b")
_SKIP_ARG = re.compile(r"(?:^|\s)(?:--watch\S*|--continuous|-t)(?=\s|$)")
_EXIT = re.compile(r"^Exit code (\d+)")
_TUID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_PLNAME = re.compile(r"^[a-z0-9-]{1,40}\.json$")
# ⚠Without --exit-status gh exits 0 on a red run; -R/--repo names another repo than the cwd's, so its head is meaningless.
_CI = re.compile(r"^gh\s+run\s+(?:watch|view)\b" + _ARGS)
_CI_REPO = re.compile(r"(?:^|\s)(?:-R\S*|--repo(?:=\S*)?)(?=\s|$)")
_CI_EXIT = re.compile(r"(?:^|\s)--exit-status(?=\s|$)")
# ⚠No run id = gh prompts for one, and without a TTY exits 1: a false red. The -i/--interval value is not an id.
_CI_ID = re.compile(r"(?:^|\s)\d+(?=\s|$)")
_CI_IVL = re.compile(r"(?:^|\s)(?:-i|--interval)(?:\s+|=)\S+")


def _norm(s):
    return " ".join(s.split())


def split_cd(cmd):
    """(cd target or None, rest of the command)."""
    m = _CD.match(cmd)
    if not m:
        return None, cmd.strip()
    return next(g for g in m.groups() if g is not None), cmd[m.end():].strip()


def skipped(rest):
    """Shapes whose rc is not the tool's own: pipes, sequences, background, watch modes, check.sh."""
    if "|" in rest or ";" in rest or "&&" in rest or "\n" in rest or rest.endswith("&"):   # newline: rc is the last line's
        return True
    return bool(_SKIP_ARG.search(rest)) or "check.sh" in rest


_ENV = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*=(?:\"[^\"]*\"|'[^']*'|[^\s\"'|;&]*)\s+)+")


def allow_kind(rest):
    """Kind for an allow-listed command, else None. Leading `VAR=value` assignments (`CI=1 npm test`) are stripped."""
    rest = _ENV.sub("", rest, count=1)
    for rx, kind in ALLOW:
        m = rx.match(rest)
        if m:
            if isinstance(kind, str):
                return kind
            sub = m.group(1)
            return (kind or {}).get(sub, sub)
    return None


def _git_root(d):
    cur = os.path.abspath(d)
    while True:
        if os.path.exists(os.path.join(cur, ".git")):   # dir, or file in a worktree
            return cur
        up = os.path.dirname(cur)
        if up == cur:
            return ""
        cur = up


def repo_of(cwd, target):
    base = cwd if isinstance(cwd, str) and os.path.isabs(cwd) else ""
    if target:
        t = os.path.expanduser(target)
        base = t if os.path.isabs(t) else (os.path.join(base, t) if base else "")
    if not base:
        return ""
    return os.path.realpath(_git_root(base) or base)


def gates(repo):
    """Whitespace-normalised `gate` strings of <repo>/.claude/pipelines/*.json."""
    out = set()
    d = os.path.join(repo, ".claude", "pipelines")
    try:
        names = [n for n in os.listdir(d) if _PLNAME.match(n)]
    except OSError:
        return out
    for n in names:
        try:
            with open(os.path.join(d, n), encoding="utf-8") as f:
                pl = json.load(f)
        except (OSError, ValueError):
            continue
        for st in pl.get("stages") or [] if isinstance(pl, dict) else []:
            g = st.get("gate") if isinstance(st, dict) else None
            if isinstance(g, str) and g.strip():
                out.add(_norm(g))
    return out


def classify(cmd, cwd):
    """(mode, step name, repo) for a command worth a row, else None."""
    target, rest = split_cd(cmd)
    if not rest or skipped(rest):
        return None
    if _CI.match(rest):
        if not _CI_EXIT.search(rest) or _CI_REPO.search(rest) or not _CI_ID.search(_CI_IVL.sub(" ", rest)):
            return None
        return "ci", None, repo_of(cwd, target)
    kind = allow_kind(rest)
    if kind:
        return "hook-" + kind, kind, repo_of(cwd, target)
    repo = repo_of(cwd, target)
    if not repo or _norm(rest) not in gates(repo):
        return None
    m = _KIND_WORD.search(rest)
    if m:
        return "gate-" + m.group(1), m.group(1), repo
    return "gate-check", "gate", repo


def head_of(repo):
    """Short commit id from .git/HEAD without a subprocess; '' when unknown."""
    try:
        g = os.path.join(repo, ".git")
        if os.path.isfile(g):
            with open(g, encoding="utf-8") as f:
                line = f.read().strip()
            if not line.startswith("gitdir:"):
                return ""
            g = os.path.join(repo, line[7:].strip())
        with open(os.path.join(g, "HEAD"), encoding="utf-8") as f:
            h = f.read().strip()
        if h.startswith("ref:"):
            ref = h[4:].strip()
            if ".." in ref.split("/"):
                return ""
            common = g
            cd = os.path.join(g, "commondir")
            if os.path.isfile(cd):
                with open(cd, encoding="utf-8") as f:
                    common = os.path.join(g, f.read().strip())
            h = ""
            for base in (g, common):
                p = os.path.join(base, ref)
                if os.path.isfile(p):
                    with open(p, encoding="utf-8") as f:
                        h = f.read().strip()
                    break
            if not h:
                with open(os.path.join(common, "packed-refs"), encoding="utf-8") as f:
                    for ln in f:
                        p = ln.split()
                        if len(p) == 2 and p[1] == ref:
                            h = p[0]
                            break
        return h[:7] if re.match(r"^[0-9a-f]{40,64}$", h) else ""
    except OSError:
        return ""


# Same as sidereus/gitinfo.py GIT_SAFE_OPTS + git_env (the plugin ships hooks/ only, so it cannot import gitinfo).
# ⚠fsmonitor/hooksPath would run repo-configured programs; without GIT_OPTIONAL_LOCKS=0 status takes index.lock
#   and can break the agent's own `git commit` right after the test run.
GIT_SAFE_OPTS = ["-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "core.quotePath=false"]


def git_status(repo):
    """`git status --porcelain -uno` stdout, or None on timeout/error. Patched in tests."""
    try:
        r = subprocess.run(["git"] + GIT_SAFE_OPTS + ["-C", repo, "status", "--porcelain", "-uno"],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=GIT_TIMEOUT,
                           env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _start_path(tuid):
    return os.path.join(START_DIR, tuid) if isinstance(tuid, str) and _TUID.match(tuid) else ""


def _sweep(now):
    try:
        for n in os.listdir(START_DIR):
            p = os.path.join(START_DIR, n)
            try:
                if now - os.path.getmtime(p) > START_TTL:
                    os.remove(p)
            except OSError:
                pass
    except OSError:
        pass


def _take_secs(tuid, now):
    p = _start_path(tuid)
    if not p:
        return 0
    try:
        with open(p, encoding="utf-8") as f:
            t0 = float(f.read().strip())
        os.remove(p)
    except (OSError, ValueError):
        return 0
    return round(max(0.0, min(now - t0, 1e6)), 2)


def append(path, line):
    """Append under flock; past EV_CAP lines, rewrite the last EV_KEEP via tmp + rename."""
    if fcntl is None:
        return _win_append(path, line) if msvcrt is not None else False
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    for _ in range(5):
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            # ⚠ a rotation by another writer replaced the inode while we waited: retry on the new file
            try:
                same = os.fstat(fd).st_ino == os.stat(path).st_ino
            except OSError:
                same = False
            if not same:
                continue
            os.write(fd, line.encode('utf-8'))
            with open(path, encoding='utf-8', errors='replace') as f:
                lines = f.read().splitlines(True)
            if len(lines) > EV_CAP:
                tmp = path + '.tmp'
                with open(tmp, 'w', encoding='utf-8') as f:
                    f.writelines(lines[-EV_KEEP:])
                os.replace(tmp, path)
            return True
        finally:
            os.close(fd)
    return False


def _win_append(path, line):
    """Windows append: msvcrt byte-0 lock on a `<path>.lock` sidecar (bounded wait), binary write, same rotation.
    ⚠Not a lock on the evidence file itself: msvcrt locks are mandatory, so readers of byte 0 would fail, and
    os.replace cannot rename onto a file a handle of ours still holds. A lock miss writes nothing (never unlocked)."""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    lk = os.open(path + '.lock', os.O_RDWR | os.O_CREAT, 0o600)
    try:
        for i in range(WIN_LOCK_TRIES):
            try:
                msvcrt.locking(lk, msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if i == WIN_LOCK_TRIES - 1:
                    return False
                time.sleep(WIN_LOCK_STEP)
        try:
            # ⚠O_BINARY: CRT text mode would turn \n into \r\n
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, 'O_BINARY', 0), 0o600)
            try:
                os.write(fd, line.encode('utf-8'))
            finally:
                os.close(fd)
            with open(path, 'rb') as f:
                lines = f.read().splitlines(True)
            if len(lines) > EV_CAP:
                tmp = path + '.tmp'
                with open(tmp, 'wb') as f:
                    f.writelines(lines[-EV_KEEP:])
                try:
                    os.replace(tmp, path)
                except OSError:
                    pass   # a reader holds the file open: the row is in, rotation waits for the next write
            return True
        finally:
            os.lseek(lk, 0, os.SEEK_SET)
            msvcrt.locking(lk, msvcrt.LK_UNLCK, 1)
    finally:
        os.close(lk)


def handle(ev):
    """Process one hook event dict; returns the row written (for tests) or None."""
    if not isinstance(ev, dict) or ev.get("tool_name") != "Bash":
        return None
    name = ev.get("hook_event_name")
    if name not in ("PreToolUse", "PostToolUse", "PostToolUseFailure"):
        return None
    ti = ev.get("tool_input")
    cmd = ti.get("command") if isinstance(ti, dict) else None
    if not isinstance(cmd, str) or ti.get("run_in_background") is True:
        return None
    hit = classify(cmd, ev.get("cwd"))
    if not hit:
        return None
    now = NOW()
    tuid = ev.get("tool_use_id")
    if name == "PreToolUse":
        if hit[0] == "ci":
            return None   # no duration for CI: the watch time is queue + run time on GitHub, not local work
        p = _start_path(tuid)
        if p:
            os.makedirs(START_DIR, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write("%.3f" % now)
        _sweep(now)
        return None
    secs = 0 if hit[0] == "ci" else _take_secs(tuid, now)
    if name == "PostToolUse":
        resp = ev.get("tool_response")
        if isinstance(resp, dict) and resp.get("interrupted") is True:
            return None
        rc = 0
    else:
        if ev.get("is_interrupt") is True:
            return None
        err = ev.get("error")
        m = _EXIT.match(err) if isinstance(err, str) else None   # ⚠match only; the text is never stored
        if not m and hit[0] == "ci":
            return None   # timeout etc.: an unknown CI result is not a red
        rc = min(int(m.group(1)), 255) if m else 1
    mode, step, repo = hit
    if not repo or (fcntl is None and msvcrt is None):
        return None
    if mode == "ci":
        row = {"v": 1, "kind": "ci", "ts": int(now), "repo": repo, "head": head_of(repo), "rc": rc}
        append(EV_FILE, json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        return row
    out = git_status(repo)
    row = {"v": 1, "kind": "check", "ts": int(now), "mode": mode, "repo": repo, "head": head_of(repo),
           "dirty": bool(out and out.strip()), "rc": rc,
           "steps": [{"name": step, "rc": rc, "n": 0, "failed": 0, "secs": secs}]}
    append(EV_FILE, json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    return row


def main():
    try:
        handle(json.loads(sys.stdin.read() or "null"))
    except Exception:  # noqa: BLE001 — never trap a session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
