"""Pipeline tab project allow-list + the person-added project store (split from `pipeline.py`, no behaviour change).

`allowed_projects()` = known_projects() ∪ live sessions' repos ∪ Sidereus ∪ projects added with «+ Add project»
(POST /api/pipelines/projects/add|remove, list entries only — nothing on disk is touched).
"""
import json
import os
import subprocess
import threading

from sidereus import prefs
from sidereus.bus import _atomic_write
from sidereus.config import CODE_DIR, DATA_DIR, IS_MAC, IS_WIN
from sidereus.toolinv import known_projects
from sidereus.work import _allowed_cwds
from sidereus.warn import warn_once

PROJ_STORE = None            # None = DATA_DIR/pipeline-projects.json (projects the person added); ⚠tests set a tmp file
USER_HOME = None             # None = ~ ; ⚠tests set a tmp dir
PROJ_STORE_MAX = 50
_STORE_LOCK = threading.Lock()


def _proj_ok(proj):
    return isinstance(proj, str) and proj in allowed_projects()


def allowed_projects():
    """Exact-match allow-list = the pipeline tab's chips: known_projects() ∪ live sessions' repos ∪ Sidereus itself.
    ★2026-10-01 a chip from a session's `repos` was refused (not a cwd). Real dirs only."""
    out = set(known_projects()) | {CODE_DIR} | set(_remembered())
    for r in _allowed_cwds().values():   # never raises: falls back to its last good value
        out |= set(x for x in (r.get("repos") or []) if isinstance(x, str))
    return sorted(p for p in out if os.path.isabs(p) and os.path.isdir(p))


def _store_path():
    return PROJ_STORE or os.path.join(DATA_DIR, "pipeline-projects.json")


def _read_store():
    try:
        with open(_store_path(), encoding="utf-8") as f:
            v = json.load(f)
    except (OSError, ValueError):
        return []
    return [p for p in v if isinstance(p, str)] if isinstance(v, list) else []


def _home():
    return os.path.realpath(USER_HOME or os.path.expanduser("~"))


def _addable(p):
    """Real absolute dir strictly inside the user's home ("/" and home itself refused)."""
    h = _home()
    return isinstance(p, str) and os.path.isabs(p) and os.path.isdir(p) and p != h and p.startswith(h + os.sep)


def _remembered():
    """Projects the person added with «+ Add project» that still exist.
    Explicit list only, never automatic."""
    return [p for p in _read_store() if _addable(p)]


def _write_store(paths):
    _atomic_write(_store_path(), json.dumps(paths, ensure_ascii=False, indent=1).encode("utf-8"), mkdir=True)


def add_project(req):
    """(code, body) for POST /api/pipelines/projects/add {path}. ~ expanded, realpath, must be a dir inside home. ⚠Caller checks Origin."""
    raw = req.get("path") if isinstance(req, dict) else None
    if not isinstance(raw, str) or not raw.strip() or "\0" in raw or len(raw) > 1024:
        return 400, {"ok": False, "err": "Enter a path"}
    p = os.path.expanduser(raw.strip())
    if not os.path.isabs(p):
        return 400, {"ok": False, "err": "Use an absolute path or one starting with ~"}
    p = os.path.realpath(p)
    if not os.path.isdir(p):
        return 400, {"ok": False, "err": "No such folder"}
    if not _addable(p):
        return 400, {"ok": False, "err": "Only project folders inside your home folder can be added"}
    with _STORE_LOCK:
        old = _read_store()
        new = ([p] + [x for x in old if x != p])[:PROJ_STORE_MAX]
        if len(old) >= PROJ_STORE_MAX and p not in old:
            return 400, {"ok": False, "err": "Up to %d projects can be added" % PROJ_STORE_MAX}  # ⚠I18N key in 06-i18n-v.js assumes 50
        try:
            _write_store(new)
        except OSError as e:
            return 500, {"ok": False, "err": "write failed (%s)" % type(e).__name__}
    return 200, {"ok": True, "path": p, "added": new}


