"""Sessions list worktree groups: folding a group keeps the lead column width (40ba sessFit + 40bb sessWtStemLead),
and the count reads singular for one child (40bb sessWtCount). Node with stub elements."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e
from tests.test_saver_quota_js import jconst

SRC = "\n".join(js_fn(n) for n in ("sessFit", "sessWtStemLead", "sessWtCount")) + "\n" + jconst("SX_DROP") + r"""
const window = {};
const TV = o => o.msg.replace(/\{(\w+)\}/g, (_, k) => o.vars[k]);
const getComputedStyle = () => ({columnGap: '4px'});
const W = {sd: 8, ailg: 14, swtg: 10, swtbr: 12};
const item = c => ({cls: c, getBoundingClientRect: () => ({width: W[c]}), remove(){ this.par.items.splice(this.par.items.indexOf(this), 1); }});
// .sxl stub: flex row with 6px padding each side and a 4px gap, width derived from its items.
const lead = cs => { const l = {items: [], querySelector: s => l.items.find(e => s === '.' + e.cls) || null,
    querySelectorAll: s => l.items.filter(e => s.split(',').includes('.' + e.cls)),
    prepend(e){ e.par = l; l.items.unshift(e); },
    getBoundingClientRect: () => ({width: 12 + l.items.reduce((s, e) => s + W[e.cls], 0) + 4 * Math.max(0, l.items.length - 1)})};
  cs.forEach(c => { const e = item(c); e.par = l; l.items.push(e); }); return l; };
const fake = w => ({getBoundingClientRect: () => ({width: w}), offsetWidth: w, offsetTop: 0, offsetHeight: 16, firstChild: 1, querySelector: () => null});
const row = cs => { const l = lead(cs), id = fake(200), us = fake(100), gs = {clientWidth: 700};
  return {clientWidth: 760, querySelector: s => ({'.sxid': id, '.sxus': us, '.sxl': l, '.sxgs': gs})[s] || null, querySelectorAll: () => [id, us]}; };
const document = {createElement: () => ({cls: '', set className(c){ this.cls = c; }, getBoundingClientRect(){ return {width: W[this.cls]}; },
  remove(){ this.par.items.splice(this.par.items.indexOf(this), 1); }})};
const fit = (rows, grp) => { const p = {};
  const box = {clientWidth: 760, style: {setProperty: (k, v) => { p[k] = v; }, removeProperty: k => { delete p[k]; }},
    classList: {add(){}, remove(){}}, querySelectorAll: () => rows, querySelector: s => (s === '.swtg' && grp) ? {} : null};
  sessFit(box); return p['--sxlead']; };
const plain = ['sd', 'ailg'];
const probe = [row(plain)];
fit(probe, true);
process.stdout.write(JSON.stringify({
  none: fit([row(plain), row(plain)], false),
  expanded: fit([row(['swtg', ...plain]), row(['swtbr', ...plain]), row(plain)], true),
  folded: fit([row(['swtg', ...plain]), row(plain)], true),
  headerOnly: fit([row(plain)], true),
  probeLeft: probe[0].querySelector('.sxl').items.length,
  one: sessWtCount(1), two: sessWtCount(2),
}));
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SessWtLead(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = subprocess.run(node_e(SRC), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        cls.R = json.loads(r.stdout)

    def test_no_group_lead_unchanged(self):
        self.assertEqual(self.R["none"], "39px")   # 12 + 8 + 4 + 14 = 38, +1 slack

    def test_fold_keeps_lead(self):
        self.assertEqual(self.R["expanded"], "55px")   # child row: 38 + 4 + 12 stem
        self.assertEqual(self.R["folded"], self.R["expanded"])
        self.assertEqual(self.R["headerOnly"], self.R["expanded"])

    def test_probe_removed(self):
        self.assertEqual(self.R["probeLeft"], 2)

    def test_count_plural(self):
        self.assertEqual(self.R["one"], "1 worktree session")
        self.assertEqual(self.R["two"], "2 worktree sessions")


if __name__ == "__main__":
    unittest.main()
