"""Pipelines tab live dot (48 plTagNames/plLiveProjs): an open server run (SESS[].plrun) counts at once, without waiting
for a tagged subagent label (agent-meta TTL 20 s). Pure functions under node with stubs; no live files."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

PRE = """
const ARCHRUN = {}; const PLS = {data: {}};
function plDescStage(){ return null; } function plLabType(){ return ''; } function plTk(t){ return t; }
function plRunName(){ return null; } function plLoad(){} function plLoadAll(){}
"""


def run(body):
    src = PRE + "\n".join(js_fn(n) for n in ("plPrLive", "plTagNames", "plHomes", "plAway", "plLiveProjs")) + "\n" + body
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


OPEN = "{name: 'bugfix', proj: '/w/a', t1: 5, stages: {Design: {o: 'run'}}}"
KNOWN = "const K = {'/w/a': {n: 1, names: ['bugfix']}, '/w/b': {n: 1, names: ['bugfix']}};"


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PipelineLiveProj(unittest.TestCase):
    def test_open_plrun_without_tag_is_live(self):
        r = run(KNOWN + "const x = {sid: 's', cwd: '/w/a', sub: [], plrun: [" + OPEN + "]};"
                "console.log(JSON.stringify([plTagNames(x, {}), plLiveProjs([x], {}, K)]));")
        self.assertEqual(r, [["bugfix"], {"/w/a": ["bugfix"]}])

    def test_ended_run_not_live(self):
        r = run(KNOWN + "const x = {sid: 's', cwd: '/w/a', sub: [], plrun: [{name: 'bugfix', proj: '/w/a', end: 9, stages: {Design: {o: 'run'}}}]};"
                "console.log(JSON.stringify([plTagNames(x, {}), plLiveProjs([x], {}, K)]));")
        self.assertEqual(r, [[], {}])

    def test_run_lands_only_in_its_recorded_project(self):
        r = run(KNOWN + "const x = {sid: 's', cwd: '/w/a', repos: ['/w/b'], sub: [], plrun: [{name: 'bugfix', proj: '/w/b', t1: 5, stages: {Design: {o: 'run'}}}]};"
                "console.log(JSON.stringify(plLiveProjs([x], {}, K)));")
        self.assertEqual(r, {"/w/b": ["bugfix"]})

    def test_plm_and_plrun_same_name_once(self):
        r = run("const x = {sid: 's', cwd: '/w/a', sub: [], plm: {name: 'bugfix'}, plrun: [" + OPEN + "]};"
                "console.log(JSON.stringify(plTagNames(x, {})));")
        self.assertEqual(r, ["bugfix"])


if __name__ == "__main__":
    unittest.main()
