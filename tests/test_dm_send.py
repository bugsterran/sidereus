"""`dm_send` (work-popup compose): validates the recipient against identity.json and appends to a temp bus only."""
import json
import os
import tempfile
import unittest

from tests._load import sidereus, load

bus = sidereus("bus")


class DmSend(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.bus_path = os.path.join(self.tmp, "bus.jsonl")
        self._bus, self._load = bus.BUS, bus._load
        bus.BUS = self.bus_path                     # never the live bus
        bus._load = lambda name, d: {"/p/a": "alice", "/p/b": "bob"} if name == "identity.json" else d

    def tearDown(self):
        bus.BUS, bus._load = self._bus, self._load
        if os.path.exists(self.bus_path):
            os.unlink(self.bus_path)
        os.rmdir(self.tmp)

    def lines(self):
        if not os.path.exists(self.bus_path):
            return []
        with open(self.bus_path, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    def test_sends_dm_to_logged_in_id(self):
        out = bus.dm_send({"to": "alice", "body": "  hi  "}, "viewer-me")
        self.assertTrue(out["ok"])
        [m] = self.lines()
        self.assertEqual((m["to"], m["from"], m["room"], m["body"], m["idSrc"]), ("alice", "viewer-me", None, "hi", "viewer"))
        self.assertEqual(m["id"], out["id"])
        self.assertEqual(m["thread"], "wk:" + out["id"])

    def test_rejects_unknown_or_guessed_id(self):
        out = bus.dm_send({"to": "mallory", "body": "x"}, "viewer-me")
        self.assertFalse(out["ok"])
        self.assertEqual(self.lines(), [])

    def test_rejects_empty_long_and_self(self):
        self.assertFalse(bus.dm_send({"to": "alice", "body": "   "}, "me")["ok"])
        self.assertFalse(bus.dm_send({"to": "alice", "body": "x" * (bus.DM_MAX + 1)}, "me")["ok"])
        self.assertFalse(bus.dm_send({"to": "alice", "body": "x"}, "alice")["ok"])
        self.assertFalse(bus.dm_send(None, "me")["ok"])
        self.assertEqual(self.lines(), [])

    def test_relay_carries_kind_and_sid(self):
        sid = "0a1b2c3d-4e5f-6789-abcd-ef0123456789"
        self.assertTrue(bus.dm_send({"to": "alice", "body": "x", "relay": True, "sid": sid}, "me")["ok"])
        [m] = self.lines()
        self.assertEqual((m["kind"], m["sid"], m["idSrc"]), ("relay", sid, "viewer"))

    def test_named_thread(self):
        self.assertTrue(bus.dm_send({"to": "alice", "body": "x", "thread": "경고DM·shop-api"}, "me")["ok"])
        self.assertEqual(self.lines()[0]["thread"], "경고DM·shop-api")
        for bad in ("", " x", "a\nb", "a" * 61, 5, "../x/y"):
            self.assertFalse(bus.dm_send({"to": "alice", "body": "x", "thread": bad}, "me")["ok"], bad)
        self.assertEqual(len(self.lines()), 1)

    def test_relay_bad_sid_rejected(self):
        for bad in ("../etc", "abc", "g1234567", 12345678, "", "a" * 65):
            self.assertFalse(bus.dm_send({"to": "alice", "body": "x", "relay": True, "sid": bad}, "me")["ok"], bad)
        self.assertEqual(self.lines(), [])

    def test_non_relay_keeps_old_key_set(self):
        bus.dm_send({"to": "alice", "body": "x", "sid": "0a1b2c3d"}, "me")
        bus.dm_send({"to": "alice", "body": "x", "relay": "yes"}, "me")
        for m in self.lines():
            self.assertEqual(set(m), {"id", "t", "from", "idSrc", "to", "room", "subject", "thread", "body"})

    def test_route_registered_post_only(self):
        cs = load()
        self.assertIn("/api/dm", cs.Handler._POST_ROUTES)
        self.assertNotIn("/api/dm", cs.Handler._GET_ROUTES)


if __name__ == "__main__":
    unittest.main()
