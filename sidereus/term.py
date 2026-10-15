"""«To terminal»: bring a live session's terminal tab to the front (iTerm2 / Terminal.app / Orca).
Detection is metadata only (tty + TERM_PROGRAM of the claude pid). Focus runs a fixed AppleScript with the tty
as an argv item — never text injection (AGENTS.md rule 7). Orca: fixed `orca terminal switch` argv, same rule. Owns `TERM_CFG_FILE`, `_TTY_CACHE`, `_TTY_FAIL`, `_TTY_LOCK`, `_JUMP_FAILS`."""
import os
import re
import shutil
import subprocess
import threading
import time
from sidereus.config import IS_MAC, IS_WIN
from sidereus.warn import warn_once
from sidereus.bus import _load, _save_json
from sidereus.live_probe import _UUID_RE, _av_cache, _ps_snap_cache, _ps_snap, agent_view

TERM_CFG_FILE = "term-cfg.json"            # under DATA_DIR, via bus._load/_save_json
TERM_APPS = ("auto", "iterm", "apple", "orca", "off")
TTY_RE = re.compile(r"^ttys?\d{1,4}$")
TTY_TTL = 60.0                             # tty/env of a pid never changes; re-probe only to bound pid reuse
TTY_FAIL_TTL = 30.0                        # after a failed ps, do not fork again this long (poll path)
_JUMP_FAILS = {}                           # how -> failed jumps since start (count carried in the viewer.err line)
TTY_TIMEOUT = 3
FOCUS_TIMEOUT = 5
_TTY_CACHE = {}                            # pid(str) -> (probed at, tty or None, app, orca handle or None)
_TTY_FAIL = [0.0]
_TTY_LOCK = threading.Lock()
_ENV_PROG = re.compile(r"(?:^|\s)TERM_PROGRAM=(\S+)")
_ENV_LCT = re.compile(r"(?:^|\s)LC_TERMINAL=(\S+)")
_ENV_ORCA = re.compile(r"(?:^|\s)ORCA_TERMINAL_HANDLE=(\S+)")
# ⚠The handle becomes an argv item of the orca CLI: no leading '-', no spaces, bounded. It stays server-side (never in `term`).
ORCA_HANDLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
ORCA_BUNDLE = "com.stablyai.orca"
ORCA_CLIS = ("orca", "orca-ide")           # orca-ide = Linux binary name

# ⚠The tty arrives only as `item 1 of argv` — never format it into the script text.
_SCRIPT_ITERM = """on run argv
set t to item 1 of argv
if application "iTerm2" is not running then return "notrunning"
tell application "iTerm2"
repeat with w in windows
repeat with tb in tabs of w
repeat with s in sessions of tb
if (tty of s) is t then
select w
select tb
select s
activate
return "ok"
end if
end repeat
end repeat
end repeat
end tell
return "notfound"
end run"""
_SCRIPT_APPLE = """on run argv
set t to item 1 of argv
if application "Terminal" is not running then return "notrunning"
tell application "Terminal"
repeat with w in windows
repeat with tb in tabs of w
if (tty of tb) is t then
set selected of tb to true
set index of w to 1
activate
return "ok"
end if
end repeat
end repeat
end tell
return "notfound"
end run"""
_SCRIPTS = {"iterm": _SCRIPT_ITERM, "apple": _SCRIPT_APPLE}


def term_cfg():
    """Saved `termApp` (auto|iterm|apple|orca|off); anything else reads as auto."""
    v = (_load(TERM_CFG_FILE, {}) or {})
    v = v.get("termApp") if isinstance(v, dict) else None
    return v if v in TERM_APPS else "auto"


def term_set(req):
    """`POST /api/term/set` body `{termApp}` -> (code, out)."""
    v = req.get("termApp") if isinstance(req, dict) else None
    if v not in TERM_APPS:
        return 400, {"ok": False, "err": "termApp must be auto|iterm|apple|orca|off"}
    _save_json(TERM_CFG_FILE, {"termApp": v})
    return 200, {"ok": True, "termApp": v}


def app_of_env(line):
    """TERM_PROGRAM (last one — env follows argv in `ps -E`) -> iterm | apple | orca | other."""
    m = _ENV_PROG.findall(line)
    prog = m[-1] if m else ""
    if prog == "Orca":
        return "orca"
    if prog == "iTerm.app":
        return "iterm"
    if prog == "Apple_Terminal":
        return "apple"
    lct = _ENV_LCT.findall(line)
    if not prog and lct and lct[-1] == "iTerm2":
        return "iterm"
    return "other"


def orca_handle_of_env(line):
    """Last ORCA_TERMINAL_HANDLE in a `ps -E` line, or None if absent or not a safe id."""
    m = _ENV_ORCA.findall(line or "")
    h = m[-1] if m else ""
    return h if ORCA_HANDLE_RE.match(h) else None


