"""Mailbox identity, project slugs and binary lookup (rich_env / bin_path)."""
import json
import os
import re
import shutil
from sidereus.config import IS_MAC, IS_WIN, claude_json
from sidereus.bus import _load
from sidereus.memo import BoundedMemo


GENERIC_DIRS ={"admin", "api", "web", "app", "server", "src", "backend", "frontend", "packages"}
_SID_PREFIX = ("session-", "rollout-")   # file-stem fallbacks: gemini `session-<ts>-<hex8>`, codex `rollout-<ts>-<uuid>`
_SID_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}(?:-\d{2})?-")


def _sid8(sid):
    """8-char display id for a session. ⚠A plain sid[:8] of a file-stem sid shows «session-» for every row —
    strip prefix + timestamp first. Display only: never use it as a lookup key (it is not the old sid[:8])."""
    s = str(sid) if sid else ""
    for p in _SID_PREFIX:
        if s.startswith(p):
            s = _SID_TS.sub("", s[len(p):])
            break
    return s[:8]


# ★Under launchd PATH is only `/usr/bin:/bin:/usr/sbin:/sbin`, so homebrew-installed tools are not found.
#   Measured 2026-08-24: `FileNotFoundError` kept piling up in `viewer.err`, and the on-screen usage was the old value
#   from the cache (usage-cache.json) — **silently stale**. EnvironmentVariables in the plist would work, but get lost
#   whenever the plist is regenerated, so the code finds absolute paths (cached once found, used directly afterwards).
_BIN_CACHE = {}
# ⚠POSIX dirs only off Windows — "/bin" there resolves to `C:\bin` on the current drive.
_BIN_DIRS = () if IS_WIN else (("/opt/homebrew/bin",) if IS_MAC else ()) + (
    "/usr/local/bin", os.path.expanduser("~/.local/bin"), os.path.expanduser("~/.bun/bin"), "/usr/bin", "/bin")


def _real_home():
    try:
        import pwd
        return pwd.getpwuid(os.getuid()).pw_dir     # ⚠not $HOME — the viewer runs with HOME=data dir
    except (ImportError, KeyError):
        return os.path.expanduser("~")


def node_dir():
    """Folder of `node` on PATH, else the old Homebrew node@22 path (kept as fallback)."""
    n = shutil.which("node")
    return os.path.dirname(n) if n else "/opt/homebrew/opt/node@22/bin"


def rich_env():
    """Environment with a boosted PATH. **Absolute paths alone are not enough** — measured 2026-08-24:
    `ccusage` is a `#!/usr/bin/env node` script and `node` lives in `/opt/homebrew/opt/node@22/bin`.
    Called by absolute path it runs, but the shebang cannot find `node` and prints `env: node: No such file or directory`
    **to stderr, not stdout**; the empty stdout then became a JSONDecodeError.
    launchd's PATH is only `/usr/bin:/bin:/usr/sbin:/sbin`, so children get a generous PATH."""
    env = dict(os.environ)
    extra = [d for d in _BIN_DIRS if os.path.isdir(d)]
    brew = ("/opt/homebrew/opt/node@22/bin", "/opt/homebrew/opt/node/bin") if IS_MAC else ()
    extra += [d for d in (node_dir(),) + brew if d and os.path.isdir(d)]
    cur = env.get("PATH", "")
    have = set(cur.split(os.pathsep))     # ⚠os.pathsep — ":" splits `C:\...` entries on Windows
    env["PATH"] = os.pathsep.join([d for d in extra if d not in have] + ([cur] if cur else []))
    return env


def bin_path(name):
    """Absolute path of an executable. If not on PATH, scan known directories. If absent, the bare name (old behavior)."""
    hit = _BIN_CACHE.get(name)
    if hit:
        return hit
    found = shutil.which(name)
    if not found:
        for d in _BIN_DIRS:
            cand = os.path.join(d, name)
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                found = cand
                break
    _BIN_CACHE[name] = found or name
    return _BIN_CACHE[name]


def bin_forget(name):
    """Drop the cached path so the next `bin_path` re-resolves it.
    ⚠Call on FileNotFoundError: a CLI update can swap the binary, and the cache would keep the dead path forever."""
    _BIN_CACHE.pop(name, None)


# ── Mailbox identity ─────────────────────────────────────────────────────────
# ★Resolved **in the same order** as the MCP server (`mailbox_mcp.server._me`): a value a session set via login is
#   unknowable here (it lives only inside that session's process), so only identity.json saved with remember=true
#   and MAILBOX_ME from the MCP config are consulted.
# ★~/.claude.json is ~165KB and mbox_of runs per session row every poll (8-20 ms/poll unmemoized), so the parsed
#   value is kept per path, stamped by (st_mtime_ns, size). ⚠Keyed by path: claude_json() follows CLAUDE_CONFIG_DIR,
#   so another root never reuses this one's value. (ctxsrc._cj_memo keeps MCP names only and imports this module.)
_ENV_MEMO = BoundedMemo(4)


