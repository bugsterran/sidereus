"""84m: structure «Architecture» header «Export HTML» menu (R1) — «Simple» opens the HEAD brief.html or previews an arch-brief
request (R2); disabled without a HEAD map (R4); run end re-fetches."""
import json
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_fn
from tests._node import node_e

PRE = "\n".join([
    "let LANG = 'ko';", i18n_prelude("LANG", ("T",)),
    "const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));",
    "function sid8(s){ return String(s).slice(0, 8); } function mboxIn(x){ return !!x.mbox; }",
    "const ARCH_BRIEF_PL = 'arch-brief';",
])
FNS = ("archBriefHref", "archXOk", "archXHead", "archBriefBusy", "archXBtn", "archXMenu", "archDmBody", "archBriefDmBody", "archNoHome", "archWhyOff",
       "archBriefReqHtml")
C = "a" * 40
MAP = {"ok": True, "modules": [{"id": "m"}], "edges": [], "commit": C, "head": C}


def run(expr):
    js = PRE + "\nlet BRIEFRUN = {}; const ARCH = {xm: '', breq: null, req: null};\n" + "\n".join(js_fn(n) for n in FNS) + "\nprocess.stdout.write(JSON.stringify(" + expr + "));"
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ArchBriefJs(unittest.TestCase):
    def test_x_ok_needs_a_map(self):
        """No map, empty, bad or no modules -> export off; an older-commit map exports (stamped in 84m2)."""
        ds = [None, dict(MAP, ok=False), dict(MAP, empty=True), dict(MAP, bad=True), dict(MAP, modules=[]), dict(MAP, stale=True),
              dict(MAP, head="b" * 40), dict(MAP, head=""), MAP]
        self.assertEqual(run("%s.map(archXOk)" % json.dumps(ds)), [False] * 5 + [True] * 4)
        self.assertEqual(run("%s.map(archXHead)" % json.dumps(ds)), [False] * 8 + [True])

    def test_disabled_button_tooltip(self):
        """Disabled with the «draw first» reason only when there is no map; no menu even if xm is set."""
        h = run("(ARCH.xm = '/r', archXBtn(" + json.dumps(dict(MAP, modules=[])) + ", '/r'))")
        self.assertIn("data-arxp", h)
        self.assertIn(" disabled", h)
        self.assertIn("aria-haspopup=menu", h)
        self.assertIn("지금 커밋의 아키텍처 구조도를 먼저 그려 주세요", h)
        self.assertIn("HTML 추출", h)
        self.assertNotIn("archxm", h)

    def test_stale_map_exports_but_no_overview_request(self):
        """An older-commit map opens the menu; «Simple» without a brief cannot request a run (needs the HEAD map)."""
        h = run("(ARCH.xm = '/r', archXBtn(" + json.dumps(dict(MAP, stale=True, head="b" * 40)) + ", '/r'))")
        self.assertIn("archxm", h)
        self.assertRegex(h, r"data-arxs disabled")
        self.assertIn("data-arxd", h)

    def test_menu_with_brief_is_a_link(self):
        """R1/R2: open menu = «Simple» real link (new tab, noopener noreferrer) + «Detailed» button."""
        d = dict(MAP, brief={"commit": C, "file": "/st/<b>&\"x/brief.html"})
        closed, h = run("[archXBtn(%s, '/my repo/a&b'), (ARCH.xm = '/my repo/a&b', archXBtn(%s, '/my repo/a&b'))]" % (json.dumps(d), json.dumps(d)))
        self.assertNotIn("archxm", closed)
        self.assertIn("aria-expanded=true", h)
        self.assertIn("role=menu", h)
        self.assertIn('href="/api/arch/brief?path=%2Fmy%20repo%2Fa%26b&amp;commit=' + C + '"', h)
        self.assertIn("target=_blank", h)
        self.assertIn('rel="noopener noreferrer"', h)
        self.assertIn("/st/&lt;b&gt;&amp;&quot;x/brief.html", h)
        self.assertNotIn("<b>", h)
        self.assertIn(">심플</a>", h)
        self.assertIn("data-arxd", h)
        self.assertIn(">상세</button>", h)
        self.assertNotIn("data-arxs", h)

    def test_menu_without_brief_requests(self):
        """R2: no brief -> «Simple» is a request button, disabled while a brief run is live."""
        idle, busy = run("[(ARCH.xm = '/r', archXBtn(%s, '/r')), (BRIEFRUN = {'/r': {stage: 'x'}}, archXBtn(%s, '/r'))]" % (json.dumps(MAP), json.dumps(MAP)))
        self.assertIn("data-arxs title=", idle)
        self.assertNotIn("href=", idle)
        self.assertIn("data-arxs disabled", busy)

    def test_brief_dm_body(self):
        """R2: wire text names the pipeline, read-only store, stage titles verbatim and the real gate flag."""
        cc, cx = run("[archBriefDmBody('/r', '/sid/', false), archBriefDmBody('/r', '/sid', true)]")
        lines = cc.split("\n")
        self.assertEqual(lines[0], "Pipeline arch-brief run — request: «/r: draw architecture overview»")
        self.assertEqual(lines[1], "Target repository: /r")
        self.assertEqual(lines[2], "Read-only: never write to the repository — write only S/brief.json, S = the store dir printed by stage 준비")
        self.assertEqual(lines[3], "Pipeline: /sid/.claude/pipelines/arch-brief.json (준비 → 개요 그리기 → 검증)")
        self.assertEqual(lines[4], "Gate: python3 /sid/scripts/arch_brief.py --last (Windows: py /sid/scripts/arch_brief.py --last)")
        self.assertIn("[pl:arch-brief/<stage title>] (not [pl:-])", lines[5])
        self.assertIn("(for arch-brief: S/map.json and S/verify.json, then S/brief.json)", cx)
        self.assertNotIn("arch-map", cx)

    def test_preview_confirm_gated(self):
        """R2: preview shows recipient + text; confirm disabled while the recipient is not logged in."""
        cands = [{"sid": "s1234567890", "id": "mb", "login": True, "dir": "r"}, {"sid": "s2", "id": "", "login": False, "dir": "x"}]
        ok, off = run("[archBriefReqHtml({p: '/r', sid: 's1234567890'}, '/r', '/sid', %s), archBriefReqHtml({p: '/r', sid: 's2'}, '/r', '/sid', %s)]"
                      % (json.dumps(cands), json.dumps(cands)))
        self.assertIn("data-arbs", ok)
        self.assertIn("r · s1234567 · mb", ok)
        self.assertIn("Pipeline arch-brief run", ok)
        self.assertIn("data-arbgo>", ok)
        self.assertIn("data-arbgo disabled", off)

    def test_busy_on_sent_and_sig_tracks_record(self):
        """R2: a 'sent' brief record already blocks «Simple»; the tick signature moves with the record state/stage."""
        js = PRE + "\nlet BRIEFRUN = {}; const ARCH = {xm: '', breq: null, req: null}; let PLREQ = {};\n" + "\n".join(js_fn(n) for n in (
            "archBriefBusy", "archXSig", "archReqMs", "archReqRows", "archReqLive", "archReqLast")) + """
const ARCH_REQ_KEEP_MS = 3600000, ARCH_REQ_LBL = {sent: 1, run: 1, stopping: 1, stopped: 1, done: 1, gone: 1};
const R = st => ({'/r': [{id: 'm1', pipeline: 'arch-brief', state: st, stage: st === 'run' ? '개요 그리기' : '', at: Date.now()}]});
const b0 = archBriefBusy('/r'), s0 = archXSig('/r');
PLREQ = R('sent'); const b1 = archBriefBusy('/r'), s1 = archXSig('/r');
PLREQ = R('run'); const s2 = archXSig('/r');
PLREQ = R('done'); const b3 = archBriefBusy('/r');
process.stdout.write(JSON.stringify([b0, b1, b3, s0 !== s1, s1 !== s2]));"""
        r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        self.assertEqual(json.loads(r.stdout), [False, True, False, True, True])

    def test_menu_wrapper_not_clipped(self):
        """R1: the span wrapper overrides 40-tokens `.wvh span{overflow:hidden}`, or the menu is clipped away."""
        import os
        import re
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "css", "79-structure-arch.css"), encoding="utf-8") as fh:
            css = fh.read()
        self.assertRegex(css, r"(?m)^\.wvh \.archxw\{[^}]*overflow:visible")
        self.assertTrue(re.search(r"<span class=archxw>", js_fn("archXBtn")))

    def test_ko_labels(self):
        """R1: Korean labels for the button and both menu items."""
        self.assertEqual(run("[T('Export HTML'), T('Simple', 'arch export'), T('Detailed', 'arch export')]"), ["HTML 추출", "심플", "상세"])

    def test_run_end_refetches(self):
        js = PRE + "\n" + "\n".join(js_fn(n) for n in ("archBriefEnded", "archBriefPoll")) + """
let BRIEFRUN = {}; const ARCH = {cache: {'/a': {}, '/b': {}}, load: {'/b': 1}}, F = [];
function archFetch(p, force){ F.push([p, force]); }
archBriefPoll({'/a': {stage: 'x'}, '/b': {stage: 'y'}, '/c': {stage: 'z'}});
const f0 = F.length;
archBriefPoll({'/b': {stage: 'y'}});
const f1 = F.slice();
archBriefPoll({});   // /b ended but still loading: no double fetch
process.stdout.write(JSON.stringify([f0, f1, F, Object.keys(BRIEFRUN)]));"""
        r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        f0, f1, f, keys = json.loads(r.stdout)
        self.assertEqual(f0, 0)                       # runs starting fetch nothing
        self.assertEqual(f1, [["/a", True]])          # /a ended (cached) -> forced re-fetch; /c ended but never viewed
        self.assertEqual(f, [["/a", True]])
        self.assertEqual(keys, [])


if __name__ == "__main__":
    unittest.main()