def remove_project(req):
    """(code, body) for POST /api/pipelines/projects/remove {path}: drops the list entry only, nothing on disk."""
    p = req.get("path") if isinstance(req, dict) else None
    with _STORE_LOCK:
        old = _read_store()
        if not isinstance(p, str) or p not in old:
            return 400, {"ok": False, "err": "Not in the list"}
        new = [x for x in old if x != p]
        try:
            _write_store(new)
        except OSError as e:
            return 500, {"ok": False, "err": "write failed (%s)" % type(e).__name__}
    return 200, {"ok": True, "added": new}


DIRS_MAX = 500


def _dir_flags(p):
    def has(n):
        return os.path.exists(os.path.join(p, n))
    return has(".git"), has(".claude") or has("AGENTS.md") or has("CLAUDE.md")


PICK_TIMEOUT = 300
_PICK_LOCK = threading.Lock()   # one native dialog at a time
# ⚠Fixed scripts, no request data inside. "System Events" owns the dialog so `activate` brings it in front of the browser;
#   `with invisibles` shows dot-folders (the in-page browser hides them by default).
_MAC_ARGV = ["osascript", "-e", 'tell application "System Events"', "-e", "activate",
             "-e", 'set f to choose folder with prompt "Choose a project folder" default location (path to home folder) with invisibles',
             "-e", "end tell", "-e", "return POSIX path of f"]
# A TopMost owner form keeps the dialog above the browser. Hidden folders follow Explorer's «Hidden items» setting.
_WIN_PS = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;Add-Type -AssemblyName System.Windows.Forms;"
           "$o=New-Object System.Windows.Forms.Form -Property @{TopMost=$true;ShowInTaskbar=$false};"
           "$d=New-Object System.Windows.Forms.FolderBrowserDialog;$d.ShowNewFolderButton=$false;"
           "if($d.ShowDialog($o) -eq [System.Windows.Forms.DialogResult]::OK){[Console]::Out.Write($d.SelectedPath)};$o.Dispose()")


def pick_supported():
    return bool(IS_MAC or IS_WIN)


def _run(argv, **kw):
    return subprocess.run(argv, **kw)   # ⚠tests patch this attribute; never a real dialog in tests


def _pick_norm(p):
    """Strip trailing separators except a root ("/", "C:\\")."""
    q = p.rstrip("/\\")
    return p[:len(q) + 1] if not q or (len(q) == 2 and q[1] == ":") else q


# Screen text only (English source, Korean in web/js/06-i18n-v.js); raw stderr/exception names go to the soft warn log.
PICK_ERR_TIMEOUT = "Timed out — the folder dialog was not closed within 5 minutes"
PICK_ERR_PATH = "The chosen path cannot be used"
PICK_ERR_OPEN = "Could not open the folder dialog"


def _pick_fail(detail):
    warn_once("pick-folder", "Folder dialog failed: {err}", soft=True, vars={"err": detail})
    return PICK_ERR_OPEN


