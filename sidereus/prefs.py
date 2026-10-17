"""«Preferences» server prefs: GET /api/prefs, POST /api/prefs/set — an allow-list of config.local.json keys.

Writes go to the config file only (atomic tmp + os.replace, previous file kept as .bak); running values
change after a restart. Unknown and `_comment` keys in the file are kept as they are.
Reader modules (saver, live_win) call `effective()` / `compact_hist()` at import.
"""
import json
import os
import re
import shutil
import threading
from datetime import datetime

from sidereus.config import CFG
from sidereus.bus import _atomic_write
from sidereus.warn import warn_once

CONFIG_PATH = None          # None = mailbox_config.config_path(); ⚠tests set a tmp path (never the live file)
PREFS_BODY_MAX = 8192
_LOCK = threading.Lock()

# No built-in autoCompactWindow history: empty = the current setting (compact-win.json) alone; config compact_history adds dated rows.
COMPACT_HIST_DEFAULT = ()
COMPACT_MAX_ROWS = 50
COMPACT_MIN, COMPACT_MAX = 1_000, 10_000_000
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NAME_BAD = re.compile(r"[\x00-\x1f\x7f/\\]")


def _v_dir(v):
    if not isinstance(v, str) or not v.strip() or len(v) > 512 or "\x00" in v:
        raise ValueError("path must be a non-empty string")
    v = v.strip()
    if not os.path.isabs(os.path.expanduser(v)) or ".." in v.replace("\\", "/").split("/"):
        raise ValueError("path must be absolute or start with ~ (no ..)")
    return v


def _v_hist(v):
    if not isinstance(v, list) or len(v) > COMPACT_MAX_ROWS:
        raise ValueError("compact_history must be a list of [YYYY-MM-DD, int|null] (max %d)" % COMPACT_MAX_ROWS)
    out, last = [], ""
    for row in v:
        if not isinstance(row, list) or len(row) != 2 or not isinstance(row[0], str) or not _DATE_RE.match(row[0]):
            raise ValueError("each row is [YYYY-MM-DD, int|null]")
        try:
            datetime.strptime(row[0], "%Y-%m-%d")
        except ValueError:
            raise ValueError("bad date %s" % row[0])
        n = row[1]
        if n is not None and (isinstance(n, bool) or not isinstance(n, int) or not COMPACT_MIN <= n <= COMPACT_MAX):
            raise ValueError("window must be null or %d..%d" % (COMPACT_MIN, COMPACT_MAX))
        if row[0] <= last:
            raise ValueError("dates must be strictly ascending")
        last = row[0]
        out.append([row[0], n])
    return out


PORT_MIN, PORT_MAX = 1024, 65535


def _v_port(v):
    # ⚠Rejected, not clamped: a clamped port would silently move the viewer to an address nobody typed.
    if isinstance(v, bool) or not isinstance(v, int) or not PORT_MIN <= v <= PORT_MAX:
        raise ValueError("port must be an integer %d..%d" % (PORT_MIN, PORT_MAX))
    return v


def _v_name(v):
    if not isinstance(v, str) or not v.strip() or len(v.strip()) > 64 or _NAME_BAD.search(v):
        raise ValueError("must be 1..64 characters, no / \\ or control characters")
    return v.strip()


def _v_features(v):
    if not isinstance(v, dict) or len(v) > 64 or not all(
            isinstance(k, str) and re.match(r"^[a-z][a-z0-9_]{0,31}$", k) and isinstance(b, bool) for k, b in v.items()):
        raise ValueError("features must be {id: true|false}")
    return dict(v)


APPLY_MODES = ("auto", "ask", "off")
APPLY_PROJ_MAX = 200


def _v_apply(v):
    # Read by hooks/pipelines_brief.py (SessionStart): global mode + exact-cwd overrides.
    if not isinstance(v, dict) or set(v) - {"mode", "projects"}:
        raise ValueError("pipeline_apply must be {mode, projects}")
    mode, projs = v.get("mode", "auto"), v.get("projects") or {}
    if mode not in APPLY_MODES:
        raise ValueError("mode must be auto|ask|off")
    if not isinstance(projs, dict) or len(projs) > APPLY_PROJ_MAX or not all(
            isinstance(k, str) and os.path.isabs(k) and "\x00" not in k and len(k) <= 512 and m in APPLY_MODES for k, m in projs.items()):
        raise ValueError("projects must be {absolute path: auto|ask|off} (max %d)" % APPLY_PROJ_MAX)
    return {"mode": mode, "projects": dict(projs)}


WATCH_MODES = ("on", "off")
WATCH_PROJ_MAX = 200
WATCH_PATH_MAX = 1024


