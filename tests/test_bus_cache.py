"""Parse cache in sidereus/bus.py: messages() and ack_map() on temp files only (never the live bus/acks)."""
import json
import os
import shutil
import tempfile
import time
import types
import unittest

from tests._load import sidereus

bus = sidereus("bus")
import mailbox_core  # noqa: E402  (on sys.path after the loader)

NOW = 1_800_000_000 * 10 ** 9


class BusCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.bus_path = os.path.join(self.tmp, "bus.jsonl")
        self.acks_path = os.path.join(self.tmp, "acks.jsonl")
        self._saved = (bus.BUS, mailbox_core.ACKS, bus.time)
        bus.BUS, mailbox_core.ACKS = self.bus_path, self.acks_path
        bus.time = types.SimpleNamespace(time_ns=lambda: NOW, time=time.time)
        with bus._parse_lock:
            bus._parse_cache.clear()

    def tearDown(self):
        bus.BUS, mailbox_core.ACKS, bus.time = self._saved
        with bus._parse_lock:
            bus._parse_cache.clear()
        shutil.rmtree(self.tmp)

    def write(self, path, recs, mode="w"):
        with open(path, mode, encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")

    def test_since_filter_and_sort(self):
        self.write(self.bus_path, [{"id": "b", "t": 20}, {"id": "a", "t": 10}, {"id": "c", "t": 30}])
        self.assertEqual([m["id"] for m in bus.messages(0)], ["a", "b", "c"])
        self.assertEqual([m["id"] for m in bus.messages(10)], ["b", "c"])   # cached parse, filter per call
        self.assertEqual(bus.messages(30), [])

    def test_append_misses(self):
        self.write(self.bus_path, [{"id": "a", "t": 10}])
        self.assertEqual(len(bus.messages(0)), 1)
        self.write(self.bus_path, [{"id": "b", "t": 20}], mode="a")
        self.assertEqual([m["id"] for m in bus.messages(0)], ["a", "b"])

    def test_same_size_replace_new_inode_misses(self):
        self.write(self.bus_path, [{"id": "a", "t": 10}])
        st = os.stat(self.bus_path)
        self.assertEqual(bus.messages(0)[0]["id"], "a")
        other = os.path.join(self.tmp, "new.jsonl")
        self.write(other, [{"id": "z", "t": 10}])
        os.utime(other, ns=(st.st_atime_ns, st.st_mtime_ns))   # same size and mtime: only the inode differs
        os.replace(other, self.bus_path)
        self.assertEqual(os.stat(self.bus_path).st_size, st.st_size)
        self.assertNotEqual(os.stat(self.bus_path).st_ino, st.st_ino)
        self.assertEqual(bus.messages(0)[0]["id"], "z")

    def test_mutation_does_not_leak(self):
        self.write(self.bus_path, [{"id": "a", "t": 10, "to": ["x"]}])
        r = bus.messages(0)
        r[0]["to"].append("y"); r[0]["id"] = "hacked"; r.clear()
        self.assertEqual(bus.messages(0), [{"id": "a", "t": 10, "to": ["x"]}])
        self.write(self.acks_path, [{"id": "m1", "who": "bob", "t": NOW - 1},
                                    {"id": "m1", "who": "bob", "kind": "ack", "note": "ok", "t": NOW - 1}])
        a = bus.ack_map()
        a["m1"]["delivered"].append("eve"); a["m1"]["ack"].clear(); a.clear()
        self.assertEqual(bus.ack_map(), {"m1": {"delivered": ["bob"], "ack": [{"who": "bob", "note": "ok"}]}})

    def test_hooked_listed_apart_from_delivered(self):
        self.write(self.acks_path, [{"id": "m1", "who": "bob", "kind": "delivered", "t": NOW - 1},
                                    {"id": "m2", "who": "bob", "kind": "hooked", "t": NOW - 1}])
        a = bus.ack_map()
        self.assertEqual(a["m1"], {"delivered": ["bob"], "ack": []})            # watcher only: no hooked key
        self.assertEqual(a["m2"], {"delivered": ["bob"], "ack": [], "hooked": ["bob"]})

    def test_ack_cut_applied_after_cache(self):
        old_t = NOW - bus.ACK_KEEP_S * 10 ** 9 + 5
        self.write(self.acks_path, [{"id": "m1", "who": "bob", "t": old_t}])
        self.assertIn("m1", bus.ack_map())
        bus.time = types.SimpleNamespace(time_ns=lambda: NOW + 10, time=time.time)   # clock moves, file does not
        self.assertEqual(bus.ack_map(), {})

    def test_ack_append_misses(self):
        self.write(self.acks_path, [{"id": "m1", "who": "bob", "t": NOW - 1}])
        self.assertEqual(set(bus.ack_map()), {"m1"})
        self.write(self.acks_path, [{"id": "m2", "who": "amy", "t": NOW - 1}], mode="a")
        self.assertEqual(set(bus.ack_map()), {"m1", "m2"})

    def test_missing_acks_is_silent_other_errors_warn(self):
        calls = []
        saved = bus.warn_once
        bus.warn_once = lambda key, *a, **k: calls.append(key)
        try:
            self.assertEqual(bus.ack_map(), {})             # fresh install: no acks.jsonl
            self.assertEqual(bus.messages(0), [])           # ... and no bus.jsonl
            self.assertEqual(calls, [])
            self.write(self.bus_path, [{"id": "a", "t": 10}])   # file appears: the "missing" cache entry misses
            self.assertEqual([m["id"] for m in bus.messages(0)], ["a"])
            os.mkdir(os.path.join(self.tmp, "d"))
            bus.BUS = os.path.join(self.tmp, "d")           # unreadable (a directory): still warned
            self.assertEqual(bus.messages(0), [])
            self.assertEqual(calls, ["bus"])
            calls.clear()
            self.write(self.acks_path, [])                  # file exists but reading fails: still warned
            with bus._parse_lock:
                bus._parse_cache.clear()
            saved_acks = mailbox_core.acks
            mailbox_core.acks = lambda: (_ for _ in ()).throw(PermissionError("denied"))
            try:
                self.assertEqual(bus.ack_map(), {})
            finally:
                mailbox_core.acks = saved_acks
            self.assertEqual(calls, ["ack-map"])
        finally:
            bus.warn_once = saved


if __name__ == "__main__":
    unittest.main()
