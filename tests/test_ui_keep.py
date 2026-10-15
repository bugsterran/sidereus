"""97b: selections restored after refresh are shape-checked; junk leaves the defaults."""
import json
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


class UiKeepJs(unittest.TestCase):
    def run_js(self, saved):
        pre = ("let place = 'all', filter = 'all', WKRANGE = 7;\n"
               "const WKR_LABEL = {1: 'd', 7: 'w', 30: 'm'};\n"
               "function setFilter(k){ filter = (typeof k === 'string' && k) ? k : 'all'; }\n")
        src = pre + "\n".join(js_fn(f) for f in ("uiKeepOk", "uiKeepApply", "uiKeepSnap")) \
            + "\nuiKeepApply(" + json.dumps(saved) + ");\nconsole.log(JSON.stringify(uiKeepSnap()));"
        return json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True).stdout)

    def test_round_trip(self):
        s = {"place": "room:release", "filter": "thread:경고DM·x", "wkr": 30}
        self.assertEqual(self.run_js(s), s)

    def test_old_bythread_key_ignored(self):
        got = self.run_js({"place": "dm", "filter": "all", "byThread": True, "wkr": 7})
        self.assertEqual(got, {"place": "dm", "filter": "all", "wkr": 7})

    def test_junk_keeps_defaults(self):
        got = self.run_js({"place": "evil", "filter": "a\nb", "wkr": 5})
        self.assertEqual(got, {"place": "all", "filter": "all", "wkr": 7})
        self.assertEqual(self.run_js(None), {"place": "all", "filter": "all", "wkr": 7})


class TlgKeepJs(unittest.TestCase):
    """Timeline rail pick: restored shape-checked; a pick that is gone falls back to auto once sessions load."""
    PRE = ("let tlgSel = '', tlgRepoSel = {key: '', repo: ''}, tlgMode = 'auto';\n"
           "const TLG_MODES = [['head'], ['start'], ['remote']];\n"
           "const cpKey = x => x.sid ? 's:' + x.sid : 'c:' + x.cwd; const tlgRepos = c => [c];\n")

    def run_js(self, saved, sess, tail="console.log(JSON.stringify(tlgKeepSnap()));"):
        fns = ("uiKeepOk", "tlgKeepApply", "tlgKeepSnap", "tlgAge", "tlgName", "tlgSessions", "tlgRepoOrder", "tlgTarget")
        src = self.PRE + "let SESS = " + json.dumps(sess) + ";\n" + "\n".join(js_fn(f) for f in fns) \
            + "\ntlgKeepApply(" + json.dumps(saved) + ");\ntlgTarget();\n" + tail
        return json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True).stdout)

    S = [{"sid": "a", "cwd": "/r/a", "project": "a", "ageSec": 90},
         {"sid": "b", "cwd": "/r/b", "project": "b", "ageSec": 5},
         {"sid": "c", "cwd": "/r/c", "project": "c"}]

    def test_round_trip(self):
        s = {"sel": "s:a", "rkey": "s:a", "repo": "/r/a", "mode": "start"}
        self.assertEqual(self.run_js(s, self.S), s)

    def test_missing_pick_falls_back(self):
        got = self.run_js({"sel": "s:gone", "rkey": "x", "repo": "rel", "mode": "evil"}, self.S)
        self.assertEqual((got["sel"], got["mode"]), ("", "auto"))

    def test_pick_survives_empty_sessions(self):
        self.assertEqual(self.run_js({"sel": "s:gone"}, [])["sel"], "s:gone")

    def test_newest_first(self):
        order = self.run_js(None, self.S, "console.log(JSON.stringify(tlgSessions().map(x => x.sid)));")
        self.assertEqual(order, ["b", "a", "c"])
        rp = self.run_js(None, self.S, "console.log(JSON.stringify(tlgRepoOrder(['/r/c', '/r/a', '/r/b'])));")
        self.assertEqual(rp, ["/r/b", "/r/a", "/r/c"])


if __name__ == "__main__":
    unittest.main()
