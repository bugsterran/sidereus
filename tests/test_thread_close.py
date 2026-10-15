"""`thread_close` (stale-thread «정리»): validates the name, derives room/recipient from the bus, appends to a temp bus only."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus
from tests.test_routes_post import post

bus = sidereus("bus")
RP = sidereus("routes_post")


def _m(t, frm, th, room=None, to=None, subject=None):
    return {"id": "m%d" % t, "t": t, "from": frm, "to": to, "room": room, "thread": th, "subject": subject, "body": "x"}


class ThreadClose(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-thclose-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.busf = os.path.join(self.tmp, "bus.jsonl")
        self.rows = []
        for obj, name, val in ((bus, "BUS", self.busf), (bus, "messages", lambda since=0: list(self.rows))):
            p = mock.patch.object(obj, name, val)
            p.start()
            self.addCleanup(p.stop)

    def lines(self):
        if not os.path.exists(self.busf):
            return []
        with open(self.busf, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    def test_closes_room_thread_in_its_own_room(self):
        self.rows = [_m(1, "a", "plan", room="dev"), _m(2, "b", "plan", room="dev"), _m(3, "a", "other", room="dev")]
        out = bus.thread_close({"thread": "plan", "room": "evil"}, "me")
        self.assertEqual(out["closed"], 1)
        [m] = self.lines()
        self.assertEqual((m["room"], m["to"], m["thread"], m["from"], m["idSrc"]), ("dev", None, "plan", "me", "viewer"))
        self.assertTrue(m["subject"].startswith("[마침]"))

    def test_dm_thread_keeps_recipient(self):
        self.rows = [_m(1, "a", "t", to="b"), _m(2, "b", "t", to="a")]
        bus.thread_close({"thread": "t"}, "me")
        self.assertEqual(sorted((m["room"], m["to"]) for m in self.lines()), [(None, "a"), (None, "b")])

    def test_already_closed_key_is_skipped(self):
        self.rows = [_m(1, "a", "t", room="dev"), _m(2, "b", "t", room="dev", subject="[마침] ok")]
        self.assertEqual(bus.thread_close({"thread": "t"}, "me")["closed"], 0)
        self.assertEqual(self.lines(), [])

    def test_rejects_bad_names(self):
        self.rows = [_m(1, "a", "t", room="dev")]
        for bad in (None, 5, "", "   ", "x" * 201, "a\nb", "missing"):
            self.assertFalse(bus.thread_close({"thread": bad}, "me")["ok"], bad)
        self.assertFalse(bus.thread_close("t", "me")["ok"])
        self.assertEqual(self.lines(), [])

    def test_route(self):
        self.rows = [_m(1, "a", "t", room="dev"), _m(2, "b", "t", room="dev")]
        with mock.patch.object(RP, "VIEWER_ME", "viewer"):
            code, out, _h = post("/api/thread/close", {"thread": "t"})
            self.assertEqual((code, out.get("closed")), (200, 1))
            self.assertEqual(post("/api/thread/close", {"thread": "nope"})[0], 400)
            self.assertEqual(post("/api/thread/close", [1])[0], 400)
        self.assertEqual([m["from"] for m in self.lines()], ["viewer"])


if __name__ == "__main__":
    unittest.main()
