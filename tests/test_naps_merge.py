"""Summary joins sleep bands split by DarkWake blips (2026-09-25): bands closer than joinS are one sleep,
and each real separator counts as one auto-wake."""
import json
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def join(naps, join_s=60):
    src = js_fn("tlNapJoin") + "\nconsole.log(JSON.stringify(tlNapJoin(" + json.dumps(naps) + ", " + str(join_s) + ")));"
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


class NapJoin(unittest.TestCase):
    def test_darkwake_blips_join(self):
        # shape of the live 17:29~20:26 case: 1-5 s separators
        b = [[1000, 3065], [3066, 4654], [4659, 6655], [6656, 8314], [8318, 11626]]
        self.assertEqual(join(b), [[1000, 11626, 4]])

    def test_real_wake_splits(self):
        self.assertEqual(join([[0, 100], [140, 200], [800, 900]]), [[0, 200, 1], [800, 900, 0]])

    def test_boundary_is_exclusive(self):
        self.assertEqual(join([[0, 100], [160, 200]]), [[0, 100, 0], [160, 200, 0]])
        self.assertEqual(join([[0, 100], [159, 200]]), [[0, 200, 1]])

    def test_unsorted_overlap_and_empty(self):
        self.assertEqual(join([[50, 80], [0, 60], [90, 90]]), [[0, 80, 0]])
        self.assertEqual(join([]), [])
        self.assertEqual(join(None), [])


if __name__ == "__main__":
    unittest.main()
