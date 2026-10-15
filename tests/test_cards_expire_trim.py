"""Cards: batch read (one write), auto-expire ages, daily trim vs concurrent append, dedup window vs trim (temp files only)."""
import glob
import json
import os
import re
import shutil
import tempfile
import threading
import time
import unittest
from datetime import datetime
from unittest import mock

from tests._load import sidereus, ROOT

cards = sidereus("cards")
notes = sidereus("notes")

NOW = datetime(2026, 9, 24, 12, 0, 0).timestamp()


def _iso(ago_s):
    return datetime.fromtimestamp(NOW - ago_s).isoformat(timespec="seconds")


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.p = [mock.patch.object(cards, "READ_IDS", os.path.join(self.d, "ids.txt")),
                  mock.patch.object(cards, "READ_MARK", os.path.join(self.d, "mark.txt")),
                  mock.patch.object(cards, "CARDS", os.path.join(self.d, "cards.jsonl"))]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        shutil.rmtree(self.d, ignore_errors=True)

    def write_cards(self, rows):
        with open(cards.CARDS, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")


class BatchReadTest(_Tmp):
    def test_many_keys_one_write(self):
        real, n = cards._atomic_write, []

        def counted(*a, **k):
            n.append(1)
            return real(*a, **k)

        keys = ["2026-09-24T10:00:%02d|agent|p" % i for i in range(50)]
        with mock.patch.object(cards, "_atomic_write", counted):
            cards.mark_cards_read(keys + [keys[0], "", "bad\nkey"])
        self.assertEqual(len(n), 1)
        self.assertEqual(cards.cards_read_ids(), keys)

    def test_single_key_still_works(self):
        cards.mark_cards_read(["2026-09-24T10:00:00|ask|a"])
        cards.mark_cards_read(["2026-09-24T10:00:01|ask|b"])
        self.assertEqual(cards.cards_read_ids(), ["2026-09-24T10:00:00|ask|a", "2026-09-24T10:00:01|ask|b"])


class MarkAllVsBatchTest(_Tmp):
    def test_mark_all_waits_for_batch_write(self):
        real, entered, release = cards._atomic_write, threading.Event(), threading.Event()

        def slow(path, *a, **k):
            if path == cards.READ_IDS:
                entered.set()
                release.wait(2)
            return real(path, *a, **k)

        with mock.patch.object(cards, "_atomic_write", slow):
            tb = threading.Thread(target=cards.mark_cards_read, args=(["2026-09-24T10:00:00|ask|a"],))
            tb.start()
            self.assertTrue(entered.wait(2))
            ta = threading.Thread(target=cards.set_cards_read, args=("2026-09-24T11:00:00",))
            ta.start()
            ta.join(0.2)
            self.assertTrue(ta.is_alive())     # blocked on the shared lock, not interleaving
            release.set()
            tb.join()
            ta.join()
        self.assertEqual(cards.cards_read(), "2026-09-24T11:00:00")
        self.assertFalse(os.path.exists(cards.READ_IDS))   # mark-all ran last and cleared the batch
        self.assertEqual(sorted(os.listdir(self.d)), ["mark.txt"])   # no half-written temp files


class ExpireTest(_Tmp):
    def test_ages(self):
        h = 3600
        self.write_cards([
            {"at": _iso(25 * h), "kind": "agent", "project": "a"},
            {"at": _iso(23 * h), "kind": "ask", "project": "b"},
            {"at": _iso(4 * 24 * h), "kind": "fwreck", "project": "c"},
            {"at": _iso(2 * 24 * h), "kind": "flimit", "project": "d"},
        ])
        got = {c["project"]: bool(c.get("old")) for c in cards.cards(10, now=NOW)}
        self.assertEqual(got, {"a": True, "b": False, "c": True, "d": False})
        self.assertEqual(cards.CARD_EXPIRE_S, 24 * h)
        self.assertEqual(cards.FAIL_CARD_EXPIRE_S, 3 * 24 * h)


class TrimTest(_Tmp):
    def test_trim_drops_old_and_keeps_concurrent_append(self):
        self.write_cards([{"at": _iso(8 * 86400), "kind": "agent", "project": "old"},
                          {"at": _iso(3600), "kind": "agent", "project": "new"}])
        real = cards._atomic_write
        th = []

        class Probe:
            """_cards_lock stand-in that signals when a second caller has to block on it."""
            def __init__(self, lk):
                self.lk, self.blocked = lk, threading.Event()

            def __enter__(self):
                if not self.lk.acquire(False):
                    self.blocked.set()
                    self.lk.acquire()
                return self

            def __exit__(self, *exc):
                self.lk.release()

        probe = Probe(threading.Lock())

        def racing_write(*a, **k):
            # An append arriving mid-trim must wait for the lock, not land in the file that is about to be replaced.
            t = threading.Thread(target=cards._card_add, args=("ask", "raced", "t"))
            t.start()
            th.append(t)
            self.assertTrue(probe.blocked.wait(2))       # the append is now parked on the lock
            return real(*a, **k)

        # Production path: the daily trim runs inside _card_add, under _cards_lock.
        with mock.patch.dict(cards._TRIM, {"at": 0.0}), \
                mock.patch.object(cards, "time", mock.Mock(time=lambda: NOW)), \
                mock.patch.object(cards, "_cards_lock", probe), \
                mock.patch.object(cards, "_atomic_write", racing_write):
            cards._card_add("agent", "trigger", "t")
            for t in th:
                t.join()
        self.assertEqual(len(th), 1)
        with open(cards.CARDS, encoding="utf-8") as f:
            projs = [json.loads(ln)["project"] for ln in f]
        self.assertEqual(projs, ["new", "trigger", "raced"])

    def test_no_rewrite_when_nothing_old(self):
        self.write_cards([{"at": _iso(60), "kind": "agent", "project": "n"}])
        with mock.patch.object(cards, "_atomic_write") as w:
            self.assertEqual(cards._trim_cards_locked(now=NOW), (1, 0))
        w.assert_not_called()


class DedupWindowTest(unittest.TestCase):
    def test_every_recent_card_window_shorter_than_keep(self):
        # Trimming a card still inside a dedup window would re-alert — every caller's window must be < CARD_KEEP_S.
        found = 0
        for fp in glob.glob(os.path.join(ROOT, "sidereus", "*.py")):
            with open(fp, encoding="utf-8") as f:
                for m in re.finditer(r"(?<!def )_recent_card\(.*,\s*([A-Za-z_][A-Za-z0-9_]*)\)", f.read()):
                    found += 1
                    self.assertLess(getattr(notes, m.group(1)), cards.CARD_KEEP_S, m.group(1))
        self.assertGreater(found, 0)


if __name__ == "__main__":
    unittest.main()
