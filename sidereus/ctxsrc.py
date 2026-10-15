"""«Context sources» — what Claude Code loads into a session's context besides the conversation (GET /api/session/context).

⚠Metadata only (AGENTS.md rule 1): paths, byte sizes, token estimates, counts and config key names.
  File text, memory text, MCP commands/env and hook commands are never read into the payload.
"""
import json
import os
import time
from sidereus.memo import BoundedMemo
from sidereus.config import claude_home, claude_json
from sidereus.transcript import CLAUDE_PROJECTS
from sidereus.ident import _slug
from sidereus.gitinfo import _git_root
from sidereus.work import _SID_SAFE, _allowed_cwds, _past_row

CLAUDE_DIR = claude_home()
CLAUDE_JSON = claude_json()
CTX_TTL_S = 60
CTX_BYTES_PER_TOK = 3.5          # rough; the UI labels it «approx.»
CTX_WALK_MAX = 40                # directory levels from cwd up to the git root
CTX_LIST_MAX = 200               # rule files / memory files counted per directory
INSTR_NAMES = ("CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", os.path.join(".claude", "CLAUDE.md"))
_ctx_cache = BoundedMemo(64)     # cwd -> (measured at, payload); sid only gates access
_cj_memo = BoundedMemo(2)        # ~/.claude.json path -> parsed names only, stamped by (mtime, size)


def _tok(n):
    return int(round(n / CTX_BYTES_PER_TOK))


def _size(p):
    try:
        return os.path.getsize(p) if os.path.isfile(p) else -1
    except OSError:
        return -1


def _walk_dirs(cwd, root):
    """cwd, its parents, ..., root (outermost first). No git root → cwd only."""
    cur, out = os.path.abspath(cwd), []
    if not root:
        return [cur]
    root = os.path.abspath(root)
    for _ in range(CTX_WALK_MAX):
        out.append(cur)
        if cur == root:
            break
        up = os.path.dirname(cur)
        if up == cur:
            break
        cur = up
    return out[::-1]


def _md_files(d, cap=CTX_LIST_MAX):
    """Sorted *.md paths under `d` (recursive, capped)."""
    out = []
    for base, dirs, files in os.walk(d):
        dirs.sort()
        for f in sorted(files):
            if f.endswith(".md"):
                out.append(os.path.join(base, f))
                if len(out) >= cap:
                    return out
    return out


def _instr_files(cwd, root):
    """Instruction files: user-level first, then cwd→git root (outer first), then `.claude/rules/*.md`."""
    rows, seen = [], set()

    def add(p, scope):
        rp = os.path.realpath(p)
        n = _size(p)
        if n < 0 or rp in seen:
            return
        seen.add(rp)
        rows.append({"path": p, "scope": scope, "bytes": n, "tokens": _tok(n)})

    add(os.path.join(CLAUDE_DIR, "CLAUDE.md"), "user")
    for p in _md_files(os.path.join(CLAUDE_DIR, "rules")):
        add(p, "user-rule")
    for d in _walk_dirs(cwd, root):
        for nm in INSTR_NAMES:
            add(os.path.join(d, nm), "local" if nm == "CLAUDE.local.md" else "project")
        for p in _md_files(os.path.join(d, ".claude", "rules")):
            add(p, "rule")
    return rows


def _memory(cwd, root):
    """Auto memory dir `~/.claude/projects/<slug>/memory` (cwd slug first, then the git root's)."""
    for c in [cwd] + ([root] if root and root != cwd else []):
        d = os.path.join(CLAUDE_PROJECTS, _slug(c), "memory")
        if os.path.isdir(d):
            idx = os.path.join(d, "MEMORY.md")
            n = max(0, _size(idx))
            files = len(_md_files(d))
            return {"dir": d, "index": idx if n else "", "bytes": n, "tokens": _tok(n), "files": files}
    return {"dir": "", "index": "", "bytes": 0, "tokens": 0, "files": 0}


def read_text(p, n=-1, errors="strict"):
    """Text of a config file (first `n` chars); a leading UTF-8 BOM is dropped (editors on Windows write one)."""
    with open(p, encoding="utf-8-sig", errors=errors) as f:
        return f.read(n)


def _json_file(p):
    """Top-level object of a JSON config file; anything else (missing, broken, non-object) = {}."""
    try:
        v = json.loads(read_text(p))
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def _names(v):
    return sorted(str(k) for k in v) if isinstance(v, dict) else []


