"""Chat room hashtags: {room: [tag, ...]} in DATA_DIR/room-tags.json.

⚠Sidereus owns this file; `rooms.json` belongs to the MCP server and is only read here (invite/create write it in routes_post, with a .bak).
"""
import json
import os
import threading

from sidereus.config import DATA_DIR
from sidereus import bus as _bus

TAGS_PATH = os.path.join(DATA_DIR, "room-tags.json")
ROOMS_PATH = os.path.join(DATA_DIR, "rooms.json")   # read-only here (existence check)
_LOCK = threading.Lock()

TAGS_MAX = 8
TAG_LEN_MAX = 20
ROOM_LEN_MAX = 200
BODY_MAX = 4096


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load():
    """{room: [tags]} — {} when the file is missing or broken; malformed entries are dropped."""
    d = _read(TAGS_PATH)
    if not isinstance(d, dict):
        return {}
    return {k: [t for t in v if isinstance(t, str)] for k, v in d.items()
            if isinstance(k, str) and isinstance(v, list)}


def _bus_rooms():
    return {m.get("room") for m in _bus.messages(0) if isinstance(m.get("room"), str)}


def _room_known(room):
    if room == "dm":
        return True
    rooms = _read(ROOMS_PATH)
    if isinstance(rooms, dict) and room in rooms:
        return True
    return room in _bus_rooms()


def _clean(tags):
    """Validated, case-insensitively deduped list, or an error string."""
    if not isinstance(tags, list):
        return "A tag list is required."
    out, seen = [], set()
    for t in tags:
        if not isinstance(t, str):
            return "Tags must be strings."
        t = t.strip()
        if not 1 <= len(t) <= TAG_LEN_MAX:
            return "Tags are 1–%d characters." % TAG_LEN_MAX   # ⚠ko key assumes 20
        # ⚠Lone surrogates (a split emoji pair) would raise UnicodeEncodeError on save -> 500; refuse them here.
        if "#" in t or any(ord(c) < 32 or 0x7f <= ord(c) < 0xa0 or 0xd800 <= ord(c) <= 0xdfff for c in t):
            return "Tags cannot contain # or control characters."
        if t.casefold() in seen:
            continue
        seen.add(t.casefold())
        out.append(t)
    if len(out) > TAGS_MAX:
        return "At most %d tags." % TAGS_MAX   # ⚠ko key assumes 8
    return out


def set_tags(room, tags):
    """(200, {ok, tags}) or (400, {ok: False, error}). An empty list removes the room's entry."""
    if not isinstance(room, str) or not room.strip() or len(room) > ROOM_LEN_MAX:
        return 400, {"ok": False, "error": "A room name is required."}
    room = room.strip()
    clean = _clean(tags)
    if isinstance(clean, str):
        return 400, {"ok": False, "error": clean}
    if not _room_known(room):
        return 400, {"ok": False, "error": "No such room."}
    with _LOCK:
        cur = load()
        if clean:
            cur[room] = clean
        else:
            cur.pop(room, None)
        _bus._save_json_bak(TAGS_PATH, cur)
    return 200, {"ok": True, "tags": clean}
