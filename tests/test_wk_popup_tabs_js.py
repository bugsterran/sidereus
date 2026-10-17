"""Work-log routing (35c wkPopup/wkHostOf): an open work popup takes the item as a tab; closed -> new window;
Shift -> own window; a moment (&at=) item and its window stay separate; a failing cross-window call falls back to a window."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def run(body):
    src = ("let POPS = {}, WKHOST = '', WKSHIFT = 0; const WKAT = {}; const R = {opened: [], reopen: [], err: []};\n"
           "function softErr(k){ R.err.push(k); }\n"
           "function fakeWin(name, tabs, bad){ return {name, closed: false, focus(){},\n"
           "  wkReopen(c, t){ if(bad) throw new Error('x'); R.reopen.push(name + ':' + t); tabs.push(t); },\n"
           "  wkHasTab(c, t){ return tabs.includes(t); }}; }\n"
           "function popOpen(url, name){ if(POPS[name]) return POPS[name]; R.opened.push(name);"
           " return POPS[name] = fakeWin(name, [], false); }\n"
           + "\n".join(js_fn(f) for f in ("popName", "wkHostOf", "wkPopup"))
           + "\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class WkPopupTabs(unittest.TestCase):
    def test_closed_opens_window_then_open_adds_tab(self):
        R = run("wkPopup('/p', 'sess:/p'); wkPopup('/p', 'agA');")
        self.assertEqual(R["opened"], ["sidereus_work_sess__p"])
        self.assertEqual(R["reopen"], ["sidereus_work_sess__p:agA"])

    def test_closed_popup_opens_new_window(self):
        R = run("wkPopup('/p', 'sess:/p'); POPS['sidereus_work_sess__p'].closed = true; wkPopup('/p', 'agA');")
        self.assertEqual(R["opened"], ["sidereus_work_sess__p", "sidereus_work_agA"])
        self.assertEqual(R["reopen"], [])

    def test_shift_opens_separate_window(self):
        R = run("wkPopup('/p', 'sess:/p'); WKSHIFT = Date.now(); wkPopup('/p', 'agA');")
        self.assertEqual(R["opened"], ["sidereus_work_sess__p", "sidereus_work_agA"])

    def test_existing_tab_wins_over_last_host(self):
        R = run("wkPopup('/p', 'a1'); wkPopup('/p', 'a2'); WKSHIFT = Date.now(); wkPopup('/p', 'b1'); WKSHIFT = 0;"
                "wkPopup('/p', 'a2');")
        self.assertEqual(R["opened"], ["sidereus_work_a1", "sidereus_work_b1"])
        self.assertEqual(R["reopen"], ["sidereus_work_a1:a2", "sidereus_work_a1:a2"])

    def test_moment_is_own_window_and_never_host(self):
        R = run("wkPopup('/p', 'sess:/p|s', 100); wkPopup('/p', 'agA');")
        self.assertEqual(R["opened"], ["sidereus_work_sess__p_s_100", "sidereus_work_agA"])
        self.assertEqual(R["reopen"], [])

    def test_failing_cross_window_call_falls_back(self):
        R = run("POPS.sidereus_work_x = fakeWin('sidereus_work_x', [], true); wkPopup('/p', 'agA');")
        self.assertEqual(R["opened"], ["sidereus_work_agA"])
        self.assertEqual(R["err"], ["wkReopen"])


if __name__ == "__main__":
    unittest.main()