def _claude_json():
    """Only MCP server names from ~/.claude.json: {"user": [...], "projects": {cwd: [...]}}. Parsed once per (mtime, size)."""
    try:
        st = os.stat(CLAUDE_JSON)
        stamp = (st.st_mtime, st.st_size)
    except OSError:
        return {"user": [], "projects": {}}
    hit = _cj_memo.get(CLAUDE_JSON, stamp=stamp)
    if hit is not None:
        return hit
    d = _json_file(CLAUDE_JSON)
    pr = d.get("projects") if isinstance(d.get("projects"), dict) else {}
    out = {"user": _names(d.get("mcpServers")),
           "projects": {k: _names((v or {}).get("mcpServers")) for k, v in pr.items() if isinstance(v, dict)}}
    return _cj_memo.put(CLAUDE_JSON, out, stamp=stamp)


def _mcp(cwd, root):
    """[{name, scope}] from ~/.claude.json (user + this project) and `.mcp.json` at the git root (or cwd)."""
    cj = _claude_json()
    rows, seen = [], set()
    proj = os.path.join(root or cwd, ".mcp.json")
    for scope, names in (("local", cj["projects"].get(cwd) or cj["projects"].get(root or "") or []),
                         ("project", _names(_json_file(proj).get("mcpServers"))),
                         ("user", cj["user"])):
        for n in names:
            if n not in seen:
                seen.add(n)
                rows.append({"name": n, "scope": scope})
    return rows


def _settings_files(cwd, root):
    base = root or cwd
    return [os.path.join(CLAUDE_DIR, "settings.json"), os.path.join(CLAUDE_DIR, "settings.local.json"),
            os.path.join(base, ".claude", "settings.json"), os.path.join(base, ".claude", "settings.local.json")]


def _hooks(cwd, root):
    """[{event, n}] — n = hook entries configured for that event across settings files. ⚠No commands."""
    cnt = {}
    for p in _settings_files(cwd, root):
        h = _json_file(p).get("hooks")
        if not isinstance(h, dict):
            continue
        for ev, groups in h.items():
            n = 0
            for g in (groups if isinstance(groups, list) else []):
                hs = g.get("hooks") if isinstance(g, dict) else None
                n += sum(1 for x in hs if isinstance(x, dict)) if isinstance(hs, list) else 0   # null/number entries are not hooks
            if n:
                cnt[str(ev)] = cnt.get(str(ev), 0) + n
    return [{"event": k, "n": v} for k, v in sorted(cnt.items())]


def _count_skills(d):
    try:
        return sum(1 for x in os.listdir(d) if os.path.isfile(os.path.join(d, x, "SKILL.md")))
    except OSError:
        return 0


def _count_agents(d):
    try:
        return sum(1 for x in os.listdir(d) if x.endswith(".md") and os.path.isfile(os.path.join(d, x)))
    except OSError:
        return 0


def context_sources(cwd):
    """Payload for one cwd (uncached)."""
    root = _git_root(cwd) or ""
    base = root or cwd
    instr = _instr_files(cwd, root)
    mem = _memory(cwd, root)
    mcp = _mcp(cwd, root)
    hooks = _hooks(cwd, root)
    nbytes = sum(r["bytes"] for r in instr) + mem["bytes"]
    return {"ok": True, "cwd": cwd, "root": root, "at": int(time.time()),
            "bytes": nbytes, "tokens": _tok(nbytes), "instr": instr, "memory": mem, "mcp": mcp, "hooks": hooks,
            "skills": {"user": _count_skills(os.path.join(CLAUDE_DIR, "skills")),
                       "project": _count_skills(os.path.join(base, ".claude", "skills"))},
            "agents": {"user": _count_agents(os.path.join(CLAUDE_DIR, "agents")),
                       "project": _count_agents(os.path.join(base, ".claude", "agents"))},
            "counts": {"instr": len(instr), "memory": mem["files"], "mcp": len(mcp),
                       "hooks": sum(h["n"] for h in hooks)}}


def session_context(cwd, sid=""):
    """(code, body) for `GET /api/session/context?cwd=&sid=` — cwd must be a session cwd the screen knows."""
    cwd, sid = cwd or "", sid or ""
    if not cwd or not os.path.isabs(cwd) or "\x00" in cwd:
        return 400, {"ok": False, "msg": "cwd required"}
    if sid and not _SID_SAFE.match(sid):
        return 400, {"ok": False, "msg": "bad sid"}
    if not (_allowed_cwds().get(cwd) or _past_row(cwd, sid)) or not os.path.isdir(cwd):
        return 400, {"ok": False, "msg": "Only sessions shown on screen can be opened."}
    now = time.time()
    hit = _ctx_cache.get(cwd)
    if hit and now - hit[0] < CTX_TTL_S:
        return 200, hit[1]
    out = context_sources(cwd)
    _ctx_cache.put(cwd, (now, out))
    return 200, out