def _v_watch(v):
    # Read by the SessionStart hook: global mode + exact-cwd overrides (same shape as pipeline_apply).
    if not isinstance(v, dict) or set(v) - {"mode", "projects"}:
        raise ValueError("mailbox_watch must be {mode, projects}")
    mode, projs = v.get("mode", "on"), v.get("projects") or {}
    if mode not in WATCH_MODES:
        raise ValueError("mode must be on|off")
    if not isinstance(projs, dict) or len(projs) > WATCH_PROJ_MAX or not all(
            isinstance(k, str) and os.path.isabs(k) and "\x00" not in k and len(k) <= WATCH_PATH_MAX and m in WATCH_MODES
            for k, m in projs.items()):
        raise ValueError("projects must be {absolute path: on|off} (max %d, path <= %d chars)" % (WATCH_PROJ_MAX, WATCH_PATH_MAX))
    return {"mode": mode, "projects": dict(projs)}


def watch_on(cwd, v=None):
    """Effective mailbox watch for a session cwd: longest project prefix (cwd == K or under K/), else mode; invalid = on."""
    if v is None:
        v = effective("mailbox_watch")
    else:
        try:
            v = _v_watch(v)
        except ValueError:
            return True
    c = _path_key(cwd)
    hit = [k for k in v["projects"] if c == _path_key(k) or c.startswith(_path_key(k).rstrip(os.sep) + os.sep)]
    return (v["projects"][max(hit, key=len)] if hit else v["mode"]) == "on"


def _path_key(p):
    """Path form for prefix compares: unchanged on POSIX; ⚠Windows mixes `/` and `\\` and ignores case."""
    return p if os.sep == "/" else os.path.normcase(os.path.normpath(p))


ROOTS_MAX = 16
HOME_DIR = os.path.expanduser("~")   # tests patch this


def dir_too_wide(path, home):
    """True if path resolves to "/", `home` or a parent of `home` (a root there would expose every file)."""
    rp = os.path.realpath(os.path.expanduser(path))
    hp = os.path.realpath(home)
    return rp == os.path.dirname(rp) or hp == rp or hp.startswith(rp.rstrip(os.sep) + os.sep)
_ROOT_LABEL = re.compile(r"^[A-Za-z0-9._-]{1,24}$")


def _v_roots(v):
    # Extra Claude config roots read by sidereus/claude_roots.py: [{dir, label?}].
    if not isinstance(v, list) or len(v) > ROOTS_MAX:
        raise ValueError("claude_roots must be a list of {dir, label} (max %d)" % ROOTS_MAX)
    out = []
    for ent in v:
        if not isinstance(ent, dict) or set(ent) - {"dir", "label"} or "dir" not in ent:
            raise ValueError("each entry is {dir, label}")
        row = {"dir": _v_dir(ent["dir"])}
        if dir_too_wide(row["dir"], HOME_DIR):
            raise ValueError("dir must not be /, the home dir or a parent of it")
        if ent.get("label") is not None:
            if not isinstance(ent["label"], str) or not _ROOT_LABEL.match(ent["label"]):
                raise ValueError("label must be 1..24 of A-Z a-z 0-9 . _ -")
            row["label"] = ent["label"]
        out.append(row)
    return out


# key -> (default, validator, env override var or None). ⚠Only these keys can be written.
PREFS = {
    "saver_hook_dir": ("~/.claude/hooks", _v_dir, None),
    "compact_history": ([list(r) for r in COMPACT_HIST_DEFAULT], _v_hist, None),
    "port": (8799, _v_port, "SIDEREUS_PORT"),   # viewer + clients read it (mailbox_config.port()); applies after a restart
    "viewer_me": ("사용자", _v_name, "MAILBOX_VIEWER_ME"),
    "default_room": ("general", _v_name, "MAILBOX_VIEWER_ROOM"),
    "features": ({}, _v_features, None),   # sidereus/features.py toggles; {} = every feature on
    "pipeline_apply": ({"mode": "auto", "projects": {}}, _v_apply, None),   # pipeline tab «Apply» (sidereus/pipeline_projects.py)
    "mailbox_watch": ({"mode": "on", "projects": {}}, _v_watch, None),   # settings «Mailbox watch» (web/js/90d-mailwatch.js)
    "claude_roots": ([], _v_roots, None),   # extra account roots (sidereus/claude_roots.py); config file only, no UI yet
}
# Keys with their own settings section (not the generic text field in 90b-mypref.js); still writable via prefs_set.
PREFS_OWN_PANE = {"features", "pipeline_apply", "mailbox_watch", "claude_roots"}


