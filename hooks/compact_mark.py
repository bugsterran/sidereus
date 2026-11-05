#!/usr/bin/env python3
"""PreCompact/PostCompact hook: mark that a Claude Code session is compacting its context.

PreCompact writes <data dir>/compacting/<session_id>.json = {"sid", "t"[, "trig"]}; PostCompact removes it.
Metadata only: never custom_instructions. Sidereus shows «Compacting» while the marker is newer than the
session's last transcript activity (sidereus/compact_marks.compacting).
Fail-silent, always exits 0, prints nothing. Stdlib only, Python 3.9.
"""
import json
import os
import re
import sys
import time

# Same derivation as sidereus/config.py DATA_DIR so the server reads the same folder.
DATA_DIR = os.path.expanduser(os.environ.get("MAILBOX_DIR") or "~/.mailbox-mcp")
MARK_DIR = os.path.join(DATA_DIR, "compacting")
SID = re.compile(r"^[0-9a-zA-Z-]{8,64}$")


def main():
    try:
        ev = json.loads(sys.stdin.read() or "{}")
        if not isinstance(ev, dict):
            return
        sid = ev.get("session_id")
        name = ev.get("hook_event_name") or ""
        if not isinstance(sid, str) or not SID.match(sid) or name not in ("PreCompact", "PostCompact"):
            return
        path = os.path.join(MARK_DIR, sid + ".json")
        if name == "PostCompact":
            try:
                os.remove(path)
            except OSError:
                pass
            return
        os.makedirs(MARK_DIR, exist_ok=True)
        rec = {"sid": sid, "t": time.time()}
        trig = ev.get("trigger")
        if trig in ("auto", "manual"):
            rec["trig"] = trig
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rec, f)
        os.replace(tmp, path)
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
