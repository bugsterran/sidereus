#!/usr/bin/env python3
"""Claude Code PreToolUse hook (Edit|Write|MultiEdit|NotebookEdit): tells the session when ANOTHER live session
edited the same file recently, so it learns about a conflict without having to call sidereus_file_peers.

- Asks the local viewer (`GET /api/agent/file`, same endpoint as mcp/sidereus_mcp.py sidereus_file_peers).
- Emits one line as hookSpecificOutput.additionalContext. ⚠Never blocks (no permissionDecision) — advice only.
- Silent (empty stdout, exit 0) when the viewer is down/slow/erroring, the tool is not an edit, or no other
  LIVE session edited the file within the viewer's window (30 min).
- ⛔Metadata only: sid8, project name, minutes ago, uncommitted flag — never message text or tool input.
- Same (session, file, peer) is announced at most once per NOTICE_TTL_S (state file in the data dir, pruned).
Stdlib only (3.9).
"""
import json
import os
import sys
import tempfile
import time
import urllib.parse
import urllib.request


def sidereus_port():
    """Viewer port: env SIDEREUS_PORT > config `port` > 8799. Mirrors mailbox_config.port() but reads the JSON directly
    (⚠standalone and fast: no repo import). Config: $MAILBOX_CONFIG, else ($MAILBOX_DIR or ~/.mailbox-mcp)/config.local.json."""
    raw = (os.environ.get("SIDEREUS_PORT") or "").strip()
    if raw.isdigit() and 1 <= int(raw) <= 65535:
        return int(raw)
    path = os.environ.get("MAILBOX_CONFIG") or os.path.join(os.environ.get("MAILBOX_DIR") or "~/.mailbox-mcp",
                                                          "config.local.json")
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as f:
            v = json.load(f).get("port")
        if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 65535:
            return v
    except Exception:
        pass
    return 8799


BASE = "http://127.0.0.1:%d" % sidereus_port()
TIMEOUT_S = 0.5      # ⚠Runs before EVERY edit — a slow/cold viewer must cost at most this, then pass silently.
NOTICE_TTL_S = 600   # same (session, file, peer) is not repeated within 10 min
PRUNE_S = 3600       # state entries older than this are dropped on each write
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
# Mirrors mailbox_config.data_dir() (not imported: keep the hook standalone and fast).
STORE = os.path.expanduser(os.environ.get("MAILBOX_DIR") or "~/.mailbox-mcp")
STATE = os.path.join(STORE, ".file-peers-notice.json")


def fetch(path, cwd):
    """GET /api/agent/file -> dict, or None on any failure."""
    url = BASE + "/api/agent/file?" + urllib.parse.urlencode({"path": path, "cwd": cwd or ""})
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_S) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d if isinstance(d, dict) and d.get("ok") else None
    except Exception:
        return None


def _clean(s, n=40):
    return " ".join(str(s or "").split())[:n]


def _ago(sec):
    try:
        m = int(sec) // 60
    except (TypeError, ValueError):
        return "recently"
    return "<1 min ago" if m < 1 else "%d min ago" % m


def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_state(d):
    try:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STATE), prefix=".tmp-fpn-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, STATE)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass


def decide(inp, now=None):
    """Hook input dict -> notice line or ''. Updates the dedup state when it returns a line."""
    now = time.time() if now is None else now
    if inp.get("tool_name") not in EDIT_TOOLS:
        return ""
    ti = inp.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("notebook_path") if isinstance(ti, dict) else ""
    if not path or not isinstance(path, str):
        return ""
    cwd = inp.get("cwd") or ""
    if not path.startswith("/") and cwd:
        path = os.path.join(cwd, path)
    path = os.path.normpath(path)
    sid = str(inp.get("session_id") or "")
    me8 = sid[:8]   # Claude session ids are UUIDs; the viewer's sid8 is their first 8 chars
    d = fetch(path, cwd)
    if not d:
        return ""
    peers = {}      # sid8 -> newest live editor row (editors come newest first)
    for e in d.get("editors") or []:
        if isinstance(e, dict) and e.get("live") and e.get("sid8") and e.get("sid8") != me8:
            peers.setdefault(e["sid8"], e)
    if not peers:
        return ""
    st = {k: v for k, v in load_state().items() if isinstance(v, (int, float)) and now - v < PRUNE_S}
    new = [e for p8, e in peers.items() if now - st.get("%s|%s|%s" % (sid, path, p8), 0) >= NOTICE_TTL_S]
    if not new:
        return ""
    for e in new:
        st["%s|%s|%s" % (sid, path, e["sid8"])] = now
    save_state(st)
    who = ", ".join("%s (%s) %s" % (_clean(e["sid8"], 12), _clean(e.get("project")) or "?", _ago(e.get("agoSec")))
                    for e in new[:3])
    more = " +%d more" % (len(new) - 3) if len(new) > 3 else ""
    unc = " (uncommitted)" if d.get("uncommitted") else ""
    verb = "edited" if len(new) == 1 else "each edited"
    return "Sidereus: %s%s %s this file%s — check before overwriting." % (who, more, verb, unc)


def main():
    try:
        raw = sys.stdin.read()
        inp = json.loads(raw) if raw.strip() else {}
        if not isinstance(inp, dict):
            return
        line = decide(inp)
        if line:
            sys.stdout.write(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "additionalContext": line}}, ensure_ascii=False))
    except Exception:
        pass


if __name__ == "__main__":
    for _s in (sys.stdin, sys.stdout):   # ⚠Windows pipes default to the ANSI codepage; hook JSON is UTF-8
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    main()
    sys.exit(0)
