"""Chat room admin overlay: DATA_DIR/room-admin.json = {hidden: {room: t_ns}, pending: {room: {created: t_ns}}}.

⚠Hiding is an overlay only — rooms.json and bus.jsonl are never edited or trimmed from here.
"""
import json
import os
import threading
import time

from sidereus.config import DATA_DIR
from sidereus import bus as _bus
from sidereus.room_tags import ROOM_LEN_MAX, _room_known

ADMIN_PATH = os.path.join(DATA_DIR, "room-admin.json")
_LOCK = threading.Lock()
_now = time.time_ns          # patched in tests (no clock)

ROOMS_MAX = 50
BODY_MAX = 16384
PENDING_MSG = "Created room '{name}' (waiting for invites)."


def load():
    """{hidden, pending} — empty maps when the file is missing or broken; malformed entries are dropped."""
    try:
        with open(ADMIN_PATH, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = None
    d = d if isinstance(d, dict) else {}
    hid, pen = d.get("hidden"), d.get("pending")
    return {
        "hidden": {k: v for k, v in hid.items() if isinstance(k, str) and isinstance(v, int)}
        if isinstance(hid, dict) else {},
        "pending": {k: {"created": v["created"]} for k, v in pen.items()
                    if isinstance(k, str) and isinstance(v, dict) and isinstance(v.get("created"), int)}
        if isinstance(pen, dict) else {},
    }


def _write(cur):
    _bus._save_json_bak(ADMIN_PATH, cur)


def check_name(room):
    """Stripped room name for a new room, or an error string."""
    if not isinstance(room, str) or not room.strip() or len(room) > ROOM_LEN_MAX:
        return None, "A room name is required."
    room = room.strip()
    if room == "dm":
        return None, "'dm' cannot be used as a room name."
    if any(ord(c) < 32 or 0x7f <= ord(c) < 0xa0 for c in room):
        return None, "Room names cannot contain control characters."
    return room, None


def say_room(room, default):
    """(room, None) when an /api/say post may go to `room`, else (None, error).
    Same name rules as create, and the room must exist (rooms.json · a bus post · pending) — except `default`,
    the configured default room that «Outside rooms» posts to by name before anyone has created it.
    ⚠Without this, /api/say accepted 'dm', control characters and typos, and each became a room card."""
    room, err = check_name(room)
    if err:
        return None, err
    if room == default or room in load()["pending"] or _room_known(room):
        return room, None
    return None, "No such room: %s" % room


def set_hidden(rooms, hide):
    """(200, {ok, hidden:[...]}) or (400, {ok: False, error}). Unknown names and 'dm' are refused."""
    if not isinstance(rooms, list) or not rooms:
        return 400, {"ok": False, "error": "A list of rooms is required."}
    if len(rooms) > ROOMS_MAX:
        return 400, {"ok": False, "error": "At most %d at a time." % ROOMS_MAX}   # ⚠ko key assumes 50
    with _LOCK:
        cur = load()
        names = []
        for r in rooms:
            if not isinstance(r, str) or not r.strip() or len(r) > ROOM_LEN_MAX or r.strip() == "dm":
                return 400, {"ok": False, "error": "This room cannot be hidden."}
            r = r.strip()
            if r not in cur["pending"] and r not in cur["hidden"] and not _room_known(r):
                return 400, {"ok": False, "error": "No such room: {name}", "vars": {"name": r}}
            names.append(r)
        t = _now()
        for r in names:
            if hide:
                cur["hidden"].setdefault(r, t)
            else:
                cur["hidden"].pop(r, None)
        _write(cur)
    return 200, {"ok": True, "hidden": sorted(cur["hidden"])}


def add_pending(room):
    """Record a room with no members yet (no rooms.json / bus write). (200|400, out)."""
    room, err = check_name(room)
    if err:
        return 400, {"ok": False, "error": err}
    with _LOCK:
        cur = load()
        if room in cur["pending"] or _room_known(room):
            return 400, {"ok": False, "error": "This room already exists."}
        cur["pending"][room] = {"created": _now()}
        _write(cur)
    # msg is a fixed i18n key; the client fills {name} from `vars` after T() (TV in 05-i18n.js)
    return 200, {"ok": True, "pending": True, "room": room, "msg": PENDING_MSG, "vars": {"name": room}}


def drop_pending(room):
    """A pending room became real (invite wrote rooms.json) — forget the pending entry."""
    with _LOCK:
        cur = load()
        if cur["pending"].pop(room, None) is not None:
            _write(cur)
