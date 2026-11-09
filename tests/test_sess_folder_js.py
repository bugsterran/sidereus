"""Sessions list «n in folder» marker (40ba sessFolderCounts / sessFolderChip / sessIdRow): live rows sharing a
cwd are counted once each; ended rows and rows without cwd never count; one row in a folder gets no marker.
Folded header-only worktree groups get a row end (40bb sessWtHeadHtml .swthf). Node with stubs."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

SRC = "\n".join(js_fn(n) for n in ("sessFolderKey", "sessFolderCounts", "sessFolderSet", "sessFolderChip", "sessIdRow",
                                    "sessWtHeadHtml", "sessWtCaret", "sessWtCount", "sessWtAttn", "sessWtNeed")) + r"""
let sessFolderN = new Map();
const wtFold = new Set();
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s;
const TV = o => o.msg.replace(/\{(\w+)\}/g, (_, k) => o.vars[k]);
function aiLogo(){ return ''; } function sessBranchHtml(){ return ''; } function acctChip(){ return ''; }
function sessGitChip(){ return ''; } function sessUsage(){ return ''; } function sessWorkBadges(){ return ''; }
function sessActs(){ return ''; } function platName(k){ return String(k); }
const S = (cwd, state) => ({project: 'api', cwd: cwd, state: state || 'wait', sid: 'x'});
const rows = [S('/r/api'), S('/r/api/', 'tool'), S('/r/api', 'done'), S('/r/api', 'gone'), S('/r/web'), S(''), {project: 'n'}];
const c = sessFolderCounts(rows);
sessFolderSet(rows);
const gr = {key: '/r/app', main: '/r/app', name: 'app', kids: [{state: 'wait'}]};
const open = sessWtHeadHtml(gr);
wtFold.add('/r/app');
process.stdout.write(JSON.stringify({
  api: c.get('/r/api'), web: c.get('/r/web'), keys: [...c.keys()],
  shared: sessIdRow(S('/r/api')), alone: sessIdRow(S('/r/web')), ended: sessIdRow(S('/r/api', 'done')),
  none: sessFolderChip({}, undefined), one: sessFolderChip({}, 1),
  open: open, folded: sessWtHeadHtml(gr),
}));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SessFolder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = subprocess.run(node_e(SRC), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        cls.R = json.loads(r.stdout)

    def test_counts_live_rows_per_folder(self):
        self.assertEqual(self.R["api"], 2)   # trailing slash folds; done/gone excluded
        self.assertEqual(self.R["web"], 1)
        self.assertEqual(sorted(self.R["keys"]), ["/r/api", "/r/web"])   # no cwd = unknown, not a folder

    def test_marker_only_when_shared(self):
        self.assertIn('class=sfn', self.R["shared"])
        self.assertIn('>2 in folder</span>', self.R["shared"])
        self.assertIn('folder totals', self.R["shared"])
        self.assertNotIn('sfn', self.R["alone"])
        self.assertNotIn('sfn', self.R["ended"])
        self.assertEqual(self.R["none"], "")
        self.assertEqual(self.R["one"], "")

    def test_marker_sits_after_name(self):
        h = self.R["shared"]
        self.assertLess(h.index('class=sp '), h.index('class=sfn'))

    def test_folded_header_gets_row_end(self):
        self.assertNotIn('swthf', self.R["open"])
        self.assertIn('class="swth swthf"', self.R["folded"])


if __name__ == "__main__":
    unittest.main()
