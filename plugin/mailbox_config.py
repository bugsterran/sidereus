#!/usr/bin/env python3
"""Install-specific settings for the mailbox tools (identity, default room, paths).

Lookup: $MAILBOX_CONFIG -> $MAILBOX_DIR/config.local.json -> ~/.mailbox-mcp/config.local.json
(the first one that is *set* wins). config.local.json is not shipped; `sidereus start` creates it from config.example.json.
Precedence for callers: env var > config file > DEFAULTS.
Paths: data (bus, cursors, presence, logs, config.local.json) live in data_dir() = $MAILBOX_DIR or
~/.mailbox-mcp; code (other scripts, imports) lives in CODE_DIR = this file's folder. They may differ.

    import mailbox_config
    cfg = mailbox_config.load()          # DEFAULTS merged with the file, cached
    mailbox_config.get("default_room")

Stdlib only, Python 3.9. A missing or broken file never raises: defaults are used and one
warning goes to stderr.
"""
import copy
import json
import os
import sys

DEFAULTS = {
    "self": {
        "ids": [],        # ids this install posts as (MAILBOX_SELF); first one is the monitor identity
        "aliases": [],    # addresses that count as "to me" (MAILBOX_ALIASES)
    },
    "alias_strip_prefixes": [],   # MAILBOX_ME=pre-x also answers to "x" for each prefix listed
    "default_room": "general",
    "viewer_me": "사용자",
    "readcheck_peer": "",
    "saver_view_path": "~/.claude/hooks/.saver-view.json",
    "hook_session_patterns": [],
    "launchd_label_prefix": "io.sidereus",   # launchd labels are "<prefix>.viewer" etc.
    # Full-label overrides per job ("" = "<prefix>.<name>"). ⚠Keys must be listed here: _merge drops unknown ones.
    "launchd_labels": {"viewer": "", "watch": "", "databackup": ""},
    "quota_probe": False,   # paid Haiku call while the usage API 429s (env SIDEREUS_QUOTA_PROBE overrides)
    "quota_lookup": True,   # read the OAuth token from the keychain for the quota API (env SIDEREUS_QUOTA_LOOKUP overrides)
    "keep_awake": True,     # hold caffeinate while sessions work
    # «Preferences» (sidereus/prefs.py validates; the viewer applies them after a restart).
    "saver_hook_dir": "~/.claude/hooks",   # folder of .saver-force.json / .saver-goal.json
    "compact_history": [],                 # [["YYYY-MM-DD", int|null], ...]; [] = current setting only
    "port": 8799,                          # viewer port; env SIDEREUS_PORT > this > 8799 (resolve with port())
}
DEFAULT_PORT = 8799
_PAIR_LISTS = ("compact_history",)   # lists of [str, int|null] rows, not strings
# ⚠Top-level keys whose shape sidereus/prefs.py owns (nested dicts / lists of objects): passed through raw, unvalidated,
# with no «unknown key» warning. Must equal prefs.PREFS_OWN_PANE (tests/test_prefs_mailwatch.py asserts it).
# ⚠Dropping them hides saved values from prefs.effective() (CFG) — features toggles were silently ignored that way.
_PREFS_OWN = ("features", "pipeline_apply", "mailbox_watch", "claude_roots")

CODE_DIR = os.path.dirname(os.path.abspath(__file__))


def asset_dir(code=CODE_DIR):
    """Folder holding web/, docs/, hooks/, mcp/: `code` itself in a clone, else `code/sidereus/_bundle` (pipx/uv install).
    ⚠Clone first — a clone must resolve exactly as before, even if a stale _bundle sits next to it."""
    return code if os.path.isdir(os.path.join(code, "web")) else os.path.join(code, "sidereus", "_bundle")

_cache = None
_warned = set()
FILE_OK = None   # False after a missing/broken file (already warned); callers skip follow-up warnings


def _warn_once(key, msg):
    if key in _warned:
        return
    _warned.add(key)
    print(f"⚠ mailbox_config: {msg}", file=sys.stderr, flush=True)


def data_dir():
    return os.path.expanduser(os.environ.get("MAILBOX_DIR") or "~/.mailbox-mcp")


def instance_id(d=None):
    """Short id of a data dir. The viewer sends it as `X-Sidereus-Instance` so `sidereus start` can tell its own viewer from another."""
    import hashlib
    real = os.path.normcase(os.path.realpath(os.path.expanduser(d or data_dir())))
    return hashlib.sha256(real.encode("utf-8")).hexdigest()[:16]


