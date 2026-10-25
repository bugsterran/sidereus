"""Incremental read of sidereus/failures_scan._fail_read: no line lost or double-counted across reads."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from tests import _clock
from tests._load import sidereus

S = sidereus("failures_scan")
_FROZEN = _clock.frozen(S)


def setUpModule():
    _FROZEN.__enter__()


def tearDownModule():
    _FROZEN.__exit__(None, None, None)


def _line(i):
    body = ("<task-notification><tool-use-id>toolu_%d</tool-use-id><status>failed</status>"
            "<summary>boom %d</summary></task-notification>" % (i, i))
    return json.dumps({"type": "user", "timestamp": datetime.fromtimestamp(_clock.NOW, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                       "cwd": "/w/repo", "message": {"role": "user", "content": body}}) + "\n"


class IncrementalReadTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.fp = os.path.join(self.d.name, "s.jsonl")
        self._ev, self._off = S._FAIL_EV, S._FAIL_OFF
        S._FAIL_EV, S._FAIL_OFF = {}, {}

    def tearDown(self):
        S._FAIL_EV, S._FAIL_OFF = self._ev, self._off
        self.d.cleanup()

    def _append(self, s):
        with open(self.fp, "a", encoding="utf-8") as f:
            f.write(s)

    def test_appends_counted(self):
        n = 0
        for add, want in ((1, 1), (1, 2), (2, 4)):
            for _ in range(add):
                n += 1
                self._append(_line(n))
            self.assertEqual(len(S._fail_read(self.fp)), want)

    def test_line_split_across_reads_counted_once(self):
        self._append(_line(1))
        ln = _line(2)
        self._append(ln[:40])
        self.assertEqual(len(S._fail_read(self.fp)), 1)
        self._append(ln[40:])
        self.assertEqual(len(S._fail_read(self.fp)), 2)
        self.assertEqual(len(S._fail_read(self.fp)), 2)

    def test_mid_line_offset_drops_partial(self):
        self._append(_line(1) + _line(2))
        S._FAIL_OFF[self.fp] = 10          # mid-line: the first (partial) line must be skipped
        self.assertEqual(len(S._fail_read(self.fp)), 1)

    def test_prune_drops_missing_files(self):
        S._FAIL_EV["/nope/x.jsonl"] = [{}]
        S._FAIL_OFF["/nope/x.jsonl"] = 5
        self._append(_line(1))
        S._fail_read(self.fp)
        saved = S._FAIL_PRUNED[0]
        try:
            S._FAIL_PRUNED[0] = 0.0
            S._fail_prune(_clock.NOW)
        finally:
            S._FAIL_PRUNED[0] = saved
        self.assertNotIn("/nope/x.jsonl", S._FAIL_EV)
        self.assertNotIn("/nope/x.jsonl", S._FAIL_OFF)
        self.assertIn(self.fp, S._FAIL_EV)


def _ts():
    return datetime.fromtimestamp(_clock.NOW, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _j(o):
    return json.dumps(o, separators=(",", ":")) + "\n"


def _fixture():
    """Tool names, tool errors, a hook block, a notification, a non-JSON line and a line longer than the chunk."""
    out = []
    for i in range(30):
        tid = "toolu_%04d" % i
        out.append(_j({"type": "assistant", "timestamp": _ts(), "cwd": "/w/r", "message": {"content": [
            {"type": "tool_use", "id": tid, "name": "Bash%d" % (i % 3), "input": {}}]}}))
        txt = "blocked by hook x" if i % 7 == 0 else "Exit code %d /a/b/c" % i
        out.append(_j({"type": "user", "timestamp": _ts(), "cwd": "/w/r", "message": {"content": [
            {"type": "tool_result", "tool_use_id": tid, "is_error": True, "content": txt}]}}))
        if i % 10 == 3:
            out.append("not json <status>failed</status>\n")
            out.append(_j({"type": "user", "timestamp": _ts(), "cwd": "/w/r", "pad": "z" * 3000}))
        if i % 10 == 5:
            out.append(_line(i))
    return "".join(out)


def _ref_read(data, off=0):
    """Pre-change per-line reference: split every line, filter by marker, parse hits in file order."""
    names, got = {}, []
    lines = data[off:].split(b"\n")
    lines.pop()
    if off > 0 and data[off - 1:off] != b"\n":
        lines.pop(0)
    for raw in lines:
        if not raw.startswith(b"{"):
            continue
        for a, b in S._TU_NAME_RE.findall(raw):
            names[a.decode()] = b.decode()
        if any(k in raw for k in S._FAIL_MARK_B):
            got.extend(S._fail_line(raw.decode("utf-8", "replace"), names))
    return got


class ChunkedScanTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.fp = os.path.join(self.d.name, "s.jsonl")
        self._saved = (S._FAIL_EV, S._FAIL_OFF, S._FAIL_TNAME, S.FAIL_CHUNK)

    def tearDown(self):
        S._FAIL_EV, S._FAIL_OFF, S._FAIL_TNAME, S.FAIL_CHUNK = self._saved
        self.d.cleanup()

    def test_same_events_for_any_chunk_size(self):
        data = _fixture().encode()
        with open(self.fp, "wb") as f:
            f.write(data)
        for off in (0, 1, 500):
            want = _ref_read(data, off)
            self.assertTrue(any(e["kind"] == "tool" and e["tool"] for e in want))
            for chunk in (7, 64, 1000, 4096, 10 ** 6):
                S._FAIL_EV, S._FAIL_OFF, S._FAIL_TNAME, S.FAIL_CHUNK = {}, {self.fp: off} if off else {}, {}, chunk
                self.assertEqual(S._fail_read(self.fp), want, (off, chunk))
                self.assertEqual(S._FAIL_OFF[self.fp], data.rfind(b"\n") + 1)

    def test_peak_bounded_by_chunk(self):
        # ★The 8 MB chunk + line split peaked at 33.6 MB on 239 MB of transcripts; the read must stay near one chunk.
        import tracemalloc
        with open(self.fp, "w", encoding="utf-8") as f:
            f.write(_j({"type": "user", "timestamp": _ts(), "pad": "q" * 200}) * 30000)
        S._FAIL_EV, S._FAIL_OFF, S._FAIL_TNAME = {}, {}, {}
        tracemalloc.start()
        try:
            S._fail_read(self.fp)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 4 * S.FAIL_CHUNK)


if __name__ == "__main__":
    unittest.main()
