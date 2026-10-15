"""sidereus.memo.BoundedMemo: LRU order, cap, stamp check, dict compatibility, thread safety."""
import os
import tempfile
import threading
import unittest
from unittest import mock

from tests._load import load, sidereus

load()
M = sidereus("memo")
T = sidereus("transcript")


class BoundedMemoTest(unittest.TestCase):
    def test_cap_evicts_least_recent(self):
        m = M.BoundedMemo(3)
        for k in "abc":
            m.put(k, k.upper())
        m.get("a")                       # refresh a
        m.put("d", "D")
        self.assertEqual(list(m), ["c", "a", "d"])
        self.assertEqual(len(m), 3)

    def test_put_existing_moves_to_end(self):
        m = M.BoundedMemo(2)
        m.put("a", 1)
        m.put("b", 2)
        m.put("a", 3)
        m.put("c", 4)
        self.assertEqual(dict(m), {"a": 3, "c": 4})

    def test_stamp(self):
        m = M.BoundedMemo(4)
        self.assertEqual(m.put("f", False, stamp=(1, 2)), False)
        self.assertIs(m.get("f", M.MISS, stamp=(1, 2)), False)   # falsy value is still a hit
        self.assertIs(m.get("f", M.MISS, stamp=(1, 3)), M.MISS)
        self.assertIsNone(m.get("nope", stamp=1))
        self.assertEqual(m["f"], ((1, 2), False))

    def test_dict_compat(self):
        m = M.BoundedMemo(4)
        m["x"] = 1                       # plain set: no eviction, no recency
        self.assertEqual(m, {"x": 1})
        self.assertEqual(m.get("y", 7), 7)
        self.assertEqual(m.pop("x"), 1)
        self.assertIsNone(m.pop("x", None))
        with self.assertRaises(KeyError):
            m.pop("x")
        m.put("k", 1)
        with mock.patch.dict(m, {"z": 2}, clear=True):
            self.assertEqual(dict(m), {"z": 2})
        self.assertEqual(dict(m), {"k": 1})
        self.assertIsInstance(m, M.BoundedMemo)
        m.clear()
        self.assertEqual(len(m), 0)

    def test_threads_stay_bounded(self):
        m = M.BoundedMemo(50)

        def work(n):
            for i in range(2000):
                m.put((n, i % 120), i)
                m.get((n, (i * 7) % 120))
        ts = [threading.Thread(target=work, args=(n,)) for n in range(6)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertLessEqual(len(m), 50)


class TailBytesTest(unittest.TestCase):
    def test_tail_bytes(self):
        fd, p = tempfile.mkstemp(prefix="sidereus-memo-")
        os.write(fd, b"0123456789")
        os.close(fd)
        try:
            self.assertEqual(T._tail_bytes(p, 4), (b"6789", 10))
            self.assertEqual(T._tail_bytes(p, 100), (b"0123456789", 10))
            with self.assertRaises(OSError):
                T._tail_bytes(p + ".missing", 4)
        finally:
            os.unlink(p)


if __name__ == "__main__":
    unittest.main()
