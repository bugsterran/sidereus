"""Status-bar layer errored account rows (60b) and «Quota details» modal focus (60-statusbar.js)."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import i18n, jconst
from tests.test_sbar_layer import FNS, N, STUBS, read
from tests._node import node_e

# Account 'bad' failed its last fetch: the server still sends the previous pct next to err.
QUOTA = """
const N = %s;
QLAST = {q: {five_hour: {pct: 38}, seven_day: {pct: 33},
             accounts: [{label: 'bad', err: 'http 500', five_hour: {pct: 22, resets_at: (N + 36e5) / 1000}, seven_day: {pct: 61}},
                        {label: 'ok', five_hour: {pct: 10}, seven_day: {pct: 20}}]}};
ACCTS = [{label: 'me', primary: true}, {label: 'bad'}, {label: 'ok'}];
""" % N


def run_js(body, fns=FNS, pre=STUBS):
    src = pre + i18n() + "\n" + jconst("esc") + "\n" + "\n".join(js_fn(f) for f in fns) + "\n" + body
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"))
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SbarErrRow(unittest.TestCase):
    def test_err_row_no_stale_pct(self):
        rows = run_js(QUOTA + "process.stdout.write(JSON.stringify(sblAccRows(QLAST.q, acctList(), mainAcct())));")
        bad = [r for r in rows if r["label"] == "bad"][0]
        self.assertTrue(bad["err"])
        self.assertEqual((bad["l5"], bad["l7"], bad["u5"], bad["u7"], bad["rs5"]), ("—", "—", None, None, ""))
        ok = [r for r in rows if r["label"] == "ok"][0]
        self.assertFalse(ok["err"])
        self.assertEqual((ok["l5"], ok["l7"]), ("90%", "80%"))

    def test_err_row_marked_and_not_switchable(self):
        h = run_js(QUOTA + "process.stdout.write(JSON.stringify(sblHtml(N)));")
        row = [r for r in h.split('<div class="sbl-acc') if ">bad" in r][0]
        self.assertIn("sbl-err", row)
        self.assertIn("실패", row)
        self.assertNotIn("78%", row)
        self.assertNotIn("39%", row)
        self.assertNotIn("data-acct", row)
        self.assertNotIn("sbl-hint", row)
        self.assertIn('data-acct="ok"', h)             # the healthy account stays switchable


FOCUS = """
var document = {body: {id: 'body'}, getElementById: () => null};
const D = {kids: ['x1', 'x2'], contains(n){ return this.kids.includes(n); }};
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SdrwFocus(unittest.TestCase):
    def test_focus_target(self):
        r = run_js("process.stdout.write(JSON.stringify(["
                   "sdrwFocusTarget(false, true, D, 'opener'),"   # open from the hidden layer button -> into the modal
                   "sdrwFocusTarget(true, true, D, 'x1'),"         # already open, focus inside -> leave
                   "sdrwFocusTarget(true, false, D, 'x1'),"        # close (Esc / ✕) -> back to the bar
                   "sdrwFocusTarget(true, false, D, document.body),"
                   "sdrwFocusTarget(false, false, D, 'railtg')]));",  # init while closed -> leave
                   fns=("sdrwFocusTarget",), pre=FOCUS)
        self.assertEqual(r, ["in", "", "bar", "bar", ""])

    def test_tab_wraps(self):
        r = run_js("const L = ['a', 'b', 'c'];"
                   "process.stdout.write(JSON.stringify([sdrwTabTarget(L, 'c', false), sdrwTabTarget(L, 'a', true),"
                   "sdrwTabTarget(L, 'b', false), sdrwTabTarget(L, 'railtg', false), sdrwTabTarget(L, 'railtg', true),"
                   "sdrwTabTarget([], 'a', false)]));", fns=("sdrwTabTarget",), pre=FOCUS)
        self.assertEqual(r, ["a", "c", None, "a", "c", None])


class SdrwDialogMarkup(unittest.TestCase):
    def test_dialog_role_on_sdrw(self):
        html, sb = read("web/index.html"), read("web/js/60-statusbar.js")
        self.assertIn("<div class=sdrw id=sdrw role=dialog aria-modal=true aria-labelledby=sdrwt>", html)
        self.assertIn("<b id=sdrwt>", sb)
        self.assertIn("sdrwTabTarget(sdrwFocusables(dr)", sb)


if __name__ == "__main__":
    unittest.main()
