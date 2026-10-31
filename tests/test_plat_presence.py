"""Cursor/Copilot record-folder readers (plat_cursor, plat_copilot): allow-listed metadata only."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

cu = sidereus("plat_cursor")
cp = sidereus("plat_copilot")
cfg = sidereus("config")

NOW = 1800000000.0
SECRET = "SECRET-TITLE"
SID = "0199aaaa-bbbb-7ccc-8ddd-eeeeffff0042"


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self._cu, self._cp, self._pa = cu.root, cp.root, cfg.pid_alive
        cu.root = cp.root = lambda: self.home
        self.alive = {4242}
        cfg.pid_alive = lambda pid: pid in self.alive

    def tearDown(self):
        cu.root, cp.root, cfg.pid_alive = self._cu, self._cp, self._pa
        shutil.rmtree(self.home, ignore_errors=True)

    def touch(self, p, t, body=""):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
        os.utime(p, (t, t))


class Cursor(_Tmp):
    def chat(self, sid=SID, age=60, cwd="/w/cu", ws="h1", meta=None):
        d = os.path.join(self.home, "chats", ws, sid)
        m = meta if meta is not None else json.dumps(
            {"cwd": cwd, "createdAtMs": int((NOW - 900) * 1000), "updatedAtMs": 1, "title": SECRET})
        self.touch(os.path.join(d, "meta.json"), NOW - 900, m)
        self.touch(os.path.join(d, "store.db-wal"), NOW - age, SECRET)

    def test_allow_list_and_activity(self):
        self.chat()
        out = cu.scan(NOW - 600, 100)
        self.assertEqual(out, [{"sid": SID, "cwd": "/w/cu", "start": NOW - 900, "mtime": NOW - 60}])
        self.assertNotIn(SECRET, json.dumps(out))

    def test_window_bound(self):
        self.chat(age=601)
        self.assertEqual(cu.scan(NOW - 600, 100), [])

    def test_malformed_skipped(self):
        self.chat(meta="{not json")
        self.chat(sid="s2", meta=json.dumps(["x"]))
        self.chat(sid="s3", meta=json.dumps({"createdAtMs": 1}))
        self.assertEqual(cu.scan(NOW - 600, 100), [])

    def test_windows_cwd_kept(self):
        self.chat(cwd="C:\\x")
        self.assertEqual(cu.scan(NOW - 600, 100)[0]["cwd"], "C:\\x")

    def test_cap(self):
        for i in range(5):
            self.chat(sid="s%d" % i)
        self.assertEqual(len(cu.scan(NOW - 600, 3)), 3)

    def test_cap_keeps_freshest_in_old_workspace(self):
        for i in range(305):
            self.chat(sid="n%03d" % i, ws="new", age=300)
        self.chat(sid="fresh", ws="old", age=1)
        os.utime(os.path.join(self.home, "chats", "new"), (NOW, NOW))
        os.utime(os.path.join(self.home, "chats", "old"), (NOW - 9999, NOW - 9999))
        out = cu.scan(NOW - 600, 300, 3000)
        self.assertEqual(len(out), 300)
        self.assertEqual(out[0]["sid"], "fresh")


class Copilot(_Tmp):
    def sess(self, sid=SID, pid=4242, cwd="/w/cp", yaml=None, lock=True):
        d = os.path.join(self.home, "session-state", sid)
        y = yaml if yaml is not None else (
            "id: %s\ncwd: %s\ngit_root: /w\nbranch: main\nclient_name: cli\nname: %s\nsummary: %s\n"
            "created_at: 2027-01-15T08:00:00.000Z\nupdated_at: 2027-01-15T08:05:00.000Z\n" % (sid, cwd, SECRET, SECRET))
        self.touch(os.path.join(d, "workspace.yaml"), NOW - 900, y)
        self.touch(os.path.join(d, "events.jsonl"), NOW - 30, SECRET)
        if lock:
            self.touch(os.path.join(d, "inuse.%d.lock" % pid), NOW - 900)

    def test_allow_list_live(self):
        self.sess()
        out = cp.scan(100)
        self.assertEqual(len(out), 1)
        self.assertEqual(set(out[0]), {"sid", "cwd", "branch", "start", "mtime", "locks"})
        self.assertEqual(out[0]["locks"], [(4242, NOW - 900)])
        self.assertEqual((out[0]["sid"], out[0]["cwd"], out[0]["branch"], out[0]["mtime"]), (SID, "/w/cp", "main", NOW - 30))
        self.assertGreater(out[0]["start"], 0)
        self.assertNotIn(SECRET, json.dumps(out))

    def test_yaml_never_keeps_name(self):
        p = os.path.join(self.home, "y.yaml")
        self.touch(p, NOW, "id: a\nname: %s\nsummary_count: 3\nsummary: %s\n" % (SECRET, SECRET))
        self.assertEqual(cp._yaml(p), {"id": "a"})

    def test_dead_or_missing_lock(self):
        self.sess(pid=99)
        self.sess(sid="nolock", lock=False)
        self.assertEqual(cp.scan(100), [])

    def test_malformed_skipped(self):
        self.sess(yaml="::::\n- [")
        self.sess(sid="other", yaml="id: different\ncwd: /w\n")
        self.assertEqual(cp.scan(100), [])

    def test_windows_cwd_kept(self):
        self.sess(cwd="C:\\x")
        self.assertEqual(cp.scan(100)[0]["cwd"], "C:\\x")

    def test_cap(self):
        for i in range(5):
            self.sess(sid="s%d" % i, yaml="id: s%d\ncwd: /w\n" % i)
        self.assertEqual(len(cp.scan(3)), 3)

    def test_copilot_home_absolute_only(self):
        self.assertTrue(cp._root_for("rel/dir").endswith(".copilot"))
        self.assertTrue(cp._root_for("").endswith(".copilot"))
        self.assertEqual(cp._root_for(self.home), self.home)


if __name__ == "__main__":
    unittest.main()
