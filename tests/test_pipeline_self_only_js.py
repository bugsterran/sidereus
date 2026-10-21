"""Default project pick (48 plLoadProjs) skips a self-only chip (server flag `self_only`); 08b ppGroups sorts it last.
Stubs only, no live files."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

PRE = "\n".join([
    "function plPaint(){}",
    "let LIST = null; async function getJSON(){ return LIST; }",
])


def run(body):   # js_fn only finds plain `function`, so the async loader is cut out here
    js = PRE + "\n" + re.search(r"^async function plLoadProjs\(.*?^}$", js_all(), re.M | re.S).group(0) + "\n(async () => {" + body + "})();"
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


def pick(projects, proj=""):
    return run("LIST = {ok: true, projects: " + json.dumps(projects) + "};"
               "globalThis.PLS = {projs: null, proj: " + json.dumps(proj) + ", data: {}, busy: {}};"
               "await plLoadProjs(); console.log(JSON.stringify(PLS.proj));")


SELF = {"path": "/sidereus", "n": 7, "self_only": True}


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SelfOnlyDefault(unittest.TestCase):
    def test_fresh_clone_does_not_open_self(self):
        self.assertEqual(pick([SELF]), "")

    def test_other_project_wins_over_self(self):
        self.assertEqual(pick([SELF, {"path": "/work", "n": 1}]), "/work")

    def test_self_with_session_is_default_as_before(self):
        self.assertEqual(pick([{"path": "/sidereus", "n": 7}, {"path": "/work", "n": 1}]), "/sidereus")

    def test_remembered_self_selection_kept(self):
        self.assertEqual(pick([SELF, {"path": "/work", "n": 1}], "/sidereus"), "/sidereus")

    def test_self_only_sorts_last(self):
        js = "const ppByName = (a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0);\nconst PP_RECENT_N = 5;\n" + js_fn("ppGroups") + "\n"
        js += ("const g = ppGroups([{p: '/a', name: 'a', last: true}, {p: '/b', name: 'b'}, {p: '/c', name: 'c'}], [], '', '');"
               "console.log(JSON.stringify(g.all.map(e => e.p)));")
        r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        self.assertEqual(json.loads(r.stdout), ["/b", "/c", "/a"])


if __name__ == "__main__":
    unittest.main()
