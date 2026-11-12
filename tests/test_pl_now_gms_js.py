"""Child CLI runs (x.gms) in «Working now» and the sessions drawer (40b gmsLive/gmsRun/gmsParChip, 40ba sessWorkBadges,
48j plNowGms/plNowSt/plNowList). Pure functions under node with stubs; no live files."""
import re
import shutil
import unittest

from tests._load import js_fn
from tests import test_pl_now_js as base

STUB = """
const AILG = { gm: ['Gemini'], cx: ['Codex CLI (OpenAI)'], pi: ['pi'], cc: ['Claude Code'] };
function ago(s){ return s + 's'; } function fmtTok(n){ return n + 'T'; }
function sessPlChip(){ return ''; }
"""
FNS = "\n".join(js_fn(n) for n in ("platName", "gmsLive", "gmsRun", "gmsParChip", "plNowGms", "sessWorkBadges")) + "\n"
PI = """{state: 'tool', sid: 'p1', cwd: '/pi', plat: 'pi', project: 'pp', gms: [
  {sid: 'g1', plat: 'gm', cmd: 'gemini -p', model: 'gem-2', dur: 30, tok: 500, run: 1, task: 'SECRET-TASK', prompt: 'SECRET-PROMPT'},
  {sid: 'g2', plat: 'cx', cmd: '', dur: 5, run: 0},
  {sid: 'g3', plat: 'gm', cmd: 'gemini old', done: 1, run: 0}]}"""
CC = """{state: 'wait', sid: 'c1', cwd: '/cc', plat: 'cc', project: 'cp', gms: [
  {sid: 'x1', plat: 'cx', cmd: 'codex exec', run: 1}, {sid: 'x2', plat: 'gm', cmd: 'gemini -p', run: 1}, {sid: 'x1', plat: 'cx', cmd: 'codex exec', run: 1}]}"""


def run(body):
    return base.run(base.NOW + STUB + FNS + body)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PlNowGms(unittest.TestCase):
    def test_r1_pi_and_cc_parent_child_rows(self):
        h = run("console.log(JSON.stringify(plNowList([" + PI + ", " + CC + "])));")
        pi, cc = h.split('data-pncwd="/cc"', 1)
        kids = re.findall(r'<button type=button class="plnagr tlnm[^"]*" data-pnagc="/pi" data-pnplat="pi"[^>]*><b>(.*?)</b></button>', pi)
        self.assertEqual(len(kids), 2)                                        # done child absent
        self.assertIn("ailg-gm", kids[0]); self.assertIn("gemini -p", kids[0]); self.assertIn('tlds on', kids[0])
        self.assertIn("ailg-cx", kids[1]); self.assertIn("Codex CLI", kids[1]); self.assertNotIn("tlds on", kids[1])
        self.assertNotIn("gemini old", h)
        ck = re.findall(r'class="plnagr tlnm[^"]*" data-pnagc="/cc"', cc)
        self.assertEqual(len(ck), 2)                                          # same sid twice = one row
        self.assertIn("codex exec", cc); self.assertIn("ailg-gm", cc)

    def test_r2_parallel_marker_card_and_drawer(self):
        r = run("const a = " + CC + ", b = " + PI + ", c = {state: 'tool', cwd: '/n'};"
                "console.log(JSON.stringify([plNowList([a]), sessWorkBadges(a), plNowList([b]), sessWorkBadges(b), plNowList([c]), sessWorkBadges(c), gmsRun(a).length]));")
        self.assertIn("parallel ×2", r[0]); self.assertIn("parallel ×2", r[1])  # x1 twice counts once
        self.assertEqual(r[6], 2)
        for s in r[2:6]:
            self.assertNotIn("parallel", s)                                   # 1 running + 1 idle / no gms: no marker, no ×0

    def test_r4_metadata_only_no_popup_id(self):
        h = run("console.log(JSON.stringify(plNowList([" + PI + "])));")
        self.assertNotIn("SECRET", h)
        kid = re.findall(r'<button type=button class="plnagr[^>]*>', h)
        self.assertTrue(kid)
        for k in kid:
            self.assertNotIn("data-pntid", k)
        self.assertIn("gem-2 · 30s · 500T · Running", h)

    def test_r1_status_counts_only_running_children(self):
        r = run("console.log(JSON.stringify([plNowSt({state: 'wait', gms: [{sid: 'a', run: 1}]}), plNowSt({state: 'wait', gms: [{sid: 'a', run: 0}]}),"
                " plNowSt({state: 'wait', gms: [{sid: 'a', run: 1, done: 1}]})]));")
        self.assertEqual(r, ["work", "idle", "idle"])

    def test_r1_cap_drops_idle_first(self):
        kids = ",".join("{sid: 'i%d', plat: 'gm', cmd: 'idle%d', run: 0}" % (i, i) for i in range(5)) + "," + \
            ",".join("{sid: 'r%d', plat: 'cx', cmd: 'run%d', run: 1}" % (i, i) for i in range(3))
        h = run("console.log(JSON.stringify(plNowGms({cwd: '/a', gms: [" + kids + "]})));")
        self.assertEqual(h.count("plnagr"), 6)
        for i in range(3):
            self.assertIn("run%d" % i, h)
        self.assertIn("+2 more", h)


if __name__ == "__main__":
    unittest.main()
