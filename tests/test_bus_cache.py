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
        self.assertEqual([m["id"] for m in bus.messages(10, 0)], ["b", "c"])   # cached parse, filter per call
        self.assertEqual(bus.messages(30, 0), [])

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
        # clock moves one cut step (the cut is floored to ACK_CUT_STEP_S), file does not
        bus.time = types.SimpleNamespace(time_ns=lambda: NOW + bus.ACK_CUT_STEP_S * 10 ** 9, time=time.time)
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
            mailbox_core.ACKS = os.path.join(self.tmp, "d")  # acks path exists but reading fails: still warned
            self.assertIsInstance(bus.ack_map(), bus.AckMapError)   # unknown, not an empty map with a version
            self.assertEqual(calls, ["ack-map"])
        finally:
            bus.warn_once = saved


class BusIncremental(unittest.TestCase):
    """Append-only logs fold only the new complete lines; the result must equal a full parse (S3)."""

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

    def raw(self, path, text, mode="a"):
        with open(path, mode, encoding="utf-8") as f:
            f.write(text)

    def _fresh(self, path, fold):
        with bus._parse_lock:
            saved = bus._parse_cache.pop(path, None)
        try:
            return fold(None, bus._read_tail(path, 0, b"")[0], None)
        finally:
            with bus._parse_lock:
                if saved is not None:
                    bus._parse_cache[path] = saved

    def test_bus_append_equals_full_and_reads_only_the_tail(self):
        self.raw(self.bus_path, json.dumps({"id": "a", "t": 30}) + "\n" + json.dumps({"id": "b", "t": 10}) + "\n", "w")
        bus._cached(self.bus_path, bus._bus_parse)
        reads = []
        real = bus._read_tail
        bus._read_tail = lambda p, off, sig: reads.append(off) or real(p, off, sig)
        try:
            self.raw(self.bus_path, json.dumps({"id": "c", "t": 20}) + "\n" + "{broken\n" + json.dumps({"id": "d", "t": 10}) + "\n")
            got = bus._cached(self.bus_path, bus._bus_parse)
        finally:
            bus._read_tail = real
        self.assertEqual(len(reads), 1)
        self.assertGreater(reads[0], 0)                          # incremental: started past the cached lines
        self.assertEqual(got, self._fresh(self.bus_path, bus._bus_parse))
        self.assertEqual([json.loads(l)["id"] for _t, l in got[0]], ["b", "d", "c", "a"])   # stable by t, file order on ties
        self.assertEqual(got[1], 1)

    def test_partial_last_line_held_back_then_counted_once(self):
        self.raw(self.bus_path, json.dumps({"id": "a", "t": 10}) + "\n", "w")
        self.raw(self.acks_path, json.dumps({"id": "m1", "who": "bob", "t": NOW - 1}) + "\n", "w")
        self.assertEqual([m["id"] for m in bus.messages(0)], ["a"])
        bus.ack_map()
        line = json.dumps({"id": "b", "t": 20}) + "\n"
        ack = json.dumps({"id": "m1", "who": "amy", "kind": "ack", "note": "ok", "t": NOW - 1}) + "\n"
        self.raw(self.bus_path, line[:9])                       # writer mid-append
        self.raw(self.acks_path, ack[:12])
        self.assertEqual([m["id"] for m in bus.messages(0)], ["a"])
        self.assertEqual(bus._cached(self.bus_path, bus._bus_parse)[1], 0)   # not counted as a broken line
        self.assertEqual(bus.ack_map()["m1"]["ack"], [])
        self.raw(self.bus_path, line[9:])
        self.raw(self.acks_path, ack[12:])
        self.assertEqual([m["id"] for m in bus.messages(0)], ["a", "b"])
        self.assertEqual(bus._cached(self.bus_path, bus._bus_parse), self._fresh(self.bus_path, bus._bus_parse))
        self.assertEqual(bus.ack_map()["m1"], {"delivered": ["bob"], "ack": [{"who": "amy", "note": "ok"}]})

    def test_truncation_and_rewrite_fall_back_to_full(self):
        self.raw(self.bus_path, "".join(json.dumps({"id": "m%d" % i, "t": i}) + "\n" for i in range(1, 6)), "w")
        self.assertEqual(len(bus.messages(0)), 5)
        self.raw(self.bus_path, json.dumps({"id": "x", "t": 1}) + "\n", "w")        # truncated in place, same inode
        self.assertEqual([m["id"] for m in bus.messages(0)], ["x"])
        self.raw(self.bus_path, json.dumps({"id": "y", "t": 2}) + "\n", "w")        # rewritten in place, grown later
        self.raw(self.bus_path, json.dumps({"id": "z", "t": 3}) + "\n")
        self.assertEqual([m["id"] for m in bus.messages(0)], ["y", "z"])
        self.assertEqual(bus._cached(self.bus_path, bus._bus_parse), self._fresh(self.bus_path, bus._bus_parse))

    def test_ack_fold_matches_mailbox_core_and_keeps_old_value(self):
        recs = [{"id": "m1", "who": "bob", "t": NOW - 5}, {"id": "m1", "who": "bob", "kind": "hooked", "t": NOW - 4},
                {"id": "m2", "who": "amy", "kind": "ack", "note": "n", "t": NOW - 3}]
        self.raw(self.acks_path, "".join(json.dumps(r) + "\n" for r in recs[:2]), "w")
        first = bus._cached(self.acks_path, bus._ack_fold)[0]
        snap = json.loads(json.dumps(first))
        more = [{"id": "m1", "who": "eve", "kind": "ack", "note": "late", "t": NOW - 1}, {"id": "m1", "who": "bob", "t": NOW - 2}]
        self.raw(self.acks_path, "".join(json.dumps(r) + "\n" for r in recs[2:] + more))
        got = bus._cached(self.acks_path, bus._ack_fold)
        self.assertIsNone(got[1])
        self.assertEqual(got[0], mailbox_core.acks())            # one merge rule: same result as the MCP side
        self.assertEqual(first, snap)                             # the earlier value was not mutated in place

    def test_acks_skips_malformed_record_and_keeps_later_ones(self):
        self.raw(self.acks_path, json.dumps({"id": "m1", "who": "bob", "t": 5}) + "\n"
                 + "[1, 2]\n" + json.dumps({"id": "m1", "who": "x", "t": "soon"}) + "\n"
                 + json.dumps({"id": ["m"], "who": "x", "t": 6}) + "\n" + "{broken\n" + "  \n"
                 + json.dumps({"id": "m2", "who": "amy", "kind": "ack", "note": "ok", "t": 7}) + "\n", "w")
        self.assertEqual(mailbox_core.acks(), {
            "m1": {"delivered": ["bob"], "ack": [], "t": 5},
            "m2": {"delivered": [], "ack": [{"who": "amy", "at": 7, "note": "ok"}], "t": 7}})

    def test_ack_fold_copies_shared_entry_before_change(self):
        shared = {"m1": {"delivered": ["bob"], "ack": [], "t": 5}}
        out = dict(shared)
        own = set()
        mailbox_core.ack_fold(out, [json.dumps({"id": "m1", "who": "amy", "kind": "hooked", "t": 9}),
                                    json.dumps({"id": "m2", "who": "eve", "t": 3})], own)
        self.assertEqual(shared, {"m1": {"delivered": ["bob"], "ack": [], "t": 5}})   # cached map untouched
        self.assertEqual(out, {"m1": {"delivered": ["bob", "amy"], "ack": [], "t": 9, "hooked": ["amy"]},
                               "m2": {"delivered": ["eve"], "ack": [], "t": 3}})
        self.assertEqual(own, {"m1", "m2"})


