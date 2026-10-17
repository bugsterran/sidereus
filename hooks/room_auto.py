#!/usr/bin/env python3
"""Auto-assigns mailbox rooms by project path.

Problem (2026-08-25): related projects should share a room, but each session had to be asked to create one.
Invites still leave a step, since the peer must join by itself.

So this hook reads the **path → room** mapping (room-map.json) and at session start:
  ① creates the room if missing
  ② adds this session's mailbox id to members (no-op if already there)
  ③ prints one line only on a new join — silent if already a member (doesn't eat context every session)
Pending invites (invited) are announced too.

★Identity is **not changed.** Uses identity.json's existing resolution (MAILBOX_ME → path → default) as-is.
  A `~/bot-A` session posting as `agent-A` is an intended setup, so
  if the hook minted a new id from the folder name, that session's send history would be cut off.

★On failure, pass silently. Room assignment must never block a session.
"""
import json
import os
import sys
import time
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mailbox_config  # noqa: E402

STORE = mailbox_config.data_dir()
ROOMS = os.path.join(STORE, "rooms.json")
IDENTITY = os.path.join(STORE, "identity.json")
ROOMMAP = os.path.join(STORE, "room-map.json")


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_atomic(path, data):
    """The MCP server writes the same file — write a temp file then replace, so no half-written JSON is left."""
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def whoami(cwd):
    env = (os.environ.get("MAILBOX_ME") or "").strip()
    if env:
        return env
    ident = load(IDENTITY, {})
    p = cwd or ""
    while p and p != "/":
        if p in ident:
            return ident[p]
        p = os.path.dirname(p)
    return ident.get("default") or ""


def rooms_for(cwd, rmap):
    """Rooms this path belongs to. Matched by path prefix; **the longest prefix** wins (subprojects first)."""
    hits = []
    for name, cfg in (rmap.items() if isinstance(rmap, dict) else []):
        if not isinstance(cfg, dict):
            continue
        best = ""
        for base in cfg.get("paths") or []:
            base = os.path.expanduser(base).rstrip("/")
            if cwd == base or cwd.startswith(base + "/"):
                if len(base) > len(best):
                    best = base
        if best:
            hits.append((len(best), name, cfg))
    hits.sort(reverse=True)
    return [(n, c) for _l, n, c in hits]


def main():
    try:
        raw = sys.stdin.read()
        inp = json.loads(raw) if raw.strip() else {}
    except Exception:
        inp = {}

    cwd = os.path.realpath(inp.get("cwd") or os.getcwd())
    me = whoami(cwd)
    if not me:
        return

    rmap = load(ROOMMAP, {})
    targets = rooms_for(cwd, rmap)
    rooms = load(ROOMS, {})
    if not isinstance(rooms, dict):
        return

    joined, created, changed = [], [], False
    for name, cfg in targets:
        r = rooms.get(name)
        if r is None:
            rooms[name] = r = {
                "created": time.time_ns(),
                "owner": me,
                "members": [],
                "topic": cfg.get("topic") or "",
                "invited": [],
            }
            created.append(name)
            changed = True
        mem = r.setdefault("members", [])
        if me not in mem:
            mem.append(me)
            if me in (r.get("invited") or []):
                r["invited"].remove(me)     # the invite is consumed
            joined.append(name)
            changed = True

    if changed:
        try:
            save_atomic(ROOMS, rooms)
        except Exception:
            return

    # pending invites (sent by a person, separate from auto-assignment)
    pending = [n for n, r in rooms.items()
               if isinstance(r, dict) and me in (r.get("invited") or []) and me not in (r.get("members") or [])]

    if not (joined or pending):
        return                              # silence is the default — prints nothing if already a member

    out = [f"[mailbox] id `{me}`"]
    for n in joined:
        r = rooms[n]
        others = [x for x in (r.get("members") or []) if x != me]
        tag = " (newly created)" if n in created else ""
        out.append(f"  · auto-joined room **{n}**{tag}"
                   + (f" — topic: {r['topic']}" if r.get("topic") else ""))
        out.append(f"    with: {', '.join(others) or 'nobody yet'}")
    for n in pending:
        out.append(f'  · room **{n}** invite pending — mailbox_room {{ action: "join", room: "{n}" }}')
    out.append("These rooms were assigned automatically by path mapping (room-map.json). "
               "No need to speak first; use the room when the user asks you to coordinate.")
    print("\n".join(out))


if __name__ == "__main__":
    for _s in (sys.stdin, sys.stdout):   # ⚠Windows pipes default to the ANSI codepage; hook output is UTF-8
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    try:
        main()
    except Exception:
        pass