def _mbox_env_default():
    """MAILBOX_ME baked into the MCP config (~/.claude.json) — the value passed as env at session start."""
    path = claude_json()
    try:
        st = os.stat(path)
    except OSError:
        return ""        # no ~/.claude.json: no env default, same as the MCP server
    stamp = (st.st_mtime_ns, st.st_size)
    hit = _ENV_MEMO.get(path, stamp=stamp)
    if hit is not None:
        return hit
    try:
        with open(path, encoding="utf-8") as f:
            c = json.load(f)
        val = ((c.get("mcpServers") or {}).get("mailbox") or {}).get("env", {}).get("MAILBOX_ME") or ""
    except (OSError, ValueError, AttributeError):
        val = ""         # odd ~/.claude.json: no env default, same as the MCP server
    return _ENV_MEMO.put(path, val, stamp=stamp)


def mbox_of(cwd):
    """(id, source). Source: identity (saved per path) · env · folder · none

    ★Removed the `default` fallback of `identity.json` (2026-09-08) — the MCP server (`server.py:_me()`) never looks at
      `default` when a project path exists. So this branch was **a divergence existing only in the viewer**, the spot
      that made unregistered sessions appear under someone else's id (same spot as the 2026-08-12 incident).
      The only place that sets an id is `mailbox_login` (= `/room as <id>`)."""
    ident = _load("identity.json", {})
    if cwd and isinstance(ident, dict):
        if cwd in ident:
            return ident[cwd], "identity"
    env = _mbox_env_default()
    if env:
        return env, "env"
    if cwd:
        return os.path.basename(cwd), "folder"
    return "", "none"


def _slug(cwd):
    """cwd -> directory name under `~/.claude/projects/`. Every non-alphanumeric becomes `-` (matches observed harness values).

    The reverse (_cwd_from_slug) needs guessing, since `-` could have been `/`·`.`·`_`,
    but this direction is lossless. So finding "this path's directory" always uses this one."""
    return "".join(c if c.isalnum() else "-" for c in cwd or "")


def _cwd_from_slug(dirname):
    """`-home-me-work-repo-A` → `/home/me/work/repo-A`.
    ★Why: when the transcript tail had no `cwd`, the project name fell to `?` (observed 2026-08-19; the session then looked
      as if it had not appeared). The folder name is the path, so it can be retraced —
      but names contain hyphens like `repo-A`, so segments are joined **while checking existing directories**."""
    parts = [x for x in dirname.split("-") if x]
    if not parts:
        return ""
    path, i = "/", 0
    while i < len(parts):
        # ★a hyphen may be part of a folder name (bot-A) — pick **the longest child name**.
        best, best_j = None, None
        name = parts[i]
        for j in range(i + 1, len(parts) + 1):
            if os.path.isdir(os.path.join(path, name)):
                best, best_j = name, j
            if j < len(parts):
                name = name + "-" + parts[j]
        if best is None:
            return ""
        path, i = os.path.join(path, best), best_j
    return path if os.path.isdir(path) else ""


PROJ_ROOT_MAX = 512
_PROJ_ROOT = BoundedMemo(PROJ_ROOT_MAX)   # cwd -> project root (no TTL, like gitinfo._GITROOT)


def _git_walk(d):
    """Nearest ancestor of an absolute dir holding `.git` (dir, or file in a worktree); "" if none. Uncached fs walk."""
    cur = os.path.abspath(d)
    while True:
        g = os.path.join(cur, ".git")
        if os.path.isdir(g) or os.path.isfile(g):
            return cur
        up = os.path.dirname(cur)
        if up == cur:
            return ""
        cur = up


def _proj_root(cwd):
    """Project path of a cwd: its git root (a shell cd into a repo subfolder stays the same project), else the cwd.
    ⚠A git root at the user's home or `/` (dotfiles repo) is ignored — it would merge every project into one."""
    if not cwd or not os.path.isabs(cwd):
        return cwd or ""
    hit = _PROJ_ROOT.get(cwd)
    if hit is None:
        r = _git_walk(cwd)
        if r and os.path.dirname(r) != r and os.path.normpath(r) != os.path.normpath(_real_home()):
            hit = r
        else:
            hit = cwd
        _PROJ_ROOT.put(cwd, hit)
    return hit


def _proj_name(cwd):
    """Working directory -> display name of its project (git root, `_proj_root`).
    If the basename is a common word, prefix one parent level (admin → proj-C/admin)."""
    if not cwd:
        return ""
    cwd = _proj_root(cwd).replace(os.sep, "/")   # Windows `C:\a\b` splits like POSIX; no-op elsewhere
    parts = [x for x in cwd.rstrip("/").split("/") if x]
    if not parts:
        return ""
    # ★A worktree is **a copy of the repo**, so name it by the repo (2026-09-08).
    #   The basename of `.../repo-A/.claude/worktrees/agent-<id>` is `agent-<id>`, so
    #   **something that is not a project** was printed after `@` in the failure catalog — which session to visit was unfindable.
    #   Measured: 10 of 127 in a 24 h window (two worktree agents, 6 + 4) looked like this.
    #   ⚠Only trim, then **run through the GENERIC_DIRS rule below** — returning right here makes
    #     `.../proj-C/admin/.claude/worktrees/agent-x` become `admin` (it must be `proj-C/admin`).
    #   ⚠`i > 0` condition: with nothing in front (`/.claude/worktrees/agent-x`) there is nothing to trim, so leave it.
    for i in range(len(parts) - 1):
        if i > 0 and parts[i] == ".claude" and parts[i + 1] == "worktrees":
            parts = parts[:i]
            break
    if parts[-1] in GENERIC_DIRS and len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return parts[-1]