class BusSlack(unittest.TestCase):
    """A post stamped earlier but appended after a later one still reaches a poll whose since passed it (S7)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._saved = bus.BUS
        bus.BUS = os.path.join(self.tmp, "bus.jsonl")
        with bus._parse_lock:
            bus._parse_cache.clear()

    def tearDown(self):
        bus.BUS = self._saved
        with bus._parse_lock:
            bus._parse_cache.clear()
        shutil.rmtree(self.tmp)

    def test_late_append_inside_slack_is_served(self):
        t = NOW
        with open(bus.BUS, "w", encoding="utf-8") as f:
            f.write(json.dumps({"id": "later", "t": t + 10 ** 9}) + "\n")
        since = max(m["t"] for m in bus.messages(0))              # poll advanced past the later post
        with open(bus.BUS, "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": "early", "t": t}) + "\n")   # stamped first, appended second
            f.write(json.dumps({"id": "old", "t": t - bus.MSG_SLACK_NS}) + "\n")
        self.assertEqual({m["id"] for m in bus.messages(since)}, {"later", "early"})   # page dedups "later" by id
        self.assertNotIn("old", {m["id"] for m in bus.messages(since)})                 # window stays small
        self.assertEqual(bus.messages(since, 0), [])
        self.assertEqual([m["id"] for m in bus.messages_range(t, None, 10)], ["later"])   # range fetch stays exact


class BusAppendOrder(unittest.TestCase):
    """Viewer writes land in strict `t` order: _bus_append re-stamps under one lock (watermark readers use t > seen)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._saved = (bus.BUS, bus.time, bus._last_append_t)
        bus.BUS = os.path.join(self.tmp, "bus.jsonl")
        bus._last_append_t = 0

    def tearDown(self):
        bus.BUS, bus.time, bus._last_append_t = self._saved
        shutil.rmtree(self.tmp)

    def lines(self):
        with open(bus.BUS, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    def test_stale_stamp_is_replaced(self):
        bus.time = types.SimpleNamespace(time_ns=lambda: NOW, time=time.time)
        bus._bus_append({"id": "a", "t": NOW + 50})     # caller stamped later than this append
        bus._bus_append({"id": "b", "t": NOW - 50})     # caller stamped earlier, appended second
        ts = [r["t"] for r in self.lines()]
        self.assertEqual(ts, [NOW, NOW + 1])            # file order = t order

    def test_same_clock_value_still_increases(self):
        bus.time = types.SimpleNamespace(time_ns=lambda: NOW, time=time.time)   # coarse clock: same value twice
        for i in range(3):
            bus._bus_append({"id": str(i), "t": 0})
        self.assertEqual([r["t"] for r in self.lines()], [NOW, NOW + 1, NOW + 2])

    def test_threads_append_in_t_order(self):
        import threading
        ths = [threading.Thread(target=bus._bus_append, args=({"id": str(i), "t": 0},)) for i in range(16)]
        for th in ths:
            th.start()
        for th in ths:
            th.join()
        ts = [r["t"] for r in self.lines()]
        self.assertEqual(len(ts), 16)
        self.assertEqual(ts, sorted(set(ts)))


if __name__ == "__main__":
    unittest.main()
