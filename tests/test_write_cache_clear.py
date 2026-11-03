"""Successful POST writes clear the 1 s /api/state cache; saver save without the hook folder returns ok:false."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus
from tests.test_routes_post import OWN, RP, post

sv = sidereus("saver")


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-wcc-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cleared = []
        self.patch(RP, "state_cache_clear", lambda: self.cleared.append(1))

    def patch(self, obj, name, val):
        p = mock.patch.object(obj, name, val)
        p.start()
        self.addCleanup(p.stop)


class CacheClearTest(_Base):
    def test_say(self):
        self.patch(RP, "BUS_PATH", os.path.join(self.tmp, "bus.jsonl"))
        self.patch(RP.room_check, "say_room", lambda r, d: (r, ""))
        code, _, _ = post("/api/say", {"body": "hi", "room": "r1"})
        self.assertEqual((code, len(self.cleared)), (200, 1))

    def test_say_failed_write_keeps_cache(self):
        self.patch(RP, "BUS_PATH", os.path.join(self.tmp, "no", "bus.jsonl"))
        self.patch(RP.room_check, "say_room", lambda r, d: (r, ""))
        code, _, _ = post("/api/say", {"body": "hi", "room": "r1"})
        self.assertEqual((code, self.cleared), (500, []))

    def test_todo_add_set(self):
        ok = lambda req: (200, {"ok": True, "items": []})
        self.patch(RP, "todo_add", ok)
        self.patch(RP, "todo_set", ok)
        for path in ("/api/todo/add", "/api/todo/set"):
            code, _, _ = post(path, {"text": "x"}, origin=OWN)
            self.assertEqual(code, 200, path)
        self.assertEqual(len(self.cleared), 2)

    def test_todo_failed_keeps_cache(self):
        self.patch(RP, "todo_add", lambda req: (400, {"ok": False, "err": "x"}))
        post("/api/todo/add", {"text": ""}, origin=OWN)
        self.assertEqual(self.cleared, [])


class SaverNoHookDirTest(_Base):
    def test_missing_dir_ok_false_and_not_created(self):
        gone = os.path.join(self.tmp, "hooks")
        for name, f in (("SAVER_FORCE", ".saver-force.json"), ("SAVER_GOAL", ".saver-goal.json"),
                        ("SAVER_LIMIT", ".saver-limit.json")):
            self.patch(sv, name, os.path.join(gone, f))
        self.patch(sv, "quota", lambda: {})
        for body in ({"mode": "off"}, {"mode": "auto"}, {"goal": 50}, {"limit": "warn"}):
            out = sv.saver_set(body)
            self.assertFalse(out["ok"], body)
            self.assertEqual((out["err"], out["path"]), ("Hook folder not found", gone))
        code, out, _ = post("/api/saver/set", {"mode": "off"})
        self.assertEqual((code, out["ok"]), (400, False))
        self.assertFalse(os.path.exists(gone))
        self.assertEqual(self.cleared, [])


if __name__ == "__main__":
    unittest.main()