def pick_folder(req=None):
    """(code, body) for POST /api/pick-folder: opens the OS folder dialog and returns the chosen absolute path.
    Nothing is added here — the person still presses «Add this folder». ⚠Caller checks Origin. ThreadingHTTPServer: blocks this request only."""
    if not pick_supported():
        return 200, {"ok": False, "unsupported": True}
    if not _PICK_LOCK.acquire(False):
        return 200, {"ok": False, "busy": True}
    try:
        kw = {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace", "timeout": PICK_TIMEOUT}
        if IS_WIN:
            argv = ["powershell", "-NoProfile", "-STA", "-Command", _WIN_PS]
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        else:
            argv = list(_MAC_ARGV)
        try:
            r = _run(argv, **kw)
        except subprocess.TimeoutExpired:
            return 200, {"ok": False, "err": PICK_ERR_TIMEOUT}
        except Exception as e:
            return 200, {"ok": False, "err": _pick_fail(type(e).__name__)}
        out = (r.stdout or "").strip("\r\n")
        if r.returncode != 0:
            if IS_MAC and "-128" in (r.stderr or ""):   # «Cancel» = AppleScript error -128
                return 200, {"ok": True, "cancelled": True}
            return 200, {"ok": False, "err": _pick_fail((r.stderr or "dialog failed").strip()[:200])}
        if not out:
            return 200, {"ok": True, "cancelled": True}   # Windows cancel prints nothing
        if "\n" in out or "\0" in out or len(out) > 1024 or not (os.path.isabs(out) or (IS_WIN and len(out) > 2 and out[1] == ":")):
            return 200, {"ok": False, "err": PICK_ERR_PATH}
        return 200, {"ok": True, "path": _pick_norm(out)}
    finally:
        _PICK_LOCK.release()


def browse_dirs(raw, hidden=False):
    """(code, body) for GET /api/pipelines/projects/dirs?path= — folder names + git/claude flags only (never file names).
    ⚠Same home boundary as _addable, but home itself is browsable (it is the top, parent ""). hidden = dot-folders too."""
    h = _home()
    raw = raw.strip() if isinstance(raw, str) else ""
    if "\0" in raw or len(raw) > 1024:
        return 400, {"ok": False, "msg": "Enter a path"}
    p = os.path.realpath(os.path.expanduser(raw)) if raw else h
    if not os.path.isabs(os.path.expanduser(raw or h)):
        return 400, {"ok": False, "msg": "Use an absolute path or one starting with ~"}
    if p != h and not p.startswith(h + os.sep):
        return 400, {"ok": False, "msg": "Only project folders inside your home folder can be added"}
    if not os.path.isdir(p):
        return 400, {"ok": False, "msg": "No such folder", "path": p}
    try:
        names = os.listdir(p)
    except OSError:
        return 200, {"ok": False, "msg": "Could not read the folder", "path": p}
    out, more = [], False
    for n in sorted((n for n in names if hidden or not n.startswith(".")), key=lambda s: (s.lower(), s)):
        q = os.path.join(p, n)
        if not os.path.isdir(q):
            continue
        if len(out) >= DIRS_MAX:
            more = True
            break
        g, c = _dir_flags(q)
        out.append({"name": n, "git": g, "claude": c})
    return 200, {"ok": True, "path": p, "home": h, "parent": "" if p == h else os.path.dirname(p), "dirs": out, "more": more,
                 "pick": pick_supported()}


def apply_get(proj):
    """«Apply» mode for `proj` as hooks/pipelines_brief.py resolves it: own override, else the global mode."""
    v = prefs.saved("pipeline_apply")
    own = v["projects"].get(proj) if isinstance(proj, str) else None
    return {"mode": own or v["mode"], "global": v["mode"], "own": own}


def apply_set(req):
    """(code, body) for POST /api/pipelines/apply {mode, proj?}: proj = that project's override (mode null drops it), else global.
    ⚠Caller checks Origin. Applies to sessions started afterwards (SessionStart hook)."""
    if not isinstance(req, dict):
        return 400, {"ok": False, "err": "bad request"}
    proj, mode = req.get("proj"), req.get("mode")
    if proj is not None and not _proj_ok(proj):
        return 400, {"ok": False, "err": "unknown project"}
    if mode not in prefs.APPLY_MODES and not (proj is not None and mode is None):
        return 400, {"ok": False, "err": "mode must be auto|ask|off"}
    with _STORE_LOCK:   # ⚠read-modify-write of one prefs key: this module is its only writer
        cur = prefs.saved("pipeline_apply")
        new = {"mode": cur["mode"], "projects": dict(cur["projects"])}
        if proj is None:
            new["mode"] = mode
        elif mode is None:
            new["projects"].pop(proj, None)
        else:
            new["projects"][proj] = mode
        code, out = prefs.prefs_set({"key": "pipeline_apply", "value": new})
    if code != 200:
        return code, out
    return 200, {"ok": True, "apply": apply_get(proj)}
