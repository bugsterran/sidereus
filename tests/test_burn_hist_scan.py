"""Incremental transcript token scan (burn_hist._tok_scan) equals a full rescan. Temp fixtures only."""
import builtins
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

from tests import _load

h = _load.sidereus("burn_hist")
T0 = 1.7e9


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def line(t, mid, rid, n):
    return json.dumps({"timestamp": iso(t), "requestId": rid,
                       "message": {"id": mid, "usage": {"input_tokens": n, "output_tokens": 1}}}) + "\n"


def full_scan(root, t0):
    """Reference: the pre-cache scan (every file read from byte 0)."""
    ev, seen = [], {}
    for d, _s, fs in sorted(os.walk(root)):
        for fn in sorted(fs):
            fp = os.path.join(d, fn)
            if not fn.endswith(".jsonl") or os.stat(fp).st_mtime < t0:
                continue
            with open(fp, encoding="utf-8") as f:
                for ln in f:
                    e = json.loads(ln)
                    m = e["message"]
                    t = h.iso_epoch(e["timestamp"], None)
                    k = (m.get("id"), e.get("requestId"))
                    n = sum(int(m["usage"].get(x) or 0) for x in h._TOK_KEYS)
                    if t < t0:
                        continue
                    if k != (None, None) and k in seen:   # duplicate key: the earliest copy wins
                        if t < ev[seen[k]][0]:
                            ev[seen[k]] = (t, n)
                        continue
                    if k != (None, None):
                        seen[k] = len(ev)
                    ev.append((t, n))
    return ev


class TokScan(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="burn-scan-")
        os.makedirs(os.path.join(self.d, "p"))
        p = mock.patch.object(h, "CLAUDE_PROJECTS", self.d)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.d, True)
        h._tok_files.clear()
        self.addCleanup(h._tok_files.clear)

    def fp(self, name):
        return os.path.join(self.d, "p", name)

    def add(self, name, *lines):
        with open(self.fp(name), "a", encoding="utf-8") as f:
            f.write("".join(lines))

    def check(self, t0):
        self.assertEqual(sorted(h._tok_scan(t0)), sorted(full_scan(self.d, t0)))

    def test_incremental_equals_full_over_appends(self):
        self.add("a.jsonl", line(T0 + 1, "m1", "r1", 10), line(T0 + 2, "m2", "r2", 20))
        self.check(T0)
        self.add("a.jsonl", line(T0 + 3, "m3", "r3", 30))
        self.add("b.jsonl", line(T0 + 4, "m4", "r4", 40))
        self.check(T0)
        self.add("a.jsonl", line(T0 + 5, None, None, 7), line(T0 + 6, None, None, 7))   # keyless lines all count
        self.check(T0)
        self.assertEqual(sum(n for _t, n in h._tok_scan(T0)), 11 + 21 + 31 + 41 + 8 + 8)

    def test_cross_file_duplicate_counted_once(self):
        self.add("a.jsonl", line(T0 + 1, "m1", "r1", 10))
        self.add("b.jsonl", line(T0 + 1, "m1", "r1", 10))
        h._tok_scan(T0)
        self.add("c.jsonl", line(T0 + 2, "m1", "r1", 10))       # a later copy in a new file
        self.assertEqual(h._tok_scan(T0), [(T0 + 1, 11)])
        self.check(T0)

    def test_duplicate_keeps_earliest_regardless_of_listing_order(self):
        # glob order is filesystem-defined (APFS sorted, ext4 hash order): the kept copy must not depend on it
        self.add("a.jsonl", line(T0 + 1, "m1", "r1", 10))
        self.add("c.jsonl", line(T0 + 2, "m1", "r1", 10))
        real = h.glob.glob
        for order in (sorted, lambda xs: sorted(xs, reverse=True)):
            h._tok_files.clear()
            with mock.patch.object(h.glob, "glob", lambda *a, **k: order(real(*a, **k))):
                self.assertEqual(h._tok_scan(T0), [(T0 + 1, 11)])

    def test_t0_forward_and_back(self):
        self.add("a.jsonl", *(line(T0 + i, "m%d" % i, "r", i) for i in range(10)))
        self.check(T0)
        self.check(T0 + 5)                                       # prunes older events
        self.check(T0 + 2)                                       # earlier t0 again -> rereads from byte 0
        self.check(T0 + 2)

    def test_replace_shrink_and_removed_file(self):
        self.add("a.jsonl", line(T0 + 1, "m1", "r1", 10), line(T0 + 2, "m2", "r2", 20))
        self.add("b.jsonl", line(T0 + 3, "m3", "r3", 30))
        self.check(T0)
        tmp = self.fp("new.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(line(T0 + 9, "m9", "r9", 90))
        os.replace(tmp, self.fp("a.jsonl"))                      # new inode, shorter
        self.check(T0)
        os.remove(self.fp("b.jsonl"))
        self.check(T0)
        self.assertEqual(list(h._tok_files), [self.fp("a.jsonl")])

    def test_partial_last_line_waits(self):
        whole = line(T0 + 2, "m2", "r2", 20)
        self.add("a.jsonl", line(T0 + 1, "m1", "r1", 10), whole[:15])
        self.assertEqual(h._tok_scan(T0), [(T0 + 1, 11)])
        self.add("a.jsonl", whole[15:])
        self.check(T0)

    def test_no_change_pass_opens_nothing(self):
        for i in range(5):
            self.add("f%d.jsonl" % i, line(T0 + i, "m%d" % i, "r", 5))
        first = h._tok_scan(T0)
        opens = []
        real = builtins.open

        def spy(*a, **k):
            opens.append(a[0])
            return real(*a, **k)
        with mock.patch.object(builtins, "open", spy):
            again = h._tok_scan(T0)
        self.assertEqual(again, first)
        self.assertEqual(opens, [])


if __name__ == "__main__":
    unittest.main()
