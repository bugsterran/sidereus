"""Paths, install config, port and platform flags. DATA_DIR is runtime state; CODE_DIR is the repo root (parent of sidereus/)."""
import contextlib
import os
import sys
import threading

# DATA_DIR = runtime state (bus, cursors, caches, logs); CODE_DIR = the repo root (chat_server.py, mailbox_config.py, web/).
# ⚠ Same folder today, but never join code paths with DATA_DIR. Older comments say `HOME` for DATA_DIR, not the user's home.
DATA_DIR = os.environ.get("MAILBOX_DIR") or os.path.expanduser("~/.mailbox-mcp")
CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # ⚠this file is sidereus/config.py — one level up


def claude_home():
    """Claude Code config root: $CLAUDE_CONFIG_DIR, else ~/.claude. ⚠Every reader of the Claude root derives from this."""
    return os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude")


def claude_json():
    """User-level config: $CLAUDE_CONFIG_DIR/.claude.json when that is set, else ~/.claude.json (Claude Code's rule)."""
    d = os.environ.get("CLAUDE_CONFIG_DIR")
    return os.path.join(os.path.expanduser(d), ".claude.json") if d else os.path.expanduser("~/.claude.json")
# First run on a new PC: nothing else creates DATA_DIR (bus writes use mkdir=False). ⚠Never fatal.
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except OSError as _e:
    print(f"⚠ chat_server: cannot create {DATA_DIR} ({_e})", file=sys.stderr, flush=True)
BUS =os.path.join(DATA_DIR, "bus.jsonl")
# Install-specific values come from mailbox_config; ⚠ an import failure must not kill the viewer.
try:
    sys.path.insert(0, CODE_DIR)
    import mailbox_config as _mcfg
    CFG = _mcfg.load()
except Exception as _e:
    print(f"⚠ chat_server: mailbox_config unavailable ({type(_e).__name__}: {_e}) — using defaults",
          file=sys.stderr, flush=True)
    CFG = {}
# ASSET_DIR = where web/, docs/, hooks/, mcp/ are read from: CODE_DIR in a clone, CODE_DIR/sidereus/_bundle in a pipx/uv install.
try:
    ASSET_DIR = _mcfg.asset_dir(CODE_DIR)
except Exception:
    ASSET_DIR = CODE_DIR
IS_CLONE = ASSET_DIR == CODE_DIR   # False = installed package: no repo to point sessions at (pipelines, tour, arch-map)
MINE = list((CFG.get("self") or {}).get("ids") or [])      # our (this session's) ids — right-side bubbles
# Port: --port (below) > env SIDEREUS_PORT > config `port` > 8799, via mailbox_config.port() — the same resolver the clients use.
try:
    PORT = _mcfg.port()
except Exception:
    PORT = 8799
try:
    INSTANCE_ID = _mcfg.instance_id(DATA_DIR)   # sent as X-Sidereus-Instance; sidereus_cli compares it with its own data dir
except Exception:
    INSTANCE_ID = ""
GZIP_MIN = 4096         # below this, compression saves less than the header costs
# ★Mac-only gate — there were 0 branches, so "what is Mac-only" was recounted every time ⇒ collected here.
#   On non-Mac only these features switch off quietly (each function falls back to its "unavailable" value, no exception).
#     · session detection `ps -Ao`·`lsof -d cwd`     ⇒ needs /proc walk
#     · watcher process env `ps -Ewwo`               ⇒ /proc/<pid>/environ
#     · sleep intervals `pmset -g log`               ⇒ journalctl or other power-event log
#     · OAuth token `security find-generic-password` ⇒ libsecret · DPAPI
#     · idle-sleep prevention `caffeinate`           ⇒ systemd-inhibit etc.
#     · boot time `sysctl -n kern.boottime`          ⇒ /proc/stat btime
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"


@contextlib.contextmanager
def file_lock(path):
    """Exclusive lock on `path` (opened for append) for the with-block: fcntl.flock, else msvcrt byte-0 lock."""
    with open(path, "a", encoding="utf-8") as lf:
        try:
            import fcntl
        except ImportError:
            fcntl = None
        if fcntl is not None:
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
            return
        import msvcrt
        lf.seek(0)
        msvcrt.locking(lf.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            lf.seek(0)
            msvcrt.locking(lf.fileno(), msvcrt.LK_UNLCK, 1)


def pid_alive(pid):
    """True = running, False = certainly gone, None = unknown (bad pid or unexpected error)."""
    # ⚠Windows: os.kill(pid, 0) calls TerminateProcess — it kills the target. Use OpenProcess there.
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    if IS_WIN:
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.OpenProcess(0x00100000, False, pid)   # SYNCHRONIZE
            if not h:
                return True if k32.GetLastError() == 5 else False   # ERROR_ACCESS_DENIED = exists
            k32.CloseHandle(h)
            return True
        except Exception:
            return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True                                   # exists under another user
    except (OSError, OverflowError, ValueError):
        return None
    return True
argv = sys.argv[1:]
if "--port" in argv:
    PORT = int(argv[argv.index("--port") + 1])


def viewer_origin(o):
    """True when an Origin header is this viewer's own page (chat_server `_origin_ok` · routes_post relay check)."""
    return (o or "").strip() in ("http://127.0.0.1:%d" % PORT, "http://localhost:%d" % PORT)


_lock = threading.Lock()


# ── Identity and target when the user posts directly ──────────────────────
#   The viewer is **a human's screen**, so it never borrows an agent id — mixed attribution corrupts judgments.
#   Override: env MAILBOX_VIEWER_ME / MAILBOX_VIEWER_ROOM > config viewer_me / default_room > default.
VIEWER_ME = os.environ.get("MAILBOX_VIEWER_ME") or CFG.get("viewer_me") or "사용자"
# ⚠Both default spellings (ko, en) count as «not set»: config.example.json ships "user", so a copied file still follows the UI language.
VIEWER_ME_DEFAULTS = ("사용자", "user")


def viewer_ids(me):
    """Ids matched as the viewer: an explicit name alone, else both default spellings (a language switch keeps old posts mine)."""
    return [me] if me not in VIEWER_ME_DEFAULTS else list(VIEWER_ME_DEFAULTS)


def viewer_me_for(me, lang):
    """Author id for one viewer post: an explicit name as-is, else the default spelling of the page's UI language."""
    return me if me not in VIEWER_ME_DEFAULTS else VIEWER_ME_DEFAULTS[1 if lang == "en" else 0]
ROOM_DEFAULT = os.environ.get("MAILBOX_VIEWER_ROOM") or CFG.get("default_room") or "general"
BUS_PATH = os.path.join(DATA_DIR, "bus.jsonl")
