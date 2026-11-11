"""Builtin pipeline runs (48 plKnown/plHomes/plAway/plLiveProjs): a Sidereus builtin (security-fix) lands on its run's
recorded proj, not as an orphan; non-builtin names keep the owner rule. Pure functions under node with stubs; no live files."""
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
const K = {'/w/side': {n: 1, names: ['arch-map']}, '/w/a': {n: 1, names: ['bugfix']}, '/w/b': {n: 1, names: ['bugfix']}, '/w/admin': {n: 0, names: []}};
Object.defineProperty(K, 'bi', {value: new Set(['security-fix'])});
const run = (name, proj) => ({name: name, proj: proj, t1: 5, stages: {Fix: {o: 'run'}}});
const ses = (cwd, r) => ({sid: 's', cwd: cwd, repos: ['/w/admin'], sub: [], plrun: [r]});
const go = x => { const orph = []; const live = plLiveProjs([x], {}, K, orph); return [live, orph.map(o => o.name)]; };
"""


def run(body):
    src = PRE + "\n".join(js_fn(n) for n in ("plPrLive", "plBi", "plBiProj", "plTagNames", "plHomes", "plAway", "plLiveProjs")) + "\n" + body
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PipelineBuiltinRun(unittest.TestCase):
    def test_builtin_goes_to_run_proj(self):
        self.assertEqual(run("console.log(JSON.stringify(go(ses('/w/x', run('security-fix', '/w/admin')))));"), [{"/w/admin": ["security-fix"]}, []])

    def test_unowned_name_stays_orph(self):
        self.assertEqual(run("console.log(JSON.stringify(go(ses('/w/x', run('nowhere', '/w/admin')))));"), [{}, ["nowhere"]])

    def test_two_owners_stay_orph(self):
        self.assertEqual(run("console.log(JSON.stringify(go(ses('/w/x', run('bugfix', '')))));"), [{}, ["bugfix"]])

    def test_builtin_without_proj_stays_orph(self):
        self.assertEqual(run("console.log(JSON.stringify(go(ses('/w/x', run('security-fix', '')))));"), [{}, ["security-fix"]])

    def test_builtin_does_not_dot_cwd(self):
        self.assertEqual(run("console.log(JSON.stringify(go(ses('/w/side', run('security-fix', '/w/admin')))));"), [{"/w/admin": ["security-fix"]}, []])


if __name__ == "__main__":
    unittest.main()
