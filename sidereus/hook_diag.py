"""Settings › «Diagnostics» (GET /api/diag): hook conflicts and silent plugin hooks across every account and project.

overlaps = other hooks on an event a Sidereus hook also handles (src plugin|user|project · name · account · matcher · cmd)
· sidereus = {event: [Sidereus hook basenames]} · silent = plugin hooks whose stdout JSON Claude Code does not read
(sidereus/hook_fields.py, static estimate) · plugins = installed plugins with version · shadow = projects whose
CLAUDE.md hides AGENTS.md.
⚠Read-only, fixes nothing. ⚠Metadata only: commands go out as script basenames or a fixed «inline <kind>» label (`_disp`); script text,
CLAUDE.md text and env values never leave this module. Only a plugin's registered installPath counts — stale cache
dirs of older versions are never read.
"""
import os
import re
import shlex
import threading
import time

from sidereus import claude_roots, ctxsrc, hook_fields, toolinv
from sidereus.config import CODE_DIR, DATA_DIR
from sidereus.harness import cmd_name

DX_TTL_S = 30
DX_ROWS_MAX = 200
DX_MD_HEAD = 4096
DX_NAME_MAX = 80
DX_JSON_MAX = 256 * 1024   # a larger settings / hooks.json is skipped, not parsed
DX_HOOK_DIRS = (os.path.join(DATA_DIR, "hooks"), os.path.join(CODE_DIR, "hooks"))
DX_HOOKS_DOC = os.path.join(CODE_DIR, "docs", "HOOKS.md")
DX_PLUGIN = "sidereus"       # our own plugin (scripts/build_plugin.py NAME)
_DIAG_CACHE = {"t": 0.0, "v": None}
_DX_NAMES = {"key": None, "v": frozenset()}
_DX_LOCK = threading.Lock()
_DX_NAME_OK = re.compile(r"[^A-Za-z0-9._@ -]+")
_DX_CTRL = re.compile(r"[\x00-\x1f\x7f]+")
_now = time.monotonic


def _json(p):
    try:
        if os.path.getsize(p) > DX_JSON_MAX:
            return {}
    except OSError:
        return {}
    return ctxsrc._json_file(p)


def _clean(s):
    return _DX_NAME_OK.sub("", str(s))[:DX_NAME_MAX]


def _sid_names():
    """Script basenames in the «Claude Code hooks» table of docs/HOOKS.md; memo by mtime."""
    try:
        mt = os.stat(DX_HOOKS_DOC).st_mtime_ns
    except OSError:
        return frozenset()
    if _DX_NAMES["key"] != (DX_HOOKS_DOC, mt):
        try:
            with open(DX_HOOKS_DOC, encoding="utf-8") as f:
                txt = f.read(256 * 1024)
        except OSError:
            return frozenset()
        _DX_NAMES["key"], _DX_NAMES["v"] = (DX_HOOKS_DOC, mt), frozenset(re.findall(r"^\| `([\w.-]+\.py)` \|", txt, re.M))
    return _DX_NAMES["v"]


_DX_SHELL_OPS = re.compile(r"[|;&<>`\n]|\$\(")
_DX_SHELL_KW = frozenset(("if", "for", "while", "case", "until", "[", "[[", "test", "!", "{", "(", "function"))
_DX_INLINE_FLAGS = frozenset(("-e", "-c", "-p", "--eval", "--print", "-m"))
_DX_KIND = (("node", re.compile(r"^(node|deno|bun)$")), ("python", re.compile(r"^python[0-9.]*$")),
            ("shell", re.compile(r"^(bash|sh|zsh|dash|ksh|fish)$")))
_DX_PATHLIKE = re.compile(r"^[A-Za-z0-9._~/${}@+-]+$")


def _inline(kind):
    return "inline " + kind   # fixed label; the UI translates it (never a slice of the command)


