"""Popover Tab-out (web/js/08 popTabOut): Tab past the last control (Shift+Tab before the first, or from the container)
closes the open popover with focus back to its opener; Tab between inner controls and closed popovers are left alone."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PopTabOut(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = js_fn("popTabOut") + r"""
const el = () => ({ offsetParent: {} });
const b1 = el(), b2 = el(), hid = { offsetParent: null }, out = el();
const mkPop = kids => ({ hidden: false, kids, contains(x){ return x === this || this.kids.includes(x); },
                         querySelectorAll(){ return this.kids; } });
const P = { full: mkPop([b1, hid, b2]), empty: mkPop([]) };
const document = { activeElement: null, getElementById: id => P[id] || null };
let closed = [];
const UIPOPS = [{ id: 'full', close: f => closed.push(['full', f]) }, { id: 'empty', close: f => closed.push(['empty', f]) }];
const run = (act, key, shift, hide) => {
  closed = []; let prevented = false;
  P.full.hidden = !!hide; document.activeElement = act;
  popTabOut({ key, shiftKey: !!shift, preventDefault(){ prevented = true; } });
  return { closed, prevented };
};
const R = {
  lastTab: run(b2, 'Tab'), midTab: run(b1, 'Tab'), firstShift: run(b1, 'Tab', 1), lastShift: run(b2, 'Tab', 1),
  boxTab: run(P.full, 'Tab'), boxShift: run(P.full, 'Tab', 1), emptyBox: run(P.empty, 'Tab'),
  outside: run(out, 'Tab'), hiddenPop: run(b2, 'Tab', 0, 1), notTab: run(b2, 'Enter'),
};
process.stdout.write(JSON.stringify(R));
"""
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        cls.R = json.loads(r.stdout)

    def test_edges_close_with_focus_back(self):
        for k in ("lastTab", "firstShift", "boxShift"):
            self.assertEqual(self.R[k], {"closed": [["full", True]], "prevented": True}, k)
        self.assertEqual(self.R["emptyBox"]["closed"], [["empty", True]])   # nothing focusable inside

    def test_inner_moves_left_alone(self):
        for k in ("midTab", "lastShift", "boxTab", "outside", "hiddenPop", "notTab"):
            self.assertEqual(self.R[k], {"closed": [], "prevented": False}, k)


if __name__ == "__main__":
    unittest.main()
