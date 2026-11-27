"""parse.pmode_spans (R2, R3): permission-mode spans of a transcript's prompt lines — merged, incremental, capped.
Temp files only; no live transcripts, clock or network."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

P = sidereus("parse")


def u(ts, mode, **kw):
    d = {"type": "user", "timestamp": ts, "permissionMode": mode, "message": {"role": "user", "content": "secret body"}}
    d.update(kw)
    return json.dumps(d) + "\n"


def ts(s):
    return P._line_ts({"timestamp": s}, 0)


class Spans(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.fp = os.path.join(self.d, "s.jsonl")
        self.saved = (dict(P._PMODE_SPANS), P._PMODE_SCAN, P._PMODE_CHUNK)
        P._PMODE_SPANS.clear()
        self.reads = []

    def tearDown(self):
        P._PMODE_SPANS.clear()
        P._PMODE_SPANS.update(self.saved[0])
        P._PMODE_SCAN, P._PMODE_CHUNK = self.saved[1], self.saved[2]
        P.__dict__.pop("open", None)
        shutil.rmtree(self.d)

    def write(self, s, mode="w"):
        # newline="": Windows text mode writes CRLF, so the appended byte count would be one more per line
        with open(self.fp, mode, encoding="utf-8", newline="") as f:
            f.write(s)

    def count_reads(self):
        real = open

        class F(object):
            def __init__(s, f):
                s.f = f

            def __enter__(s):
                return s

            def __exit__(s, *a):
                s.f.close()

            def seek(s, *a):
                return s.f.seek(*a)

            def read(s, n=-1):
                b = s.f.read(n)
                self.reads.append(len(b))
                return b
        P.open = lambda *a, **k: F(real(*a, **k))

    def test_merge_equal_and_new_span_on_change(self):
        self.write(u("2026-11-01T00:00:00Z", "default") + u("2026-11-01T00:01:00Z", "bypassPermissions")
                   + u("2026-11-01T00:02:00Z", "bypassPermissions") + u("2026-11-01T00:03:00Z", "default"))
        got = P.pmode_spans(self.fp)
        self.assertEqual([s[0] for s in got], ["default", "bypassPermissions", "default"])
        self.assertEqual(got[1][1:], [ts("2026-11-01T00:01:00Z"), ts("2026-11-01T00:02:00Z")])
        self.assertNotIn("secret", json.dumps(got))   # R3: mode and times only

    def test_appended_bytes_only_and_unchanged_size_no_read(self):
        a = u("2026-11-01T00:00:00Z", "auto")
        self.write(a)
        self.count_reads()
        self.assertEqual(P.pmode_spans(self.fp)[0][0], "auto")
        self.reads[:] = []
        self.assertEqual(P.pmode_spans(self.fp)[0][0], "auto")
        self.assertEqual(self.reads, [])              # stat only
        b = u("2026-11-01T00:05:00Z", "dontAsk")
        self.write(b, "a")
        got = P.pmode_spans(self.fp)
        self.assertEqual([s[0] for s in got], ["auto", "dontAsk"])
        self.assertEqual(sum(self.reads), len(b.encode()))

    def test_truncation_resets(self):
        self.write(u("2026-11-01T00:00:00Z", "auto") + u("2026-11-01T00:01:00Z", "auto"))
        P.pmode_spans(self.fp)
        self.write(u("2026-11-01T01:00:00Z", "default"))
        self.assertEqual([s[0] for s in P.pmode_spans(self.fp)], ["default"])

    def test_trailing_partial_line_waits(self):
        line = u("2026-11-01T00:00:00Z", "bypassPermissions")
        self.write(line[:-1])                         # no newline yet: still being written
        self.assertEqual(P.pmode_spans(self.fp), [])
        self.write("\n", "a")
        self.assertEqual([s[0] for s in P.pmode_spans(self.fp)], ["bypassPermissions"])

    def test_bad_lines_give_nothing(self):
        self.write('{"type":"user","permissionMode":"auto", broken\n'
                   + json.dumps({"type": "assistant", "timestamp": "2026-11-01T00:00:00Z", "permissionMode": "auto"}) + "\n"
                   + json.dumps({"type": "user", "timestamp": "2026-11-01T00:00:00Z"}) + "\n"
                   + u("2026-11-01T00:00:00Z", "auto mode") + u("2026-11-01T00:00:00Z", "a" * 33)
                   + json.dumps({"type": "user", "permissionMode": "auto"}) + "\n")
        self.assertEqual(P.pmode_spans(self.fp), [])

    def test_missing_file_unknown(self):
        self.assertEqual(P.pmode_spans(os.path.join(self.d, "none.jsonl")), [])

    def test_cap_drops_oldest(self):
        n = P._PMODE_SPAN_CAP + 6
        self.write("".join(u("2026-11-01T00:%02d:%02dZ" % (i // 60, i % 60), "auto" if i % 2 else "default") for i in range(n)))
        got = P.pmode_spans(self.fp)
        self.assertEqual(len(got), P._PMODE_SPAN_CAP)
        self.assertEqual(got[-1][1], ts("2026-11-01T00:01:09Z"))
        self.assertEqual(got[0][1], ts("2026-11-01T00:00:06Z"))

    def test_scan_window_drops_cut_first_line_and_chunks(self):
        old = u("2026-11-01T00:00:00Z", "auto")
        new = u("2026-11-01T00:01:00Z", "dontAsk") + u("2026-11-01T00:02:00Z", "default")
        self.write(old + new)
        P._PMODE_SCAN = len(new) + 5                  # window starts 5 bytes before the end of `old`
        P._PMODE_CHUNK = 17                           # lines span chunk borders
        self.assertEqual([s[0] for s in P.pmode_spans(self.fp)], ["dontAsk", "default"])


if __name__ == "__main__":
    unittest.main()


class SpansGap(unittest.TestCase):
    """Growth beyond _PMODE_SCAN between two calls leaves an unread gap: the old spans must not bridge it (R2)."""
    setUp, tearDown, write = Spans.setUp, Spans.tearDown, Spans.write

    def test_gap_past_reach_drops_old_spans(self):
        self.write(u("2026-11-25T01:00:00Z", "bypassPermissions"))
        self.assertEqual([s[0] for s in P.pmode_spans(self.fp)], ["bypassPermissions"])
        gap = u("2026-11-25T02:00:00Z", "default")
        tail = u("2026-11-25T03:00:00Z", "bypassPermissions")
        P._PMODE_SCAN = len(tail) + 10              # the «default» line falls outside the reach
        self.write(gap + tail, "a")
        sp = P.pmode_spans(self.fp)
        self.assertEqual([(s[0], s[1]) for s in sp], [("bypassPermissions", ts("2026-11-25T03:00:00Z"))])
