"""URL hash <-> main tab (web/js/92 mvHashKey/mvHashOf/mvHashSync, 05-i18n mainView boot order)."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

TABS = ["pipe", "struct", "time", "chat", "br", "token", "hist", "retro"]


def run(body):
    js = js_fn("mvHashKey") + "\n" + js_fn("mvHashOf") + "\n" + body
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def boot(hash_, own=None, ui=None, popup=False):
    """Evaluate the 05-i18n mainView IIFE against a stubbed location/storage."""
    iife = re.search(r"^let mainView = \(\(\) => \{.*?\}\)\(\);", js_all(), re.S | re.M).group(0)
    body = ("const location = {hash: %s}, UIS = %s, OWN = %s;\n" % (json.dumps(hash_), json.dumps(ui or {}), json.dumps(own or {}))
            + "const ISPOP = %s, ISWP = false, ISBP = false;\n" % ("true" if popup else "false")
            + "function tabOwn(k){ return Object.prototype.hasOwnProperty.call(OWN, k) ? OWN[k] : null; }\n"
            + iife + "\nprocess.stdout.write(JSON.stringify(mainView));")
    return run(body)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class MainViewHash(unittest.TestCase):
    def test_round_trip_every_tab(self):
        out = run("process.stdout.write(JSON.stringify(%s.map(k => [mvHashKey('#' + mvHashOf(k)), mvHashKey(k)])));"
                  % json.dumps(TABS))
        self.assertEqual(out, [[k, k] for k in TABS])

    def test_unknown_or_empty_is_null(self):
        out = run("process.stdout.write(JSON.stringify(['', '#', '#x', '#svccgo', null].map(mvHashKey)));")
        self.assertEqual(out, [None] * 5)
        self.assertEqual(run("process.stdout.write(JSON.stringify(mvHashOf('work')));"), "")

    def test_hash_beats_tab_memory(self):
        self.assertEqual(boot("#structure", own={"mbMainView": "chat"}, ui={"mbMainView": "time"}), "struct")

    def test_no_hash_keeps_order(self):
        self.assertEqual(boot("", own={"mbMainView": "chat"}, ui={"mbStartView": "time"}), "chat")
        self.assertEqual(boot("", ui={"mbStartView": "br", "mbMainView": "time"}), "br")
        self.assertEqual(boot("", ui={"mbMainView": "hist"}), "hist")
        self.assertEqual(boot("#nope"), "pipe")

    def test_feature_off_tab_refused_from_hash(self):
        self.assertEqual(boot("#insights", own={"mbMainView": "chat"}, ui={"mbTabsOff": '["retro"]'}), "chat")

    def test_popup_ignores_hash(self):
        self.assertEqual(boot("#structure", own={"mbMainView": "chat"}, popup=True), "chat")

    def test_sync_uses_replace_state_and_skips_popups(self):
        tpl = ("let mainView = 'br'; const ISPOP = %s, ISWP = false, ISBP = false, calls = [];\n"
               "const location = {pathname: '/', search: '?a=1', hash: '#timeline'};\n"
               "const history = {state: null, replaceState: (s, t, u) => calls.push(u)};\n"
               "function softErr(){}\n" + js_fn("mvHashSync")
               + "\nmvHashSync(); location.hash = '#branches'; mvHashSync(); process.stdout.write(JSON.stringify(calls));")
        self.assertEqual(run(tpl % "false"), ["/?a=1#branches"])
        self.assertEqual(run(tpl % "true"), [])


if __name__ == "__main__":
    unittest.main()
