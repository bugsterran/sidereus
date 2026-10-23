"""POST /api/say and /api/dm at the route level, plus body-shape edges of the other handlers.

test_routes_post covers malformed/oversize/cross-origin for the other routes; test_request_hardening covers
/api/say lengths over a socket; test_dm_send covers dm_send() itself. This file drives the handlers
(socketless, via test_routes_post.post) for what those leave out: /api/say happy path and field handling,
write failure -> 500, /api/dm non-object bodies and dm_send exceptions, and non-object / non-string JSON.
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus
from tests.test_routes_post import OWN, post

RP = sidereus("routes_post")
RA = sidereus("room_admin")
bus = sidereus("bus")
wm = sidereus("warn")


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-say-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def patch(self, obj, name, val):
        p = mock.patch.object(obj, name, val)
        p.start()
        self.addCleanup(p.stop)


class SayTest(_Base):
    def setUp(self):
        super().setUp()
        self.busf = os.path.join(self.tmp, "bus.jsonl")
        self.patch(RP, "BUS_PATH", self.busf)
        self.patch(RP, "VIEWER_ME", "me")
        # room existence (room_admin.say_room): r1 exists, «home» is the default room, nothing pending
        self.patch(RP, "ROOM_DEFAULT", "home")
        self.patch(RA, "_room_known", lambda r: r == "r1")
        self.patch(RA, "ADMIN_PATH", os.path.join(self.tmp, "room-admin.json"))
        # identity.json fixture for DM targets (bus.dm_target_error reads it through bus._load)
        self.patch(bus, "DATA_DIR", self.tmp)
        with open(os.path.join(self.tmp, "identity.json"), "w", encoding="utf-8") as f:
            json.dump({"sid1": "alice", "sid2": "me"}, f)

    def _lines(self):
        if not os.path.exists(self.busf):
            return []
        with open(self.busf, encoding="utf-8") as f:
            return [json.loads(x) for x in f]

    def test_happy_minimal_room(self):
        code, out, h = post("/api/say", {"body": "  hi  ", "room": " r1 "})
        self.assertEqual(code, 200)
        self.assertTrue(out["ok"])
        (m,) = self._lines()
        self.assertEqual(m["id"], out["id"])
        self.assertEqual((m["from"], m["idSrc"], m["to"], m["room"]), ("me", "viewer", None, "r1"))
        self.assertEqual((m["body"], m["subject"], m["thread"]), ("hi", None, None))
        self.assertNotIn("replyTo", m)
        self.assertFalse(h.close_connection)

    def test_no_target_refused_never_default_room(self):
        for req in ({"body": "hi"}, {"body": "hi", "room": "  "}, {"body": "hi", "room": "r1", "to": "alice"}):
            code, out, _ = post("/api/say", req)
            self.assertEqual(code, 400, req)
            self.assertIn("No recipient", out["error"])
        self.assertEqual(self._lines(), [])

    def test_room_name_rules_and_existence(self):
        for room, why in (("dm", "dm"), ("a\nb", "control"), ("nope", "No such room"), ("x" * 201, "room name")):
            code, out, _ = post("/api/say", {"body": "hi", "room": room})
            self.assertEqual(code, 400, room)
            self.assertIn(why, out["error"], room)
        self.assertEqual(self._lines(), [])
        with open(RA.ADMIN_PATH, "w", encoding="utf-8") as f:
            json.dump({"pending": {"fresh": {"created": 1}}}, f)
        for room in ("home", " home ", "fresh"):        # default room («방 밖 글») even before it exists · a pending room
            self.assertEqual(post("/api/say", {"body": "hi", "room": room})[0], 200, room)
        self.assertEqual([m["room"] for m in self._lines()], ["home", "home", "fresh"])

    def test_dm_reply_goes_to_peer_not_a_room(self):
        req = {"body": "ok", "to": " alice ", "replyTo": "ab12", "thread": "th1"}
        code, out, _ = post("/api/say", req)
        self.assertEqual(code, 200)
        (m,) = self._lines()
        self.assertEqual((m["to"], m["room"], m["replyTo"], m["thread"]), ("alice", None, "ab12", "th1"))

    def test_dm_to_unknown_or_self_refused(self):
        for to in ("ghost", "me"):
            code, out, _ = post("/api/say", {"body": "x", "to": to})
            self.assertEqual(code, 400, to)
        self.assertEqual(self._lines(), [])

    def test_happy_all_fields(self):
        req = {"body": "b", "room": "r1", "subject": " s ", "thread": " th ", "replyTo": " ab12 "}
        self.assertEqual(post("/api/say", req)[0], 200)
        (m,) = self._lines()
        self.assertEqual((m["room"], m["subject"], m["thread"], m["replyTo"]), ("r1", "s", "th", "ab12"))

    def test_blank_optional_fields_become_none(self):
        post("/api/say", {"body": "b", "room": "r1", "subject": "   ", "thread": "", "replyTo": "  "})
        (m,) = self._lines()
        self.assertEqual((m["subject"], m["thread"]), (None, None))
        self.assertNotIn("replyTo", m)

    def test_empty_body_refused(self):
        for req in ({}, {"body": ""}, {"body": "   \n"}, {"body": None}):
            code, out, _ = post("/api/say", req)
            self.assertEqual(code, 400, req)
            self.assertIn("Empty posts", out["error"])
        self.assertEqual(self._lines(), [])

    def test_bad_json_refused_and_closes(self):
        for raw in (b"{bad", b"[1, 2]", b'"str"', b"null", b"\xff"):
            code, out, h = post("/api/say", raw)
            self.assertEqual(code, 400, raw)
            self.assertIn("Could not read the body", out["error"])
            self.assertTrue(h.close_connection, raw)
        self.assertEqual(self._lines(), [])

    def test_empty_request_body_is_empty_post(self):
        code, out, _ = post("/api/say", b"")
        self.assertEqual(code, 400)
        self.assertIn("Empty posts", out["error"])

    def test_size_cap(self):
        code, _, h = post("/api/say", b"", clen=200_001)
        self.assertEqual((code, h.rfile.reads, h.close_connection), (400, 0, True))
        body = json.dumps({"body": "x" * 1000, "room": "r1"}).encode()
        self.assertEqual(post("/api/say", body)[0], 200)      # well under the cap goes through

    def test_write_failure_is_500(self):
        def boom(path):
            raise OSError("disk full")
        self.patch(RP, "_open_append", boom)
        code, out, _ = post("/api/say", {"body": "hi", "room": "r1"})
        self.assertEqual(code, 500)
        self.assertIn("disk full", out["error"])

    def test_non_string_fields_are_400(self):
        # .strip() on a number used to raise out of do_POST with no response.
        for req in ({"body": 5}, {"body": ["x"]}, {"body": "b", "room": 3}, {"body": "b", "subject": {"a": 1}},
                    {"body": "b", "thread": 1}, {"body": "b", "replyTo": True}, {"body": "b", "to": 3}):
            code, out, _ = post("/api/say", req)
            self.assertEqual(code, 400, req)
            self.assertIn("Fields that are not strings", out["error"])
        self.assertEqual(self._lines(), [])


class DmRouteTest(_Base):
    def setUp(self):
        super().setUp()
        self.calls = []
        self.patch(RP, "VIEWER_ME", "me")

    def _stub(self, out):
        self.patch(RP, "dm_send", lambda req, me: (self.calls.append((req, me)), out)[1])

    def test_happy_passes_request_and_viewer_id(self):
        self._stub({"ok": True, "id": "abc", "to": "alice"})
        code, out, _ = post("/api/dm", {"to": "alice", "body": "hi"})
        self.assertEqual((code, out), (200, {"ok": True, "id": "abc", "to": "alice"}))
        self.assertEqual(self.calls, [({"to": "alice", "body": "hi"}, "me")])

    def test_rejection_is_400(self):
        self._stub({"ok": False, "error": "메일박스 미접속 — 받을 수 없습니다"})
        code, out, _ = post("/api/dm", {"to": "ghost", "body": "hi"})
        self.assertEqual(code, 400)
        self.assertFalse(out["ok"])

    def test_non_object_bodies_never_reach_dm_send(self):
        self._stub({"ok": True})
        for raw in (b"", b"{bad", b"[1]", b"null", b'"s"', b"3"):
            code, out, _ = post("/api/dm", raw)
            self.assertEqual((code, out["ok"]), (400, False), raw)
        self.assertEqual(self.calls, [])

    def test_relay_needs_viewer_origin(self):
        self._stub({"ok": True, "id": "abc", "to": "alice"})
        req = {"to": "alice", "body": "hi", "relay": True, "sid": "0a1b2c3d"}
        code, out, _ = post("/api/dm", req)                         # no Origin (agent curl) -> refused, not downgraded
        self.assertEqual((code, out["ok"], out["err"]), (403, False, "relay needs the viewer page"))
        self.assertEqual(self.calls, [])
        port = sidereus("config").PORT
        for o in ("http://127.0.0.1:%d" % port, "http://localhost:%d" % port):
            self.assertEqual(post("/api/dm", req, origin=o)[0], 200, o)
        self.assertEqual(post("/api/dm", {"to": "alice", "body": "hi"})[0], 200)   # plain DM without Origin still ok
        self.assertEqual(len(self.calls), 3)

    def test_oversize_not_read(self):
        self._stub({"ok": True})
        code, _, h = post("/api/dm", b"", clen=65537)
        self.assertEqual((code, h.rfile.reads, h.close_connection), (400, 0, True))
        self.assertEqual(self.calls, [])

    def test_dm_send_exception_is_400_without_detail(self):
        def boom(req, me):
            raise OSError("secret path /x/y")
        self.patch(RP, "dm_send", boom)
        code, out, _ = post("/api/dm", {"to": "a", "body": "b"})
        self.assertEqual(code, 400)
        self.assertEqual(out, {"ok": False, "error": "Could not write (OSError)"})   # type only, no message

    def test_real_dm_send_writes_bus(self):
        # End to end through the real dm_send: identity.json and bus.jsonl in a temp dir.
        self.patch(bus, "DATA_DIR", self.tmp)
        busf = os.path.join(self.tmp, "bus.jsonl")
        self.patch(bus, "BUS", busf)
        with open(os.path.join(self.tmp, "identity.json"), "w", encoding="utf-8") as f:
            json.dump({"sid1": "alice"}, f)
        code, out, _ = post("/api/dm", {"to": "alice", "body": "hi"})
        self.assertEqual((code, out["ok"], out["to"]), (200, True, "alice"))
        with open(busf, encoding="utf-8") as f:
            (m,) = [json.loads(x) for x in f]
        self.assertEqual((m["from"], m["to"], m["thread"]), ("me", "alice", "wk:" + out["id"]))


class DmPlreqTest(_Base):
    """R3 server side: /api/dm `plreq` (run request / stop) records metadata only, a stop is checked before sending."""
    SID = "0a1b2c3d-0000"

    def setUp(self):
        super().setUp()
        self.calls = []
        PQ = sidereus("pl_reqs")
        self.pq, self.path = PQ, os.path.join(self.tmp, "plreq.json")
        self.patch(RP, "VIEWER_ME", "me")
        self.patch(PQ, "PLREQ_PATH", self.path)
        self.patch(PQ, "PLSTOP_DIR", os.path.join(self.tmp, "plstop"))
        self.patch(PQ, "_now", lambda: 1_000_000.0)
        self.n = 0

        def fake(req, me):
            self.n += 1
            self.calls.append(req)
            return {"ok": True, "id": "mid%d" % self.n, "to": req["to"]}
        self.patch(RP, "dm_send", fake)

    def send(self, plreq, relay=True, to="alice"):
        req = {"to": to, "body": "secret body", "relay": relay, "sid": self.SID, "plreq": plreq}
        return post("/api/dm", req, origin=OWN)

    def recs(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)["reqs"]

    def test_req_writes_one_record_without_body(self):
        code, out, _ = self.send({"kind": "req", "pipeline": "arch-map", "repo": "/r"})
        self.assertEqual((code, out["ok"]), (200, True))
        (r,) = self.recs()
        self.assertEqual((r["id"], r["mid"], r["sid"], r["to"], r["repo"]), ("mid1", "mid1", self.SID, "alice", "/r"))
        self.assertNotIn("secret body", json.dumps(self.recs()))

    def test_plreq_without_relay_refused(self):
        code, out, _ = self.send({"kind": "req", "pipeline": "arch-map", "repo": "/r"}, relay=False)
        self.assertEqual((code, out["ok"]), (400, False))
        self.assertEqual(self.calls, [])

    def test_stop_unknown_or_mismatched_refused_before_send(self):
        self.send({"kind": "req", "pipeline": "arch-map", "repo": "/r"})
        stop = {"kind": "stop", "pipeline": "arch-map", "repo": "/r", "of": "mid1"}
        for bad, to in ((dict(stop, of="zzz"), "alice"), (dict(stop, repo="/x"), "alice"), (stop, "bob")):
            self.assertEqual(self.send(bad, to=to)[0], 400, bad)
        self.assertEqual(len(self.calls), 1)
        code, out, _ = self.send(stop)
        self.assertEqual((code, len(self.calls)), (200, 2))
        self.assertEqual(self.recs()[0]["stop"], {"mid": "mid2", "at": 1_000_000.0})
        with open(os.path.join(self.tmp, "plstop", self.SID + ".json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"arch-map": {"at": 1_000_000.0, "mid": "mid2", "of": "mid1"}})


class BodyShapeEdgesTest(_Base):
    """Valid JSON of the wrong shape on the handlers that take {"key": ...}."""

    def setUp(self):
        super().setUp()
        saved = (list(wm._WARN_LOG), dict(wm._wmute), set(wm._warned))

        def restore():
            wm._WARN_LOG[:] = saved[0]
            wm._wmute.clear()
            wm._wmute.update(saved[1])
            wm._warned.clear()
            wm._warned.update(saved[2])
        self.addCleanup(restore)

    def test_cards_read_non_object_falls_back_to_all(self):
        self.patch(RP, "set_cards_read", lambda: "AT")
        self.patch(RP, "mark_cards_read", lambda ks: self.fail("per-key path taken"))
        for raw in (b"[1]", b"null", b'{"keys": "notalist"}'):
            code, out, _ = post("/api/cards/read", raw)
            self.assertEqual((code, out), (200, {"ok": True, "at": "AT"}), raw)

    def test_cards_read_key_plus_keys_one_call(self):
        got = []
        self.patch(RP, "mark_cards_read", lambda ks: (got.append(ks), ["x"])[1])
        self.patch(RP, "set_cards_read", lambda: self.fail("mark-all path taken"))
        code, out, _ = post("/api/cards/read", {"key": "a", "keys": ["b", "c"]})
        self.assertEqual((code, out), (200, {"ok": True, "ids": ["x"]}))
        self.assertEqual(got, [["a", "b", "c"]])

    def test_room_invite_exception_is_reported(self):
        self.patch(RP._PostRoutes, "_room_invite", lambda self_, req: 1 / 0)
        code, out, _ = post("/api/room/invite", {"room": "r", "ids": ["a"]}, origin=OWN)
        self.assertEqual(code, 200)
        self.assertFalse(out["ok"])
        self.assertIn("ZeroDivisionError", out["vars"]["err"])

    def test_room_invite_non_object(self):
        self.patch(RP, "sessions_rows", lambda **k: self.fail("sessions read for a bad body"))
        code, out, _ = post("/api/room/invite", b"[1]", origin=OWN)
        self.assertEqual((code, out["ok"]), (200, False))

    def test_saver_set_exception_is_400(self):
        def boom(req):
            raise ValueError("x" * 500)
        self.patch(RP, "saver_set", boom)
        code, out, _ = post("/api/saver/set", {"mode": "on"})
        self.assertEqual(code, 400)
        self.assertFalse(out["ok"])
        self.assertLessEqual(len(out["err"]), 200)                # error text is capped

    def test_health_dismiss_non_object_or_non_string_key_is_400(self):
        # _body_json returns any JSON value: a list / numeric key used to raise out of do_POST.
        wm._WARN_LOG[:] = [{"key": "k1"}]
        for raw in (b"[1]", b'"s"', b"5", b'{"key": 5}', b'{"key": ["k1"]}'):
            code, out, _ = post("/api/health/dismiss", raw)
            self.assertEqual((code, out["ok"]), (400, False), raw)
        self.assertEqual(len(wm._WARN_LOG), 1)

    def test_cards_read_non_string_keys_dropped(self):
        got = []
        self.patch(RP, "mark_cards_read", lambda ks: (got.append(ks), [])[1])
        self.patch(RP, "set_cards_read", lambda: "AT")
        post("/api/cards/read", {"key": 5, "keys": ["a", 3, None, ""]})
        self.assertEqual(got, [["a"]])
        self.assertEqual(post("/api/cards/read", {"key": 5, "keys": [3]})[1], {"ok": True, "at": "AT"})

    def test_room_invite_bad_field_types(self):
        self.patch(RP, "sessions_rows", lambda **k: self.fail("sessions read for a bad body"))
        for req in ({"room": 5, "ids": ["a"]}, {"room": "r", "ids": "alice"}, {"room": "r", "ids": ["a"], "topic": 1}):
            code, out, _ = post("/api/room/invite", req, origin=OWN)
            self.assertEqual((code, out["ok"]), (200, False), req)


if __name__ == "__main__":
    unittest.main()