def config_path():
    p = os.environ.get("MAILBOX_CONFIG")
    if p:
        return os.path.expanduser(p)
    return os.path.join(data_dir(), "config.local.json")


def _merge(base, over, where=""):
    # ⚠ a value whose type differs from the default is dropped (warned), so callers can trust types.
    out = copy.deepcopy(base)
    for k, v in over.items():
        if k.startswith("_"):
            continue                      # "_comment" style keys in the example file
        if k not in base:
            if not where and k in _PREFS_OWN:
                out[k] = copy.deepcopy(v)   # validated by sidereus/prefs.py (effective/saved), not here
                continue
            _warn_once(f"unknown:{where}{k}", f"unknown key '{where}{k}' ignored")
            continue
        if isinstance(base[k], dict):
            if isinstance(v, dict):
                out[k] = _merge(base[k], v, f"{where}{k}.")
            else:
                _warn_once(f"type:{where}{k}", f"'{where}{k}' must be an object — default used")
        elif isinstance(base[k], list):
            if isinstance(v, list) and all(isinstance(x, list if k in _PAIR_LISTS else str) for x in v):
                out[k] = copy.deepcopy(v)
            else:
                _warn_once(f"type:{where}{k}", f"'{where}{k}' must be a list of strings — default used")
        elif isinstance(base[k], bool):
            if isinstance(v, bool):
                out[k] = v
            else:
                _warn_once(f"type:{where}{k}", f"'{where}{k}' must be true or false — default used")
        elif isinstance(base[k], int):
            if isinstance(v, int) and not isinstance(v, bool):
                out[k] = v
            else:
                _warn_once(f"type:{where}{k}", f"'{where}{k}' must be an integer — default used")
        elif isinstance(v, str):
            out[k] = v
        else:
            _warn_once(f"type:{where}{k}", f"'{where}{k}' must be a string — default used")
    return out


def load(reload=False):
    global _cache, FILE_OK
    if _cache is not None and not reload:
        return _cache
    path = config_path()
    data = {}
    FILE_OK = True
    try:
        with open(path, encoding="utf-8-sig") as f:     # a leading BOM (Windows editors) is not an error
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("top level is not an object")
    except FileNotFoundError:
        # --demo never creates or reads the config, so a missing file is expected there — stay silent.
        if "--demo" not in sys.argv:
            _warn_once("missing", f"{path} not found — using defaults (`python3 -m sidereus start` creates it)")
        data, FILE_OK = {}, False
    except Exception as e:
        _warn_once("broken", f"{path} unreadable ({type(e).__name__}: {e}) — using defaults")
        data, FILE_OK = {}, False
    _cache = _merge(DEFAULTS, data)
    return _cache


def get(key, default=None):
    return load().get(key, default)


def env_list(name, fallback):
    """Comma-separated env var if set, else the config list."""
    raw = os.environ.get(name)
    if raw is not None and raw.strip():
        return [x.strip() for x in raw.split(",") if x.strip()]
    return list(fallback)


def valid_port(v):
    """int port in 1..65535, else None (bools and strings of digits are handled by the caller)."""
    return v if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 65535 else None


def port():
    """Viewer port: env SIDEREUS_PORT > config `port` > 8799. ⚠The single source for every client and the server."""
    raw = (os.environ.get("SIDEREUS_PORT") or "").strip()
    if raw.isdigit() and valid_port(int(raw)):
        return int(raw)
    return valid_port(get("port")) or DEFAULT_PORT


def launchd_label(name):
    return (get("launchd_labels") or {}).get(name) or f"{get('launchd_label_prefix')}.{name}"


if __name__ == "__main__":
    # `--get KEY` / `--label NAME` / `--port` print one value for shell scripts.
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # ⚠Windows pipes use the ANSI code page; values may hold Korean
    except Exception:
        pass
    if len(sys.argv) == 3 and sys.argv[1] == "--get":
        v = get(sys.argv[2])
        print(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
        sys.exit(0)
    if len(sys.argv) == 2 and sys.argv[1] == "--port":
        print(port())
        sys.exit(0)
    if len(sys.argv) == 3 and sys.argv[1] == "--label":
        print(launchd_label(sys.argv[2]))
        sys.exit(0)
    print(config_path())
    print(json.dumps(load(), ensure_ascii=False, indent=2))
