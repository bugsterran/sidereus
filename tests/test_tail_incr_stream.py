"""_tail_incr streams line by line; results must match the old whole-block decode+split."""
import os
import shutil
import tempfile
import unittest

from tests._load import load

load()
from sidereus.transcript import _tail_incr


def _old(fp, nb, prev):
    """The pre-streaming implementation, kept as the reference."""
    try:
        size = os.path.getsize(fp)
    except OSError:
        return [], None, None, True
    reset = not (prev and prev[1] is not None and size >= prev[1])
    if reset:
        off = size - nb if size > nb else 0
        start = off
    else:
        start, off = prev[0], prev[1]
        if size == off:
            return [], start, off, False
    with open(fp, "rb") as f:
        f.seek(off)
        raw = f.read(size - off)
    if reset and off > 0:
        i = raw.find(b"\n")
        if i < 0:
            return [], size, size, True
        off += i + 1
        start = off
        raw = raw[i + 1:]
    j = raw.rfind(b"\n")
    if j < 0:
        return [], start, off, reset
    txt = raw[:j].decode("utf-8", "replace")
    return ([l for l in txt.split("\n") if l.strip().startswith("{")],
            start, off + j + 1, reset)


class TailIncrStream(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="ti_")
        self.fp = os.path.join(self.d, "t.jsonl")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _w(self, data, mode="wb"):
        with open(self.fp, mode) as f:
            f.write(data)

    def _both(self, nb, prev):
        new = _tail_incr(self.fp, nb, prev)
        self.assertEqual(new, _old(self.fp, nb, prev))
        return new

    def test_partial_last_line(self):
        self._w(b'{"a":1}\n{"b":2}\n{"c":')
        lines, s, e, rs = self._both(1000, None)
        self.assertEqual(lines, ['{"a":1}', '{"b":2}'])
        self.assertEqual((s, e, rs), (0, 16, True))
        self._w(b'{"only-partial"')
        self.assertEqual(self._both(1000, None), ([], 0, 0, True))

    def test_append(self):
        self._w(b'noise\n{"a":1}\n{"b":')
        r1 = self._both(1000, None)
        self._w(b'2}\n  {"c":3}\nplain\n', "ab")
        r2 = self._both(1000, (r1[1], r1[2]))
        self.assertEqual(r2[0], ['{"b":2}', '  {"c":3}'])
        self.assertFalse(r2[3])
        self.assertEqual(self._both(1000, (r2[1], r2[2])), ([], r2[1], r2[2], False))

    def test_truncated_window_drops_first_line(self):
        self._w(b'{"x":"' + b"y" * 50 + b'"}\n{"a":1}\n{"b":2}\n')
        for nb in (1, 10, 30, 70, 10 ** 6):
            self._both(nb, None)
        self.assertEqual(self._both(10, None)[0], ['{"b":2}'])

    def test_shrink_or_rotate(self):
        self._w(b'{"a":1}\n{"b":2}\n{"c":3}\n')
        r1 = self._both(1000, None)
        self._w(b'{"z":9}\n')                  # rewritten smaller
        r2 = self._both(1000, (r1[1], r1[2]))
        self.assertEqual(r2, (['{"z":9}'], 0, 8, True))
        os.remove(self.fp)
        self.assertEqual(self._both(1000, (r2[1], r2[2])), ([], None, None, True))

    def test_invalid_utf8(self):
        self._w(b'{"a":"\xff\xfe"}\n{"b":"\xe2\x82"}\n{"c":"\xf0\x9f\x98\x80"}\n\xe2\x82\n'
                b'\xc2\xa0{"nbsp":1}\n\x1c{"fs":1}\n{"d":"\xe2\x82\n')
        lines = self._both(10 ** 6, None)[0]
        self.assertEqual(lines[0], '{"a":"��"}')
        self.assertEqual(lines[1], '{"b":"�"}')
        self.assertEqual(lines[2], '{"c":"\U0001F600"}')
        self.assertIn('\xa0{"nbsp":1}', lines)       # str.strip() drops non-ASCII whitespace
        self.assertIn('\x1c{"fs":1}', lines)
        self.assertEqual(lines[-1], '{"d":"�')


if __name__ == "__main__":
    unittest.main()