def _disp(c, path):
    """Display name of a hook command: the resolved script's basename, else a script-like token's basename, else a fixed
    «inline <kind>» label. ⚠Inline code (node -e, bash -c, shell one-liners) would otherwise surface as its text."""
    if path:
        return os.path.basename(path)[:DX_NAME_MAX]
    try:
        toks = shlex.split(c)
    except ValueError:      # unbalanced quotes: treat as a one-liner
        return _inline("shell")
    if not toks or _DX_SHELL_OPS.search(c) or toks[0] in _DX_SHELL_KW:
        return _inline("shell")
    for i, t in enumerate(toks[:-1]):
        if t in _DX_INLINE_FLAGS:
            b = os.path.basename(toks[i - 1]) if i else ""
            return _inline(next((k for k, rx in _DX_KIND if rx.match(b)), "script"))
    n = cmd_name(c)
    if n == toolinv.MASK:
        return n
    t = next((x for x in toks if os.path.basename(x.rstrip("/")) == n), "")
    return n if n and t and _DX_PATHLIKE.match(t) else _inline("shell")


def _hooks(obj):
    """(event, matcher, command) of every command hook in a settings/hooks.json `hooks` object."""
    out = []
    for ev in sorted(obj if isinstance(obj, dict) else {}):
        for g in obj[ev] if isinstance(obj[ev], list) else []:
            if not isinstance(g, dict):
                continue
            m = _DX_CTRL.sub("", g["matcher"])[:DX_NAME_MAX] if isinstance(g.get("matcher"), str) else ""   # regex text: keep | * ( )
            for h in g.get("hooks") if isinstance(g.get("hooks"), list) else []:
                if isinstance(h, dict) and h.get("type", "command") == "command" and isinstance(h.get("command"), str):
                    out.append((str(ev), m, h["command"]))
    return out


def _is_sid(path, names, plugin=""):
    """A Sidereus hook: a documented script under our hooks dirs, or under our own plugin's hooks/."""
    if not path or os.path.basename(path) not in names:
        return False
    d = os.path.dirname(path)
    return any(d == os.path.realpath(h) for h in DX_HOOK_DIRS) or (plugin == DX_PLUGIN and os.path.basename(d) == "hooks")


def _accounts(home, rows, plugins):
    """User hooks of every account into rows; installed plugins (deduped by realpath(installPath)) into plugins."""
    for a in claude_roots.accounts():
        d, lab = a["dir"], _clean(a.get("label") or "")
        s, sl = _json(os.path.join(d, "settings.json")), _json(os.path.join(d, "settings.local.json"))
        for f in (s, sl):
            for ev, m, c in _hooks(f.get("hooks")):
                rows.append({"event": ev, "matcher": m, "src": "user", "name": "", "acct": lab, "c": c,
                             "path": hook_fields.resolve(c, "", (d,) + tuple(DX_HOOK_DIRS), home)})
        en = {}
        for f in (s, sl):
            if isinstance(f.get("enabledPlugins"), dict):
                en.update(f["enabledPlugins"])
        reg = _json(os.path.join(d, "plugins", "installed_plugins.json")).get("plugins")
        for k in sorted(reg if isinstance(reg, dict) else {}):
            for inst in reg[k] if isinstance(reg[k], list) else []:
                ip = inst.get("installPath") if isinstance(inst, dict) else None
                if not isinstance(ip, str) or not os.path.isdir(ip):
                    continue
                nm, _s, mk = str(k).partition("@")
                p = plugins.setdefault(os.path.realpath(ip), {"name": _clean(nm), "market": _clean(mk), "version": "",
                                                              "accts": [], "on": False})
                if not p["version"] and isinstance(inst.get("version"), str):
                    p["version"] = _clean(inst["version"])
                if lab not in p["accts"]:
                    p["accts"].append(lab)
                p["on"] = p["on"] or en.get(k, True) is not False   # missing key = enabled (toolinv._plugins)
                break


