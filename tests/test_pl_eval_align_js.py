"""«Evaluation» panel anchor (48i plEvalAlign): right-aligned only when it fits, else left-aligned under the button."""
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def _align(right, w):
    code = js_fn("plEvalAlign") + "\nprocess.stdout.write(plEvalAlign({right: %d}, %d));" % (right, w)
    r = subprocess.run(node_e(code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    return r.stdout.decode()


class PlEvalAlign(unittest.TestCase):
    def test_button_near_left_edge_aligns_left(self):
        # measured: button right edge 242, panel 451 wide -> right align would start at -209 and clamp to 8
        self.assertEqual(_align(242, 451), "left")

    def test_room_on_the_left_keeps_right_align(self):
        self.assertEqual(_align(900, 451), "right")
        self.assertEqual(_align(459, 451), "right")


if __name__ == "__main__":
    unittest.main()
