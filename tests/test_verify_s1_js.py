"""Rail toggle refits the status bar (92d railApply) · wfBadge label goes through T() (48g) ·
cache share text keeps AA contrast in light theme (86 rtCache) · people room count folds viewer ids (50)."""
import json
import os
import shutil
import subprocess
import unittest

from tests._load import js_fn, ROOT
from tests.test_saver_quota_js import i18n, jconst
from tests._node import node_e


def run(body, fns):
    src = ("let THEME = 'dark';\nconst document = {documentElement: {dataset: {get theme(){ return THEME; }}}, body: null, getElementById: () => null};\n"
           + i18n() + "\n" + jconst("esc") + "\n" + jconst("thc") + "\n" + "\n".join(js_fn(f) for f in fns)
           + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class VerifyS1(unittest.TestCase):
    def test_rail_apply_rebuilds_status_bar_once_next_frame(self):
        R = run(r"""
let frames = [], sb = 0, railOpen = true, railSbRaf = 0; const RAIL_W = 1200, innerWidth = 1440;
function requestAnimationFrame(f){ frames.push(f); return frames.length; }
function cancelAnimationFrame(id){ if(id) frames[id - 1] = null; }
function buildSbar(){ sb++; } function railTip(){}
const cl = () => ({toggle(){}, contains(){ return true; }});
const rail = {classList: cl()};
document.body = {classList: cl()}; document.getElementById = id => id === 'rail' ? rail : null;
railApply(); railApply();
R.before = sb; frames.forEach(f => f && f()); R.after = sb;
""", ("railMode", "railActive", "railApply"))
        self.assertEqual((R["before"], R["after"]), (0, 1))

    def test_wf_badge_translated(self):
        R = run("LANG = 'ko'; R.ko = wfBadge('run', 'p'); LANG = 'en'; R.en = wfBadge('', '');", ("wfBadge",))
        self.assertIn(">워크플로</i>", R["ko"])
        self.assertIn('title="워크플로 · run · p"', R["ko"])
        self.assertIn(">Workflow</i>", R["en"])

    def test_cache_share_text_contrast_light(self):
        R = run(r"""
LANG = 'en';
const rep = {days: 7, cache: {days: [{d: '2026-11-01', pct: 40, read: 10, create: 5}], sessions: [{sid: 'abc', project: 'p', pct: 40, read: 1, create: 1}]}};
THEME = 'light'; R.light = rtCache(rep); THEME = 'dark'; R.dark = rtCache(rep);
""", ("fmtTok", "fmtPct", "rtCache"))
        self.assertIn("background:#b8641a", R["light"])
        self.assertIn('style="color:#9a4f0f"', R["light"])
        self.assertIn('style="color:#e8913a"', R["dark"])

    def test_people_room_count_folds_viewer_ids(self):
        R = run(r"""
const CFG = {viewerMe: 'me', viewerIds: ['me', 'viewer', '나']};
R.n = rcWhoIds(['viewer', '나', 'me', 'a', 'a', '']).length;
""", ("rcWhoIds",))
        self.assertEqual(R["n"], 2)
        with open(os.path.join(ROOT, "web", "js", "50-people.js"), encoding="utf-8") as fh:
            self.assertIn("rcWhoIds(r.members||[]).length", fh.read())


if __name__ == "__main__":
    unittest.main()
