"""Second silent-except pass: faults that used to vanish now warn_once(soft); expected misses stay quiet.

No live files: temp dirs only, and every dependency is monkeypatched on the module that reads it.
"""
import os
import shutil
import tempfile
import unittest

from tests import _load

ag = _load.sidereus("agents")
fl = _load.sidereus("failures")
qu = _load.sidereus("quota")
bus = _load.sidereus("bus")
ts = _load.sidereus("timeline_scan")
ss = _load.sidereus("structure_cache")
tr = _load.sidereus("transcript")


class _Patch(object):
    """Swap module attributes and capture warn_once calls as (key, soft)."""

    def __init__(self, mod, **attrs):
        self.mod, self.attrs, self.saved, self.got = mod, attrs, {}, []

    def __enter__(self):
        self.attrs["warn_once"] = lambda key, msg, soft=False, en=None, log=True, **kw: self.got.append((key, soft))
        for k, v in self.attrs.items():
            self.saved[k] = getattr(self.mod, k)
            setattr(self.mod, k, v)
        return self.got

    def __exit__(self, *a):
        for k, v in self.saved.items():
            setattr(self.mod, k, v)


def _boom(*a, **k):
    raise TypeError("bug")


class FaultsWarn(unittest.TestCase):
    def test_agent_ended(self):
        with _Patch(ag, _tail_lines=_boom) as got:
            self.assertFalse(ag._agent_ended("/x/agent-a.jsonl"))
        self.assertEqual(got, [("ag-ended", True)])

    def test_fail_cards(self):
        with _Patch(fl, _fail_events=_boom) as got:
            self.assertIsNone(fl._fail_cards())
        self.assertEqual(got, [("fail-cards", True)])

    def test_timeline_segments(self):
        with _Patch(ts, _tail_incr=_boom) as got:
            self.assertEqual(ts._seg_scan("/x/s.jsonl", 0, 1000, 10), ([], None, []))
        self.assertEqual(got, [("tl-segs", True)])

    def test_ack_map(self):
        with _Patch(bus, _cached=_boom) as got:
            self.assertEqual(bus.ack_map(), {})
        self.assertEqual(got, [("ack-map", True)])

    def test_quota_log_oserror_now_warns(self):
        def no_disk(path):
            raise OSError("disk full")
        saved = qu._qlog_last[0]
        qu._qlog_last[0] = None
        try:
            with _Patch(qu, _open_append=no_disk, _cc_account=lambda: None) as got:
                qu._quota_log({"five_hour": {"pct": 1}}, 1, "t")
        finally:
            qu._qlog_last[0] = saved
        self.assertEqual(got, [("qlog", True)])


class ExpectedStayQuiet(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_bus_load_missing(self):
        with _Patch(bus, DATA_DIR=self.d) as got:
            self.assertEqual(bus._load("nope.json", {"k": 1}), {"k": 1})
        self.assertEqual(got, [])

    def test_struct_disk_read_corrupt(self):
        p = os.path.join(self.d, "x.json.gz")
        with open(p, "wb") as f:
            f.write(b"\x1f\x8b\x08\x00garbage")
        with _Patch(ss, _struct_disk_file=lambda kind, key: p) as got:
            self.assertIsNone(ss._struct_disk_read("k", "key"))
        self.assertEqual(got, [])

    def test_timestamps_fall_back(self):
        self.assertEqual(tr.iso_epoch("not a time", 7.0), 7.0)
        self.assertEqual(tr._line_ts({"timestamp": 12345}, 3.0), 3.0)

    def test_narrowed_does_not_hide_bugs(self):
        with _Patch(bus, json=None):
            open(os.path.join(self.d, "a.json"), "w", encoding="utf-8").close()
            with _Patch(bus, DATA_DIR=self.d):
                self.assertRaises(AttributeError, bus._load, "a.json", {})


if __name__ == "__main__":
    unittest.main()
