"""Room pills (buildRooms) and placement (soleRoom/absorbed/inPlace) share one room list: roomNames(). Runs JS through node."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


@unittest.skipUnless(shutil.which("node"), "node not installed")
class RoomAbsorb(unittest.TestCase):
    def run_js(self, rooms, msgs, expr):
        src = "let ROOMS = " + json.dumps(rooms) + ", MSGS = " + json.dumps(msgs) + ";\n" \
            + "\n".join(js_fn(n) for n in ("roomNames", "soleRoom", "absorbed", "inPlace")) \
            + "\nprocess.stdout.write(JSON.stringify(" + expr + "));"
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        return json.loads(r.stdout)

    def test_undefined_room_in_post_is_not_sole(self):
        msgs = [{"room": "ghost", "body": "x"}, {"body": "public"}]
        self.assertEqual(self.run_js({"main": {}}, msgs, "roomNames()"), ["ghost", "main"])
        self.assertEqual(self.run_js({"main": {}}, msgs, "soleRoom()"), "")
        self.assertFalse(self.run_js({"main": {}}, msgs, "absorbed(MSGS[1])"))
        self.assertTrue(self.run_js({"main": {}}, msgs, "inPlace(MSGS[1], 'dm')"))

    def test_one_room_public_roomless_absorbed(self):
        msgs = [{"room": "main"}, {"body": "public"}]
        self.assertEqual(self.run_js({"main": {}}, msgs, "soleRoom()"), "main")
        self.assertTrue(self.run_js({"main": {}}, msgs, "absorbed(MSGS[1])"))
        self.assertTrue(self.run_js({"main": {}}, msgs, "inPlace(MSGS[1], 'room:main')"))
        self.assertFalse(self.run_js({"main": {}}, msgs, "inPlace(MSGS[1], 'dm')"))

    def test_dm_never_absorbed(self):
        msgs = [{"room": "main"}, {"to": "bob"}]
        self.assertFalse(self.run_js({"main": {}}, msgs, "absorbed(MSGS[1])"))
        self.assertTrue(self.run_js({"main": {}}, msgs, "inPlace(MSGS[1], 'dm')"))
        self.assertFalse(self.run_js({"main": {}}, msgs, "inPlace(MSGS[1], 'room:main')"))


if __name__ == "__main__":
    unittest.main()
