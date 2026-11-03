"""Room name checks for POST /api/say: name rules and existence (rooms.json · a bus post).

⚠Read-only: `rooms.json` belongs to the MCP server; rooms are created and managed by sessions (the `room` skill).
"""
import json
import os

from sidereus.config import DATA_DIR
from sidereus import bus as _bus

ROOMS_PATH = os.path.join(DATA_DIR, "rooms.json")   # read-only here (existence check)
ROOM_LEN_MAX = 200


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _bus_rooms():
    return {m.get("room") for m in _bus.messages(0) if isinstance(m.get("room"), str)}


def _room_known(room):
    if room == "dm":
        return True
    rooms = _read(ROOMS_PATH)
    if isinstance(rooms, dict) and room in rooms:
        return True
    return room in _bus_rooms()


def check_name(room):
    """(stripped room name, None) or (None, error string)."""
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
    The room must exist (rooms.json · a bus post) — except `default`, the configured default room
    that «Outside rooms» posts to by name before anyone has created it.
    ⚠Without this, /api/say accepted 'dm', control characters and typos, and each became a room card."""
    room, err = check_name(room)
    if err:
        return None, err
    if room == default or _room_known(room):
        return room, None
    return None, "No such room: %s" % room
