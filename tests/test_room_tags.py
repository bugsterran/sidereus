"""Room hashtags (sidereus/room_tags.py + POST /api/rooms/tags): round trip, limits, unknown room, .bak, Origin guard."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus
from tests.test_routes_post import EVIL, PORT, post

RT = sidereus("room_tags")
OWN = "http://127.0.0.1:%d" % PORT


class RoomTagsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-rt-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "room-tags.json")
        rooms = os.path.join(self.tmp, "rooms.json")
        with open(rooms, "w", encoding="utf-8") as f:
            json.dump({"dev": {"members": []}}, f)
        for name, val in (("TAGS_PATH", self.path), ("ROOMS_PATH", rooms),
                          ("_bus_rooms", lambda: {"busroom"})):
            p = mock.patch.object(RT, name, val)
            p.start()
            self.addCleanup(p.stop)

    def test_round_trip(self):
        self.assertEqual(RT.load(), {})
        code, out = RT.set_tags("dev", [" api ", "API", "버그"])
        self.assertEqual((code, out), (200, {"ok": True, "tags": ["api", "버그"]}))
        self.assertEqual(RT.set_tags("busroom", ["x"])[0], 200)
        self.assertEqual(RT.set_tags("dm", ["y"])[0], 200)
        self.assertEqual(RT.load(), {"dev": ["api", "버그"], "busroom": ["x"], "dm": ["y"]})
        RT.set_tags("dm", [])
        self.assertNotIn("dm", RT.load())

    def test_broken_file_loads_empty(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{nope")
        self.assertEqual(RT.load(), {})

    def test_rejects_bad_tags(self):
        for tags in (["a#b"], ["x" * 21], [""], ["  "], ["a\nb"], [3], "abc",
                     ["t%d" % i for i in range(9)]):
            code, out = RT.set_tags("dev", tags)
            self.assertEqual(code, 400, tags)
            self.assertFalse(out["ok"])
            self.assertTrue(out["error"])
        self.assertEqual(RT.set_tags("dev", ["t%d" % i for i in range(8)])[0], 200)
        self.assertFalse(os.path.exists(self.path + ".bak"))

    def test_lone_surrogate_is_400_and_code_points_count(self):
        code, out = RT.set_tags("dev", ["ab\ud83d"])
        self.assertEqual(code, 400)
        self.assertFalse(out["ok"])
        self.assertFalse(os.path.exists(self.path))
        self.assertEqual(RT.set_tags("dev", ["\U0001F600" * 20])[0], 200)   # 20 code points (40 UTF-16 units)
        self.assertEqual(RT.set_tags("dev", ["\U0001F600" * 21])[0], 400)

    def test_rejects_unknown_room(self):
        self.assertEqual(RT.set_tags("nope", ["a"])[0], 400)
        self.assertEqual(RT.set_tags("", ["a"])[0], 400)
        self.assertFalse(os.path.exists(self.path))

    def test_bak_after_second_write(self):
        RT.set_tags("dev", ["one"])
        self.assertFalse(os.path.exists(self.path + ".bak"))
        RT.set_tags("dev", ["two"])
        with open(self.path + ".bak", encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"dev": ["one"]})
        self.assertEqual(RT.load(), {"dev": ["two"]})

    def test_route(self):
        code, out, _ = post("/api/rooms/tags", {"room": "dev", "tags": ["a"]}, origin=OWN)
        self.assertEqual((code, out), (200, {"ok": True, "tags": ["a"]}))
        code, out, _ = post("/api/rooms/tags", {"room": "nope", "tags": ["a"]}, origin=OWN)
        self.assertEqual(code, 400)
        self.assertFalse(out["ok"])
        self.assertEqual(post("/api/rooms/tags", b"[1]", origin=OWN)[0], 400)

    def test_route_rejects_foreign_or_missing_origin(self):
        code, out, h = post("/api/rooms/tags", {"room": "dev", "tags": ["a"]}, origin=EVIL)
        self.assertEqual(code, 403)
        self.assertEqual(h.rfile.reads, 0)
        self.assertEqual(post("/api/rooms/tags", {"room": "dev", "tags": ["a"]})[0], 403)
        self.assertFalse(os.path.exists(self.path))


if __name__ == "__main__":
    unittest.main()