def _sid_pids(av, snap):
    """sid -> [pid, ...]: official `claude agents` answers first, then argv `--resume <sid>` of other claude pids."""
    out = {}
    for pid, it in (av or {}).items():
        sid = it.get("sessionId") if isinstance(it, dict) else ""
        if sid:
            out.setdefault(sid, []).append(str(pid))
    known = {str(p) for p in (av or {})}    # ⚠av keys may be int, ps pids str
    for pid, _pp, cmd in snap or []:
        parts = cmd.split()
        if not parts or os.path.basename(parts[0]) != "claude" or str(pid) in known:
            continue
        m = _UUID_RE.search(cmd)
        if m:
            out.setdefault(m.group(0), []).append(str(pid))
    return out


def _probe(pids, force=False):
    """One `ps -Ewwo pid=,tty=,command=` for pids not cached or past TTL -> fills `_TTY_CACHE`. ⚠Failures cached (poll path).
    ⚠A failed re-probe keeps the previous entry: a pid's tty never changes, and dropping it first turned a ps timeout under
    load into term=None (button fell back to «Copy command»). Only a ps that answers without the pid marks it gone.
    `force` = request path: ignore the poll fail cache and evict nothing else."""
    now = time.time()
    with _TTY_LOCK:
        if not force:
            for p in [p for p, v in _TTY_CACHE.items() if p not in pids and now - v[0] > TTY_TTL]:
                _TTY_CACHE.pop(p, None)
        want = [p for p in pids if p.isdigit() and (p not in _TTY_CACHE or now - _TTY_CACHE[p][0] > TTY_TTL)][:64]
        if not want or not IS_MAC or (not force and now - _TTY_FAIL[0] < TTY_FAIL_TTL):
            return
        try:
            txt = subprocess.run(["ps", "-Ewwo", "pid=,tty=,command=", "-p", ",".join(sorted(want, key=int))],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace",
                                 timeout=TTY_TIMEOUT).stdout
        except Exception as e:
            _TTY_FAIL[0] = now
            warn_once("term-probe", "terminal tab lookup failed ({err})", vars={"err": type(e).__name__}, soft=True)
            return
        seen = set()
        for ln in txt.splitlines():
            parts = ln.split(None, 2)
            if len(parts) < 2:
                continue
            tty = parts[1] if TTY_RE.match(parts[1]) else None
            env = parts[2] if len(parts) > 2 else ""
            app = app_of_env(env)
            _TTY_CACHE[parts[0]] = (now, tty, app, orca_handle_of_env(env) if app == "orca" else None)
            seen.add(parts[0])
        for p in want:
            if p not in seen:
                _TTY_CACHE[p] = (now, None, "other", None)   # gone pid — no re-probe until TTL


def _term_of(pids):
    """First cached `{app, tty}` among `pids`, or None. ⚠No orca handle — this dict goes to the page."""
    for pid in pids:
        hit = _TTY_CACHE.get(pid)
        if hit and (hit[1] or hit[3]):
            return {"app": hit[2], "tty": hit[1]}
    return None


def _resolve(sid):
    """Request-time re-lookup for a row with no `term` (new or /clear-changed sid) -> (pid found, term or None).
    One bounded pass on a click only (no extra polling): cached official list / ps snapshot when fresh, then one forced ps."""
    try:
        av = agent_view()
    except Exception:
        av = _av_cache[1]
    try:
        snap = _ps_snap()
    except Exception:
        snap = _ps_snap_cache[1]
    pids = _sid_pids(av, snap).get(sid, [])
    if not pids:
        return False, None
    _probe(set(pids), force=True)
    return True, _term_of(pids)


def term_attach(rows):
    """Set `row["term"] = {app, tty}` (or None) on Claude rows. ⚠Reads live_probe's caches only — never forks them."""
    sp = _sid_pids(_av_cache[1], _ps_snap_cache[1])
    _probe({p for ps in sp.values() for p in ps})
    for r in rows:
        if r.get("ext"):
            continue
        r["term"] = None
        if r.get("state") == "done":
            continue
        r["term"] = _term_of(sp.get(r.get("sid") or "", []))


def _orca_handle(sid):
    """Server-side handle for `sid` from the probe cache (never from the request or the row)."""
    for pid in _sid_pids(_av_cache[1], _ps_snap_cache[1]).get(sid, []):
        hit = _TTY_CACHE.get(pid)
        if hit and hit[3]:
            return hit[3]
    return None


