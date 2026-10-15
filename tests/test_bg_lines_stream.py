"""_bg_lines streams line by line; results must match the old whole-buffer decode+splitlines."""
import os
import tempfile
import unittest

from tests._load import load

load()
import sidereus.bgtasks as bg


def _done(data, start):
    """Offset after a read from `start`: past the last complete line (a trailing partial line is held back)."""
    return max(start, data.rfind(b"\n") + 1)


def _old(fp, start, end=None):
    """The pre-streaming implementation of the read/filter step, kept as the reference (up to `end`)."""
    with open(fp, "rb") as f:
        f.seek(start)
        raw = f.read() if end is None else f.read(max(0, end - start))
    lines = raw.decode("utf-8", "replace").splitlines()
    if start > 0 and lines and not lines[0].lstrip().startswith("{"):
        lines = lines[1:]
    return [l for l in lines if l.lstrip().startswith("{")]


class BgLinesStream(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="sidereus-bgl-")
        self._off = dict(bg._bg_offset)
        bg._bg_offset.clear()

    def tearDown(self):
        bg._bg_offset.clear()
        bg._bg_offset.update(self._off)

    def _file(self, data):
        fp = os.path.join(self.d, "t.jsonl")
        with open(fp, "wb") as f:
            f.write(data)
        return fp

    def _check(self, data, start):
        fp = self._file(data)
        bg._bg_offset[fp] = start
        got = bg._bg_lines(fp)
        end = _done(data, start)
        self.assertEqual(got, _old(fp, start, end))
        self.assertEqual(bg._bg_offset[fp], end)
        return got

    def test_partial_line_across_two_reads(self):
        # A JSON line written in two halves is parsed exactly once, whole, on the read that completes it.
        fp = self._file(b'{"a":1}\n{"type":"user","msg":"do')
        bg._bg_offset[fp] = 0
        self.assertEqual(bg._bg_lines(fp), ['{"a":1}'])
        self.assertEqual(bg._bg_offset[fp], 8)
        with open(fp, "ab") as f:
            f.write(b'ne"}\n')
        self.assertEqual(bg._bg_lines(fp), ['{"type":"user","msg":"done"}'])
        self.assertEqual(bg._bg_lines(fp), [])

    def test_window_mid_line(self):
        data = b'{"a":1}\n{"b":"xyz"}\n  {"c":3}\nplain\n{"d":4}'
        for start in range(len(data) + 1):
            self._check(data, start)
        self.assertEqual(self._check(data, 1), ['{"b":"xyz"}', '  {"c":3}'])   # '{"d":4}' has no "\n" yet
        # a truncated first piece that happens to start with "{" is kept, as before
        self.assertEqual(self._check(b'{"x":{"y":1}}\n{"z":2}\n', 5), ['{"y":1}}', '{"z":2}'])

    def test_invalid_utf8_and_separators(self):
        data = (b'{"k":"\xff\xfe"}\n{"t":"\xe2\x82"}\n{"u":"\xed\xa0\x80"}\r\n'
                b'{"v":1}\r{"w":2}\x0b{"x":3}\xc2\x85{"y":4}\xe2\x80\xa8{"z":5}\n\xc2\xa0{"nb":6}\n\xe2\x82\n')
        for start in range(len(data) + 1):
            self._check(data, start)
        got = self._check(data, 0)
        self.assertIn('{"k":"��"}', got)
        self.assertIn('{"t":"�"}', got)

    def test_empty_file(self):
        self.assertEqual(self._check(b"", 0), [])

    def test_missing_file(self):
        fp = os.path.join(self.d, "nope.jsonl")
        self.assertEqual(bg._bg_lines(fp), [])
        self.assertNotIn(fp, bg._bg_offset)

    def test_first_sight_seed_window(self):
        data = b"".join(b'{"i":%d}\n' % i for i in range(50))
        fp = self._file(data)
        saved = bg.BG_SEED_BYTES
        try:
            bg.BG_SEED_BYTES = 37           # lands mid-line
            got = bg._bg_lines(fp)
        finally:
            bg.BG_SEED_BYTES = saved
        self.assertEqual(got, _old(fp, len(data) - 37))


if __name__ == "__main__":
    unittest.main()
