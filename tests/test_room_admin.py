"""Room admin overlay (sidereus/room_admin.py + POST /api/rooms/hide|unhide|create): overlay only, .bak, limits, Origin guard."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus
from tests.test_routes_post import OWN, post

RA = sidereus("room_admin")
RP = sidereus("routes_post")
bus = sidereus("bus")


def _has_key(src, k):
    """`k` written as an object key (either quote style) in the dictionary source."""
    return ("'%s':" % k) in src or ('"%s":' % k) in src


def _i18n_src():
    """Repo web/js/06-i18n-*.js source (not live data) — server msg keys must have an I18N.ko entry."""
    web = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "js")
    out = []
    for f in sorted(os.listdir(web)):
        if f.startswith("06-i18n"):
            with open(os.path.join(web, f), encoding="utf-8") as fh:
                out.append(fh.read())
    return "".join(out)


class RoomAdminTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-ra-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "room-admin.json")
        self.rooms = os.path.join(self.tmp, "rooms.json")
        self.busf = os.path.join(self.tmp, "bus.jsonl")
        clock = iter(range(1000, 2000))
        for obj, name, val in ((RA, "ADMIN_PATH", self.path), (RA, "_room_known", lambda r: r in ("dev", "busroom")),
                               (RA, "_now", lambda: next(clock)), (bus, "DATA_DIR", self.tmp), (bus, "BUS", self.busf),
                               (RP, "sessions_rows", lambda **k: [
                                   {"mbox": "alice", "mboxSrc": "identity"}, {"mbox": "carol", "mboxSrc": "identity"}])):
            p = mock.patch.object(obj, name, val)
            p.start()
            self.addCleanup(p.stop)

    def _lines(self):
        try:
            with open(self.busf, encoding="utf-8") as f:
                return [json.loads(x) for x in f]
        except FileNotFoundError:
            return []

    def test_hide_unhide_round_trip(self):
        self.assertEqual(RA.load(), {"hidden": {}, "pending": {}})
        self.assertEqual(RA.set_hidden(["dev", " busroom "], True), (200, {"ok": True, "hidden": ["busroom", "dev"]}))
        self.assertEqual(RA.load()["hidden"], {"dev": 1000, "busroom": 1000})
        self.assertEqual(RA.set_hidden(["dev"], False)[0], 200)
        self.assertEqual(RA.load()["hidden"], {"busroom": 1000})
        self.assertTrue(os.path.exists(self.path + ".bak"))

    def test_rejects_unknown_dm_and_too_many(self):
        for rooms in (["nope"], ["dm"], ["dev", "dm"], [], "dev", [5], ["dev"] * 51):
            code, out = RA.set_hidden(rooms, True)
            self.assertEqual((code, out["ok"]), (400, False), rooms)
        self.assertFalse(os.path.exists(self.path))
        self.assertEqual(RA.set_hidden(["dev"] * 50, True)[0], 200)

    def test_broken_json_loads_empty(self):
        for raw in ("{nope", "[1]", '{"hidden": [1], "pending": {"x": 5}}'):
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(raw)
            self.assertEqual(RA.load(), {"hidden": {}, "pending": {}}, raw)

    def test_hide_keeps_bus(self):
        with open(self.busf, "w", encoding="utf-8") as f:
            for i in range(3):
                f.write(json.dumps({"id": str(i), "room": "dev", "t": i}) + "\n")
        code, _, _ = post("/api/rooms/hide", {"rooms": ["dev"]}, origin=OWN)
        self.assertEqual(code, 200)
        self.assertEqual(len(self._lines()), 3)
        self.assertFalse(os.path.exists(self.rooms))
        self.assertEqual(post("/api/rooms/unhide", {"rooms": ["dev"]}, origin=OWN)[0], 200)
        self.assertEqual(RA.load()["hidden"], {})

    def test_pending_create_touches_nothing_else(self):
        code, out, _ = post("/api/rooms/create", {"room": "new"}, origin=OWN)
        self.assertEqual((code, out["ok"], out["pending"]), (200, True, True))
        # msg must be a fixed I18N key (T() lookup), the name travels separately in `room`
        self.assertEqual((out["msg"], out["vars"]), (RA.PENDING_MSG, {"name": "new"}))
        src = _i18n_src()
        for k in [RA.PENDING_MSG] + list(RP.INVITE_MSGS.values()):
            self.assertTrue(_has_key(src, k), k)   # I18N.ko key (English source)
        self.assertEqual(RA.load()["pending"], {"new": {"created": 1000}})
        self.assertFalse(os.path.exists(self.rooms))
        self.assertFalse(os.path.exists(self.busf))
        for body in ({"room": "new"}, {"room": "dev"}, {"room": "dm"}, {"room": ""}, {"room": "x" * 201}, [1]):
            self.assertEqual(post("/api/rooms/create", body, origin=OWN)[0], 400, body)
        self.assertTrue(RA.set_hidden(["new"], True)[1]["ok"])     # a pending room can be hidden too

    def test_create_with_ids_invites(self):
        with open(self.rooms, "w", encoding="utf-8") as f:
            json.dump({"old": {"members": []}}, f)
        RA.add_pending("r1")
        code, out, _ = post("/api/rooms/create", {"room": "r1", "ids": ["alice", "carol"]}, origin=OWN)
        self.assertEqual((code, out["ok"], out["added"]), (200, True, ["alice", "carol"]))
        self.assertEqual((out["msg"], out["vars"]), (RP.INVITE_MSGS[(True, False)], {"room": "r1", "n": 2, "m": 0}))
        with open(self.rooms, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["r1"]["invited"], ["alice", "carol"])
        with open(self.rooms + ".bak", encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"old": {"members": []}})
        self.assertEqual([(m["to"], m["subject"].startswith("[초대]")) for m in self._lines()],
                         [("alice", True), ("carol", True)])
        self.assertEqual(RA.load()["pending"], {})

    def test_create_existing_with_ids_refused(self):
        code, out, _ = post("/api/rooms/create", {"room": "dev", "ids": ["alice"]}, origin=OWN)
        self.assertEqual((code, out["error"]), (400, "This room already exists."))
        self.assertFalse(os.path.exists(self.rooms))
        self.assertFalse(os.path.exists(self.busf))

    def test_dry_invite_existing_member_adds_nobody(self):
        with open(self.rooms, "w", encoding="utf-8") as f:
            json.dump({"dev": {"members": ["alice"], "invited": []}}, f)
        code, out, _ = post("/api/room/invite", {"room": "dev", "ids": ["alice"], "dry": True}, origin=OWN)
        self.assertEqual((code, out["dry"], out["added"], out["already"]), (200, True, [], ["alice"]))
        self.assertFalse(os.path.exists(self.busf))

    def test_room_errors_have_en(self):
        src = _i18n_src()
        for k in ("A room name is required.", "'dm' cannot be used as a room name.",
                  "Room names cannot contain control characters.", "A list of rooms is required.",
                  "This room cannot be hidden.", "This room already exists.", "Bad request.",
                  "The room changed since the preview — check again.", "At most 50 at a time.",
                  "Tags are 1–20 characters.", "At most 8 tags."):
            self.assertTrue(_has_key(src, k), k)   # I18N.ko key (English source)

    def test_routes_need_origin(self):
        for path, body in (("/api/rooms/hide", {"rooms": ["dev"]}), ("/api/rooms/unhide", {"rooms": ["dev"]}),
                           ("/api/rooms/create", {"room": "n"}), ("/api/rooms/create", {"room": "n", "ids": ["alice"]})):
            code, out, h = post(path, body)
            self.assertEqual((code, h.rfile.reads), (403, 0), path)
        self.assertFalse(os.path.exists(self.path))
        self.assertFalse(os.path.exists(self.rooms))
        self.assertFalse(os.path.exists(self.busf))


if __name__ == "__main__":
    unittest.main()
