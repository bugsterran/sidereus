#!/usr/bin/env python3
"""Notification hook (matcher permission_prompt|elicitation_dialog): mark that a Claude Code session is waiting on a permission prompt.

Writes <data dir>/permwait/<session_id>.json = {"sid", "t"[, "tool"]}, or <session_id>.<agent_id>.json = {"sid", "t", "k", "aid"[, "tool"]}
for a subagent's prompt -- never the message, title or tool input (metadata only; "tool" is the PermissionRequest tool_name).
Sidereus shows «Awaiting approval» while the marker is newer than the session's last transcript activity (sidereus/perm_marks.perm_wait).
⚠Claude Code sends this notification 6 s after the dialog opens (cancelled if answered sooner), in every permission mode.
Also accepts the PermissionRequest event. Fail-silent, always exits 0, prints nothing. Stdlib only, Python 3.9.
"""
import json
import os
import re
import sys
import time

# Same derivation as sidereus/config.py DATA_DIR so the server reads the same folder.
DATA_DIR = os.path.expanduser(os.environ.get("MAILBOX_DIR") or "~/.mailbox-mcp")
MARK_DIR = os.path.join(DATA_DIR, "permwait")
SID = re.compile(r"^[0-9a-zA-Z-]{8,64}$")
AID = re.compile(r"^[0-9a-zA-Z_-]{1,64}$")
KEEP_TOOL_S = 15          # the Notification fallback arrives ~6 s after PermissionRequest; keep that marker's tool
PRUNE_S = 7 * 86400


def _is_prompt(ev):
    name = ev.get("hook_event_name") or ""
    if name == "PermissionRequest":
        return True
    # An MCP elicitation dialog also blocks the turn on the user, so it marks the same way.
    return name in ("Notification", "") and ev.get("notification_type") in ("permission_prompt", "elicitation_dialog")


def _kind(ev):
    if (ev.get("hook_event_name") or "") == "PermissionRequest":
        return "req"
    return "elicit" if ev.get("notification_type") == "elicitation_dialog" else "perm"


def _prune(sid, now):
    """Drop this session's subagent markers older than PRUNE_S (one file per agent would otherwise pile up)."""
    pre = sid + "."
    for n in os.listdir(MARK_DIR):
        if n.startswith(pre) and n.endswith(".json") and n != sid + ".json":
            p = os.path.join(MARK_DIR, n)
            try:
                with open(p, encoding="utf-8") as f:
                    t = float((json.load(f) or {}).get("t") or 0)
            except (OSError, ValueError, TypeError, AttributeError):
                t = 0             # unreadable marker: drop it
            try:
                if now - t > PRUNE_S:
                    os.remove(p)
            except OSError:
                pass


def main():
    try:
        ev = json.loads(sys.stdin.read() or "{}")
        sid = ev.get("session_id") if isinstance(ev, dict) else None
        if not isinstance(sid, str) or not SID.match(sid) or not _is_prompt(ev):
            return
        os.makedirs(MARK_DIR, exist_ok=True)
        now = time.time()
        aid = ev.get("agent_id")
        aid = aid if isinstance(aid, str) and AID.match(aid) else ""
        # ⚠A subagent's event carries the parent's session_id plus agent_id: its own file, so a later main prompt cannot overwrite it.
        path = os.path.join(MARK_DIR, sid + ("." + aid if aid else "") + ".json")
        kind = _kind(ev)
        tool = ev.get("tool_name") if kind == "req" else None
        tool = tool[:120] if isinstance(tool, str) else ""
        if not tool and kind != "req":
            try:
                with open(path, encoding="utf-8") as f:
                    old = json.load(f) or {}
                if now - float(old.get("t") or 0) <= KEEP_TOOL_S and isinstance(old.get("tool"), str):
                    tool = old["tool"][:120]
            except (OSError, ValueError, TypeError, AttributeError):
                pass
        rec = {"sid": sid, "t": now}
        if aid:
            rec.update(k=kind, aid=aid)
        if tool:
            rec["tool"] = tool
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rec, f)
        os.replace(tmp, path)
        _prune(sid, now)
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
