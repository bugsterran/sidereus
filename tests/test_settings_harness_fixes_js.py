"""«Security tools» empty list vs failed request (web/js/90e-diag.js)."""
import json
import os
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SRC = i18n_prelude("'ko'", ("T",)) + r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const js = f => fs.readFileSync(path.join(ROOT, 'web', 'js', f), 'utf8');
const c = {T, softErr: () => {}, tabGet: (k, d) => d, lsGet: (k, d) => d, lsSet: () => true,
  esc: s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'),
  matchMedia: () => ({matches: false, addEventListener: () => {}}),
  document: {documentElement: {dataset: {}, style: {setProperty(){}, removeProperty(){}}}, getElementById: () => null, querySelector: () => null},
  getJSON: async () => ({ok: true}), LANG: 'ko'};
vm.createContext(c);
vm.runInContext(js('90-settings.js') + '\n' + js('90e-diag.js'), c);
const R = {};
R.empty = vm.runInContext("DX = {ok: true}; DXT = {ok: true, tools: []}; cfgPaneDx()", c);
R.failed = vm.runInContext("DXT = {err: 'boom'}; cfgPaneDx()", c);
console.log(JSON.stringify(R));
"""


def run():
    r = subprocess.run(node_e("const ROOT = " + json.dumps(ROOT) + ";\n" + SRC), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SecToolsEmptyVsFailed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run()

    def test_empty_list_is_not_a_load_failure(self):
        self.assertNotIn("불러오지 못", self.r["empty"].split("보안 도구")[-1])
        self.assertIn("설치 안 됨", self.r["empty"])

    def test_failed_request_still_says_could_not_load(self):
        tail = self.r["failed"].split("보안 도구")[-1]
        self.assertIn('class="cfgpd err"', tail)
        self.assertIn("boom", tail)


if __name__ == "__main__":
    unittest.main()