def effective(key, cfg=None):
    """Validated value from the loaded config (import-time CFG), else the default — for reader modules."""
    default, check, _env = PREFS[key]
    v = (CFG if cfg is None else cfg).get(key)
    if v is None or v == "" or v == []:
        return default
    try:
        return check(v)
    except ValueError as e:
        warn_once("pref:" + key, "Config {key} is invalid, default used ({err})", vars={"key": key, "err": e})
        return default


def saved(key):
    """Validated value of `key` in the config file now (not the import-time one), else the default."""
    default, check, _env = PREFS[key]
    data, _err = _read_file()
    v = (data or {}).get(key)
    if v is None or v == "" or v == []:
        return default
    try:
        return check(v)
    except ValueError:
        return default


def compact_hist(cfg=None):
    """((0, None), (local-midnight ts, window|None), ...) for live_win.COMPACT_HIST."""
    rows = effective("compact_history", cfg)
    return ((0, None),) + tuple((datetime.strptime(d, "%Y-%m-%d").timestamp(), n) for d, n in rows)


def _path():
    if CONFIG_PATH:
        return CONFIG_PATH
    import mailbox_config
    return mailbox_config.config_path()


def _read_file():
    """(raw dict, error) — a missing file is {}; a broken one is an error (never overwritten)."""
    try:
        with open(_path(), encoding="utf-8-sig") as f:     # a leading BOM (Windows editors) is not an error
            d = json.load(f)
    except FileNotFoundError:
        return {}, None
    except (OSError, ValueError) as e:
        return None, "config file unreadable (%s) — fix it by hand" % type(e).__name__
    if not isinstance(d, dict):
        return None, "config file top level is not an object — fix it by hand"
    return d, None


def prefs_get():
    """GET /api/prefs body."""
    data, err = _read_file()
    keys = {}
    for k, (default, check, env) in PREFS.items():
        if k in PREFS_OWN_PANE:
            continue
        if env and os.environ.get(env):
            keys[k] = {"value": os.environ[env], "default": default, "src": "env", "env": env, "restart": True}
            continue
        src, val = "default", default
        if data and data.get(k) not in (None, "", []):
            try:
                val, src = check(data[k]), "file"
            except ValueError:
                val = default
        keys[k] = {"value": val, "default": default, "src": src, "restart": True}
    out = {"ok": True, "path": _path(), "keys": keys}
    try:
        out["mailbox_watch"] = _v_watch((data or {}).get("mailbox_watch") or {})
    except ValueError:
        out["mailbox_watch"] = dict(PREFS["mailbox_watch"][0], projects={})
    if err:
        out["err"] = err
    return out


def _write(data):
    p = _path()
    if os.path.exists(p):
        shutil.copy2(p, p + ".bak")
    # user-edited config: keep its mode (0644 when new), not _atomic_write's 0600
    _atomic_write(p, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
                  prefix=".config-local.", mkdir=True, mode=0o644, like=p)


def compact_hist_append(day, window):
    """Add [day, window] to config compact_history (ascending; the same date is replaced) -> error string or None."""
    with _LOCK:
        data, err = _read_file()
        if err:
            return err
        try:
            rows = _v_hist(data.get("compact_history") or [])
        except ValueError as e:
            return "compact_history invalid (%s) — not updated" % e
        rows = sorted([r for r in rows if r[0] != day] + [[day, window]], key=lambda r: r[0])[-COMPACT_MAX_ROWS:]
        data["compact_history"] = rows
        try:
            _write(data)
        except OSError as e:
            return "config write failed (%s)" % type(e).__name__
    return None


def prefs_set(req):
    """POST /api/prefs/set {key, value} | {key, reset: true} -> (code, out)."""
    if not isinstance(req, dict) or req.get("key") not in PREFS:
        return 400, {"ok": False, "err": "unknown key"}
    key = req["key"]
    default, check, env = PREFS[key]
    if env and os.environ.get(env):
        return 400, {"ok": False, "err": "set by env %s — change it there" % env}
    reset = req.get("reset") is True
    if not reset:
        if "value" not in req:
            return 400, {"ok": False, "err": "value missing"}
        try:
            val = check(req["value"])
        except ValueError as e:
            return 400, {"ok": False, "err": str(e)}
    with _LOCK:
        data, err = _read_file()
        if err:
            return 400, {"ok": False, "err": err}
        if reset:
            data.pop(key, None)
            val = default
        else:
            data[key] = val
        try:
            _write(data)
        except OSError as e:
            warn_once("prefs-write", "Could not write the config file ({err})",
                      vars={"err": f"{type(e).__name__}: {e}"})
            return 500, {"ok": False, "err": "write failed (%s)" % type(e).__name__}
    return 200, {"ok": True, "value": val, "restart": True}
