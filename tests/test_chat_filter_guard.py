"""Chat filter guards: every filter write goes through setFilter, which never stores undefined."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


class NoDirectAssign(unittest.TestCase):
    def test_only_setfilter_assigns_filter(self):
        # Every chat-filter write goes through setFilter (declaration in 05-i18n.js and setFilter itself excepted).
        import re
        from tests._load import js_all
        hits = [ln.strip() for ln in js_all().splitlines()
                if re.search(r"(^|[^.\w$])filter\s*=(?!=)", ln.split("//")[0])
                and not ln.startswith("let filter=") and not ln.startswith("function setFilter(")]
        self.assertEqual(hits, [])


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SetFilter(unittest.TestCase):
    def run_js(self, rooms, msgs, body):
        js = ("let filter='x', place='room:keep', ROOMS=" + json.dumps(rooms) + ", MSGS=" + json.dumps(msgs) + ";\n"
              + "\n".join(js_fn(n) for n in ("roomNames", "soleRoom", "absorbed", "chatFilterKey", "setFilter"))
              + "\nconst o=[];" + body + "process.stdout.write(JSON.stringify(o));")
        r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_missing_key_falls_back_to_all(self):
        got = self.run_js({}, [], "for(const k of [undefined, '', null, 'waiting']){ setFilter(k); o.push(filter); }")
        self.assertEqual(got, ["all", "all", "all", "waiting"])

    def test_thread_key_opens_its_room_not_a_hidden_filter(self):
        msgs = [{"room": "a", "thread": "t1"}, {"room": "b"}, {"to": "bob", "thread": "t2"}]
        body = ("for(const k of ['thread:t1', 'thread:t2', 'thread:gone']){ place='room:keep'; setFilter(k); o.push([filter, place]); }")
        self.assertEqual(self.run_js({"a": {}, "b": {}}, msgs, body),
                         [["all", "room:a"], ["all", "dm"], ["all", "all"]])

    def test_absorbed_thread_opens_sole_room(self):
        msgs = [{"room": "a"}, {"thread": "t3"}]
        self.assertEqual(self.run_js({"a": {}}, msgs, "setFilter('thread:t3'); o.push(filter, place);"), ["all", "room:a"])


if __name__ == "__main__":
    unittest.main()
