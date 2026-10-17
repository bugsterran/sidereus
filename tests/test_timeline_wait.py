"""Session row `wt` = [human prompts that came ≥ WAIT_MIN_S after the previous line, seconds] from line metadata only:
tool results, isMeta lines and short gaps are ignored, the cache carries it across appends, the key is absent at 0."""
import datetime
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

ts = sidereus("timeline_scan")
tl = sidereus("timeline")

T0 = 1_790_000_000          # fixture epoch, never the clock


def _iso(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _ln(kind, t, **x):
    e = {"type": kind, "timestamp": _iso(t)}
    if kind == "user":
        e["message"] = {"role": "user", "content": x.pop("content", "hello")}
    e.update(x)
    return json.dumps(e, separators=(",", ":"))


class TimelineWait(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.fp = os.path.join(self.d, "s.jsonl")
        ts._SEG_RAW.clear(); ts._SEG_WIN.clear()

    def tearDown(self):
        ts._SEG_RAW.clear(); ts._SEG_WIN.clear()
        shutil.rmtree(self.d)

    def _write(self, lines, mode="w"):
        with open(self.fp, mode, encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def _wt(self, cut=T0):
        ts._sess_segments(self.fp, cut)
        return ts._sess_waits(self.fp, cut)

    def test_counts_and_ignores(self):
        self._write([
            _ln("assistant", T0 + 10),
            _ln("user", T0 + 70),                                                    # 60 s wait: counts
            _ln("assistant", T0 + 80),
            _ln("user", T0 + 100),                                                   # 20 s: too short
            _ln("user", T0 + 200, content=[{"type": "tool_result", "content": "x"}]),   # tool result
            _ln("user", T0 + 300, isMeta=True),                                      # meta line
            _ln("queue-operation", T0 + 340),
            _ln("user", T0 + 350),                                                   # 10 s after the queue line
            _ln("assistant", T0 + 360),
            _ln("user", T0 + 400),                                                   # 40 s: counts
        ])
        self.assertEqual(self._wt(), [60, 40])

    def test_wait_clipped_to_cut(self):
        self._write([_ln("assistant", T0), _ln("user", T0 + 500)])
        self.assertEqual(self._wt(cut=T0 + 400), [100])

    def test_append_uses_cached_last_line(self):
        self._write([_ln("assistant", T0), _ln("user", T0 + 5)])
        self.assertEqual(self._wt(), [])
        self._write([_ln("user", T0 + 95)], mode="a")                                # previous line read last time
        self.assertEqual(self._wt(), [90])

    def test_row_key_absent_at_zero(self):
        orig = tl.clear_of
        tl.clear_of = lambda sid: []
        try:
            self._write([_ln("assistant", T0), _ln("user", T0 + 5)])
            os.utime(self.fp, (T0 + 5, T0 + 5))
            row = tl._tl_sess_row(self.fp, "sid1", None, T0, "/w/a", "a")
            self.assertNotIn("wt", row)
            self._write([_ln("assistant", T0), _ln("user", T0 + 45), _ln("assistant", T0 + 50), _ln("user", T0 + 90)])
            os.utime(self.fp, (T0 + 90, T0 + 90))
            ts._SEG_RAW.clear(); ts._SEG_WIN.clear()
            row = tl._tl_sess_row(self.fp, "sid1", None, T0, "/w/a", "a")
            self.assertEqual(row["wt"], [2, 85])
        finally:
            tl.clear_of = orig


if __name__ == "__main__":
    unittest.main()
