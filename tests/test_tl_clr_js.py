"""Timeline /clear marks (web/js/74b tlClrMarks): one `.tlclr` per `x.clr` entry, escaped title,
nothing at all when `clr` is missing or empty (keeps the demo screen bytes unchanged)."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TlClrMarks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = js_fn("TV") + "\n" + js_fn("tlClrMarks") + r"""
const T = s => s, tlHh = t => 'H' + t;
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const pct = t => t / 10;
process.stdout.write(JSON.stringify({
  none: tlClrMarks([{}, {clr: []}, {clr: null}], pct),
  two: tlClrMarks([{clr: [{at: 100, old8: 'aaaa1111', new8: 'bbbb2222'}, {at: 'x'}]},
                   {clr: [{at: 250, old8: '<o>', new8: 'n"'}]}], pct),
}));
"""
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        cls.R = json.loads(r.stdout)

    def test_missing_or_empty_renders_nothing(self):
        self.assertEqual(self.R["none"], "")

    def test_one_mark_per_valid_entry(self):
        h = self.R["two"]
        self.assertEqual(h.count("class=tlclr"), 2)
        self.assertIn('left:10.00%', h)
        self.assertIn('left:25.00%', h)
        self.assertIn("H100 Cleared — new session bbbb2222\nPrevious session aaaa1111", h)

    def test_ids_are_escaped(self):
        h = self.R["two"]
        self.assertIn("&lt;o>", h)
        self.assertIn("n&quot;", h)
        self.assertNotIn("<o>", h)


if __name__ == "__main__":
    unittest.main()
