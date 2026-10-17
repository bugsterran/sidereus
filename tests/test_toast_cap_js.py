"""Toast stack cap: toast() (web/js/15-alarms.js) keeps at most TOAST_MAX toasts, dropping the oldest. Fake DOM, timers never fire."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e


def run(n):
    """Returns the project names of the toasts left after n toast() calls."""
    src = ("const box = {kids: [], get children(){ return this.kids; }, get firstElementChild(){ return this.kids[0]; },"
           " appendChild(e){ e.parent = this; this.kids.push(e); }};\n"
           "function mk(){ return {classList: {add(){}}, remove(){ const k = this.parent.kids; const i = k.indexOf(this);"
           " if (i >= 0) k.splice(i, 1); }}; }\n"
           "const document = {getElementById: () => box, createElement: mk};\n"
           "const setTimeout = () => 0, clearTimeout = () => {};\n"
           "const cardHTML = c => c.project, FA_ACTS = {};\n"
           + js_fn("toast") + "\n"
           "for (let i = 0; i < " + str(n) + "; i++) toast({kind: 'ask', project: 'p' + i});\n"
           "process.stdout.write(JSON.stringify(box.kids.map(e => e.innerHTML)));")
    src = "const TOAST_MS = 10000, TOAST_LEAVE_MS = 3000, TOAST_MAX = " + str(MAX) + ";\n" + src
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


MAX = 5


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ToastCap(unittest.TestCase):
    def test_constant_is_five(self):
        self.assertIn("TOAST_MAX = 5", js_all())

    def test_under_cap_keeps_all(self):
        self.assertEqual(run(3), ["p0", "p1", "p2"])

    def test_burst_keeps_newest_five(self):
        self.assertEqual(run(13), ["p8", "p9", "p10", "p11", "p12"])


if __name__ == "__main__":
    unittest.main()