def _plugin_rows(home, rows, plugins):
    """Hooks of every enabled plugin into rows; sets known/checked on each plugin."""
    for rp in sorted(plugins):
        p = plugins[rp]
        hj = _json(os.path.join(rp, "hooks", "hooks.json"))
        hs = _hooks(hj.get("hooks") if isinstance(hj.get("hooks"), dict) else hj)
        p["known"], p["checked"] = bool(p["version"]), bool(hs) and p["on"]
        if not p["on"]:
            continue
        for ev, m, c in hs:
            rows.append({"event": ev, "matcher": m, "src": "plugin", "name": p["name"], "acct": ", ".join(p["accts"]),
                         "c": c, "path": hook_fields.resolve(c, rp, (rp,), home), "plugin": p})


def _shadowed(proj):
    """True when proj has both CLAUDE.md and AGENTS.md and CLAUDE.md neither links to nor imports AGENTS.md."""
    cm, am = os.path.join(proj, "CLAUDE.md"), os.path.join(proj, "AGENTS.md")
    if not (os.path.isfile(cm) and os.path.isfile(am)):
        return False
    if os.path.realpath(cm) == os.path.realpath(am):
        return False
    try:
        with open(cm, "rb") as f:
            head = f.read(DX_MD_HEAD)
    except OSError:
        return False
    return b"@AGENTS.md" not in head


def _projects(home, rows, shadow):
    acct_dirs = {os.path.realpath(a["dir"]) for a in claude_roots.accounts()}
    for proj in toolinv.known_projects():
        base = os.path.join(proj, ".claude")
        if _shadowed(proj) and len(shadow) < DX_ROWS_MAX:
            shadow.append({"proj": proj, "claude": "CLAUDE.md", "agents": "AGENTS.md"})
        if os.path.realpath(base) in acct_dirs:
            continue
        for fn in ("settings.json", "settings.local.json"):
            for ev, m, c in _hooks(_json(os.path.join(base, fn)).get("hooks")):
                rows.append({"event": ev, "matcher": m, "src": "project", "name": _clean(os.path.basename(proj)), "acct": "",
                             "c": c, "path": hook_fields.resolve(c, "", (proj,) + tuple(DX_HOOK_DIRS), home)})


def _build():
    home = claude_roots.SCAN_HOME
    rows, plugins, shadow = [], {}, []
    _accounts(home, rows, plugins)
    _plugin_rows(home, rows, plugins)
    _projects(home, rows, shadow)
    names = _sid_names()
    sid = {}
    for r in rows:
        r["sid"] = _is_sid(r["path"], names, (r.get("plugin") or {}).get("name", ""))
        if r["sid"]:
            sid.setdefault(r["event"], set()).add(_disp(r["c"], r["path"]))
    pub = ("event", "matcher", "src", "name", "acct")
    over = [dict({k: r[k] for k in pub}, cmd=_disp(r["c"], r["path"])) for r in rows if not r["sid"] and r["event"] in sid]
    over.sort(key=lambda o: (o["event"], o["src"], o["name"], o["cmd"]))
    silent, seen = [], set()
    for r in rows:
        p = r.get("plugin")
        if not p or r["sid"]:
            continue
        v, un = hook_fields.judge(r["path"], r["event"])
        k = (p["name"], r["event"], _disp(r["c"], r["path"]))
        if v in ("silent", "partial") and k not in seen and len(silent) < DX_ROWS_MAX:
            seen.add(k)
            silent.append({"plugin": p["name"], "version": p["version"], "event": r["event"], "cmd": k[2], "verdict": v,
                           "unread": un})
    pl = sorted(plugins.values(), key=lambda p: (p["name"], p["market"]))[:DX_ROWS_MAX]
    return {"ok": True, "overlaps": over[:DX_ROWS_MAX], "sidereus": {e: sorted(v) for e, v in sorted(sid.items())},
            "silent": silent, "plugins": [dict(p, accts=sorted(p["accts"])) for p in pl], "shadow": shadow}


def diag():
    """(code, body) for GET /api/diag; memoized DX_TTL_S seconds."""
    now = _now()
    with _DX_LOCK:
        if _DIAG_CACHE["v"] is not None and now - _DIAG_CACHE["t"] < DX_TTL_S:
            return 200, _DIAG_CACHE["v"]
    v = _build()
    with _DX_LOCK:
        _DIAG_CACHE["t"], _DIAG_CACHE["v"] = now, v
    return 200, v
