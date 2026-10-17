"""Chat compose target (web/js/10-feed.js chatTarget): replies go back to their source; a new post goes to the open
room, or in «방 밖 글» to the default room named by the page (the server never picks one — test_routes_post_say_dm)."""
import json
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def run(state):
    js = ("let MSGS, place, replyTo, CFG;\n" + js_fn("chatTarget") + "\n"
          "function soleRoom(){ return SOLE; }\nfunction absorbed(m){ return !m.room && !m.to && !!SOLE; }\n"
          "const S = " + json.dumps(state) + ";\nvar SOLE = S.sole || '';\n"
          "MSGS = S.msgs || []; place = S.place; replyTo = S.reply || null; CFG = S.cfg || {};\n"
          "process.stdout.write(JSON.stringify(chatTarget()));")
    return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


CFG = {"defaultRoom": "general", "viewerMe": "me"}
MSGS = [{"id": "r1", "room": "dev", "from": "a"},
        {"id": "d1", "to": "me", "from": "alice"},
        {"id": "d2", "to": "bob", "from": "me"},
        {"id": "p1", "from": "a"}]


class ChatTarget(unittest.TestCase):
    def t(self, **k):
        return run(dict({"msgs": MSGS, "cfg": CFG}, **k))

    def test_new_post_in_room_goes_to_that_room(self):
        self.assertEqual(self.t(place="room:dev"), {"room": "dev"})

    def test_new_post_outside_rooms_goes_to_named_default(self):
        self.assertEqual(self.t(place="dm"), {"room": "general", "dflt": True})
        self.assertIsNone(self.t(place="dm", cfg={}))            # no default configured: nothing to send to

    def test_replies_follow_their_source(self):
        self.assertEqual(self.t(place="dm", reply="r1"), {"room": "dev"})
        self.assertEqual(self.t(place="dm", reply="d1"), {"to": "alice"})      # DM to me -> back to the sender
        self.assertEqual(self.t(place="dm", reply="d2"), {"to": "bob"})        # my own DM -> same peer
        self.assertEqual(self.t(place="room:dev", reply="d1"), {"to": "alice"})

    def test_roomless_public_reply(self):
        self.assertEqual(self.t(place="room:x", reply="p1", sole="x"), {"room": "x"})      # absorbed into the sole room
        self.assertEqual(self.t(place="dm", reply="p1"), {"room": "general", "dflt": True})


if __name__ == "__main__":
    unittest.main()