def _orca_cli():
    """`orca` / `orca-ide` on PATH or the usual install dirs — launchd's PATH lacks Homebrew and ~/.local/bin."""
    # ⚠absolute entries only: a relative PATH entry (".") would resolve a planted `orca` against the server's cwd
    dirs = [d for d in (os.environ.get("PATH") or "").split(os.pathsep) if d and os.path.isabs(d)]
    dirs += [os.path.expanduser("~/.local/bin")]
    if not IS_WIN:
        dirs += ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"]
    path = os.pathsep.join(dirs)
    for name in ORCA_CLIS:
        hit = shutil.which(name, path=path)
        if hit:
            return hit
    return None


def _focus_orca(cmd, handle):
    """Orca: `terminal switch` (then the older `terminal focus`) by handle; else bring the app forward only.
    Focus only — no input, spawn or kill against the session (AGENTS.md rule 7). ⚠Never `terminal list/show` (content preview)."""
    cli = _orca_cli() if handle else None
    if cli:
        for verb in ("switch", "focus"):
            try:
                r = subprocess.run([cli, "terminal", verb, "--terminal", handle],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   timeout=FOCUS_TIMEOUT)
            except Exception:
                break
            if r.returncode == 0:
                return 200, {"ok": True, "how": "focused", "cmd": cmd}
            if "unknown" not in ((r.stdout or "") + (r.stderr or "")).lower():
                break                             # switch exists but failed (stale handle) — focus would fail too
    if not IS_MAC:
        return 200, {"ok": False, "how": "unsupported", "cmd": cmd}
    try:
        r = subprocess.run(["open", "-b", ORCA_BUNDLE], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=FOCUS_TIMEOUT)
    except Exception as e:
        return 200, {"ok": False, "how": "error", "cmd": cmd, "err": type(e).__name__}
    if r.returncode != 0:
        return 200, {"ok": False, "how": "notfound", "cmd": cmd, "err": "orca not installed"}
    return 200, {"ok": False, "how": "app", "cmd": cmd, "hint": "cli" if not cli else "handle"}


def term_focus(sid, rows, cfg=None):
    """Bring `sid`'s tab forward -> (code, out). The caller validated the sid shape; tty comes from `rows` (or `_resolve`) only.
    Every failure but «off» goes to viewer.err (how + short reason, never conversation text)."""
    code, out = _focus(sid, rows, cfg)
    how = out.get("how")
    if not out.get("ok") and how != "off":
        n = _JUMP_FAILS[how] = _JUMP_FAILS.get(how, 0) + 1
        why = str(out.get("err") or out.get("hint") or "-").replace("\n", " ")[:80]
        warn_once("term-jump-" + str(how), "terminal jump failed ({how}: {why}; {n} so far)",
                  vars={"how": how, "why": why, "n": n}, soft=True)
    return code, out


def _focus(sid, rows, cfg):
    cmd = "claude --resume " + sid
    row = next((r for r in rows or [] if r.get("sid") == sid and not r.get("ext") and r.get("state") != "done"), None)
    if row is None:   # ⚠notfound, not 400: the page reads a 400 here as a permission problem
        return 200, {"ok": False, "how": "notfound", "cmd": cmd, "err": "session not live on screen"}
    t = row.get("term")
    app = cfg or term_cfg()
    if app == "off":
        return 200, {"ok": False, "how": "off", "cmd": cmd}
    if not isinstance(t, dict):
        found, t = _resolve(sid)
        if not found:
            return 200, {"ok": False, "how": "notfound", "cmd": cmd, "err": "no process for session"}
        if not isinstance(t, dict):
            return 200, {"ok": False, "how": "unsupported", "cmd": cmd}
    if app == "auto":
        app = t.get("app")
    if app == "orca":
        return _focus_orca(cmd, _orca_handle(sid))
    tty = t.get("tty")
    if not isinstance(tty, str) or not TTY_RE.match(tty):
        return 200, {"ok": False, "how": "notfound", "cmd": cmd, "err": "bad tty"}
    if app not in _SCRIPTS or not IS_MAC:
        return 200, {"ok": False, "how": "unsupported", "cmd": cmd}
    try:
        r = subprocess.run(["osascript", "-e", _SCRIPTS[app], "/dev/" + tty],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=FOCUS_TIMEOUT)
    except subprocess.TimeoutExpired:
        # ⚠Not a permission problem: the script walks every window/tab and a busy app answers late.
        return 200, {"ok": False, "how": "timeout", "cmd": cmd, "err": "osascript timeout"}
    except Exception as e:
        return 200, {"ok": False, "how": "error", "cmd": cmd, "err": type(e).__name__}
    res = (r.stdout or "").strip()
    if res == "ok":
        return 200, {"ok": True, "how": "focused", "cmd": cmd}
    if res in ("notfound", "notrunning"):
        return 200, {"ok": False, "how": "notfound", "cmd": cmd, "err": res}
    return 200, {"ok": False, "how": "error", "cmd": cmd, "err": (r.stderr or res or "osascript failed").strip()[:200]}
