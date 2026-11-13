"""84m: structure «Architecture» header «Export HTML» menu — «Simple» opens the HEAD brief.html (an older map opens its own, stamped
with how far HEAD moved); «Ask the session to draw» previews a brief-ask request to the repo's own session (R1, R2); done re-fetches (R3)."""
import json
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_all, js_fn
from tests._node import node_e

PRE = "\n".join([
    "let LANG = 'ko';", i18n_prelude("LANG", ("T", "TV")),
    "const esc = s => String(s).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));",
    "function sid8(s){ return String(s).slice(0, 8); } function mboxIn(x){ return !!x.mbox; }",
    "const ARCH_ASK_PL = 'brief-ask', ARCH_BRIEF_PL = 'arch-brief';",
])
FNS = ("archBriefHref", "archXOk", "archXHead", "archAskOk", "archOwners", "archBase", "archCands", "archHome", "archBriefBusy", "archXBtn", "archXMenu",
       "archAskBody", "archNoHome", "archWhyOff", "archBriefReqHtml")
C = "a" * 40
ST = "/data/arch/k1/" + C
FMT = "brief.json v2 schema line one\nline two {\"layout\": numbers only}"
ASK = {"dir": ST, "commit": C, "fmt": FMT}
MAP = {"ok": True, "modules": [{"id": "m"}], "edges": [], "commit": C, "head": C, "sidereus": "/sid"}
OWN = {"sid": "own1234567890", "cwd": "/r", "mbox": "mb-own", "model": "opus-x", "plat": "cc"}
OTHER = {"sid": "oth1234567890", "cwd": "/elsewhere", "mbox": "mb-oth", "model": "sonnet-y", "plat": "cc"}


def _top(key, head):
    """Top-level statement of web/js that starts with `head` and holds `key` (an async function or an anonymous handler)."""
    src = js_all()
    i = src.index(key)
    a = src.rindex("\n" + head, 0, i) + 1
    return src[a:src.index("\n}", i) + 2 + (1 if src[src.index("\n}", i) + 2:].startswith(")") else 0)] + ";"


def run(expr):
    js = PRE + "\nlet BRIEFRUN = {}, SESS = []; const ARCH = {xm: '', breq: null, req: null};\n" + "\n".join(js_fn(n) for n in FNS) + "\nprocess.stdout.write(JSON.stringify(" + expr + "));"
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
        self.assertNotIn("data-arxa", h)

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

    def test_older_map_brief_link_says_head_moved(self):
        """An older shown map with its own brief: «Simple» is a link stamped with how far HEAD moved; a HEAD brief has no stamp."""
        d = dict(MAP, stale=True, head="b" * 40, behind=4, brief={"commit": C, "file": "/st/brief.html"})
        old, cur = run("[(ARCH.xm = '/r', archXBtn(%s, '/r')), archXBtn(%s, '/r')]" % (json.dumps(d), json.dumps(dict(MAP, brief={"commit": C, "file": "/st/brief.html"}))))
        self.assertIn('commit=' + C + '"', old)
        self.assertIn("<small>", old)
        self.assertIn("4", old.split("<small>", 1)[1].split("</small>", 1)[0])
        self.assertNotIn("data-arxs", old)
        self.assertNotIn("<small>", cur)

    def test_r1_ask_button_only_for_owning_session(self):
        """R1: «Ask the session to draw» shows only with a cwd === repo live session; none -> one reason line; «Simple» stays disabled."""
        d = json.dumps(dict(MAP, ask=ASK))
        own, other, none, ended = run("[%s].map(ss => (SESS = ss, ARCH.xm = '/r', archXBtn(%s, '/r')))" % (", ".join(json.dumps(x) for x in (
            [OTHER, OWN], [OTHER], [], [dict(OWN, state="done")])), d))
        self.assertIn("data-arxa", own)
        self.assertIn("세션에 그려 달라고 요청", own)
        self.assertIn("data-arxs disabled", own)
        for h in (other, none, ended):
            self.assertNotIn("data-arxa", h)
            self.assertIn("이 저장소에서 실행 중인 세션이 없습니다", h)

    def test_r1_no_ask_without_server_ask_or_head_map(self):
        """R1: no `ask` (older server), a partial one, an ask for another commit or a stale map -> no button and no reason line."""
        asks = [None, dict(ASK, fmt=""), dict(ASK, dir=""), dict(ASK, commit="b" * 40)]
        hs = run("(SESS = [%s], ARCH.xm = '/r', [%s].map(d => archXBtn(d, '/r')))" % (json.dumps(OWN), ", ".join(
            [json.dumps(dict(MAP, ask=a)) for a in asks] + [json.dumps(dict(MAP, ask=ASK, stale=True, head="b" * 40))])))
        for h in hs:
            self.assertNotIn("data-arxa", h)
            self.assertNotIn("이 저장소에서 실행 중인 세션이 없습니다", h)

    def test_r1_ask_disabled_while_sent(self):
        """R1: a live brief-ask record (or a server run) disables the button so a second request waits."""
        busy = run("(SESS = [%s], BRIEFRUN = {'/r': {stage: 'x'}}, ARCH.xm = '/r', archXBtn(%s, '/r'))" % (json.dumps(OWN), json.dumps(dict(MAP, ask=ASK))))
        self.assertIn("data-arxa disabled", busy)

    def test_r2_ask_body(self):
        """R2: wire text holds the format verbatim, the store paths, the --check gate with --commit/--by and «own analysis»."""
        b = run("archAskBody('/r', %s, 'own1234567890', '/sid/', 'en')" % json.dumps(dict(ASK, dir=ST + "/")))
        self.assertIn("Target repository: /r", b)
        self.assertIn("Commit: " + C, b)
        self.assertIn("Decide what is core from your own analysis of this repository; the map is a reference only.", b)
        self.assertIn("write only " + ST + "/brief.json", b)
        self.assertIn(ST + "/map.json and " + ST + "/verify.json", b)
        self.assertIn("Gate: python3 /sid/scripts/arch_brief.py --check --repo /r --commit " + C + " --by own1234567890 "
                      "(Windows: py /sid/scripts/arch_brief.py --check --repo /r --commit " + C + " --by own1234567890)", b)
        self.assertIn("Rerun the gate until it passes", b)
        self.assertTrue(b.endswith("\nFormat:\n" + FMT))
        self.assertIn("Language: English — ", b)
        self.assertIn("Language: Korean — ", run("archAskBody('/r', %s, 's', '/sid', 'ko')" % json.dumps(ASK)))

    def test_r2_ask_body_quotes_paths_with_spaces(self):
        """R2: a repo path with a space stays one shell argument in both gate forms."""
        b = run("archAskBody('/my r', %s, 's1', '/si d', 'en')" % json.dumps(ASK))
        self.assertIn("python3 '/si d/scripts/arch_brief.py' --check --repo '/my r' --commit", b)
        self.assertIn('py "/si d/scripts/arch_brief.py" --check --repo "/my r" --commit', b)

    def test_preview_confirm_gated(self):
        """R1: preview shows recipient + text; confirm disabled while the recipient is not logged in."""
        cands = [{"sid": "s1234567890", "id": "mb", "login": True, "dir": "r", "g": 0}, {"sid": "s2", "id": "", "login": False, "dir": "x", "g": 0}]
        ok, off = run("[archBriefReqHtml({p: '/r', sid: 's1234567890'}, '/r', '/sid', %s, %s), archBriefReqHtml({p: '/r', sid: 's2'}, '/r', '/sid', %s, %s)]"
                      % (json.dumps(cands), json.dumps(ASK), json.dumps(cands), json.dumps(ASK)))
        self.assertIn("data-arbs", ok)
        self.assertIn("r · s1234567 · mb", ok)
        self.assertIn("--by s1234567890", ok)
        self.assertIn("Language: Korean — ", ok)   # preview uses the viewer LANG ('ko' here), as the sent body does
        self.assertIn("data-arbgo>", ok)
        self.assertIn("data-arbgo disabled", off)

    def test_r1_send_only_from_confirm(self):
        """R1/R2: pressing «Ask» only opens the preview; confirm posts once to the owning session with plreq brief-ask,
        a body free of other session fields; a late result after a project switch leaves the new preview alone."""
        js = PRE + "\n" + "\n".join(js_fn(n) for n in FNS) + "\n" + _top("const q = ARCH.breq;", "async function archBriefSend") + """
let BRIEFRUN = {}, PLREQ = {}, POSTS = [], strMode = 'arch', strOn = ['/r'], SESS = %s, release = null;
const ARCH = {xm: '/r', breq: null, req: null, msg: '', cache: {'/r': %s}};
function paintStruct(){} function kbHold(){} function archReqLast(){ return null; } function archReqLive(){ return false; }
function postJSON(u, b){ POSTS.push([u, b]); return new Promise(r => { release = () => r({ok: true}); }); }
const L = {}; global.document = {addEventListener: (k, f) => { (L[k] = L[k] || []).push(f); }, querySelectorAll: () => []};
""" % (json.dumps([OTHER, OWN]), json.dumps(dict(MAP, ask=ASK))) + _top("[data-arxa]", "document.addEventListener('click'") + """
const click = sel => L.click.forEach(f => f({target: {closest: s => s.split(',').some(x => x === sel || x === '.archtab') ? {} : null}}));
click('[data-arxa]');
const afterAsk = POSTS.length, q = JSON.parse(JSON.stringify(ARCH.breq));
(async () => {
  const p = archBriefSend(); ARCH.breq = {p: '/other', sid: 'x', busy: false}; release(); await p;
  process.stdout.write(JSON.stringify([afterAsk, q, POSTS, ARCH.breq]));
})();"""
        r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        after_ask, q, posts, breq = json.loads(r.stdout)
        self.assertEqual(after_ask, 0)                                   # the menu click sends nothing
        self.assertEqual(q, {"p": "/r", "sid": OWN["sid"], "busy": False})   # owning session picked, not the other one
        self.assertEqual(len(posts), 1)
        u, b = posts[0]
        self.assertEqual(u, "/api/dm")
        self.assertEqual((b["to"], b["sid"], b["thread"]), ("mb-own", OWN["sid"], "pipeline:brief-ask"))
        self.assertEqual(b["plreq"], {"kind": "req", "pipeline": "brief-ask", "repo": "/r"})
        self.assertIn("--by " + OWN["sid"], b["body"])
        for v in ("opus-x", "mb-own", "mb-oth", OTHER["sid"], "sonnet-y"):
            self.assertNotIn(v, b["body"])
        self.assertEqual(breq, {"p": "/other", "sid": "x", "busy": False})   # late result dropped

    def test_busy_on_sent_and_sig_tracks_record(self):
        """R1: a sent brief-ask record already blocks «Ask the session to draw»; the tick signature moves with the record state/stage."""
        js = PRE + "\nlet BRIEFRUN = {}; const ARCH = {xm: '', breq: null, req: null}; let PLREQ = {};\n" + "\n".join(js_fn(n) for n in (
            "archBriefBusy", "archXSig", "archReqMs", "archReqRows", "archReqLive", "archReqLast")) + """
const ARCH_REQ_KEEP_MS = 3600000, ARCH_REQ_LBL = {sent: 1, run: 1, stopping: 1, stopped: 1, done: 1, gone: 1};
const R = st => ({'/r': [{id: 'm1', pipeline: 'brief-ask', state: st, stage: '', at: Date.now()}]});
const b0 = archBriefBusy('/r'), s0 = archXSig('/r');
PLREQ = R('sent'); const b1 = archBriefBusy('/r'), s1 = archXSig('/r');
PLREQ = R('run'); const s2 = archXSig('/r');
PLREQ = R('done'); const b3 = archBriefBusy('/r');
process.stdout.write(JSON.stringify([b0, b1, b3, s0 !== s1, s1 !== s2]));"""
        r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        self.assertEqual(json.loads(r.stdout), [False, True, False, True, True])

    def test_arch_brief_pipeline_record_keeps_row_and_stop(self):
        """A live arch-brief pipeline-file request (Pipelines «Run», or sent before brief-ask) keeps its row + «Stop» and blocks a new ask."""
        js = PRE + "\nlet BRIEFRUN = {}; const ARCH = {xm: '', breq: null, req: null, pstop: null, cache: {}}; let PLREQ = {};\n" + "\n".join(js_fn(n) for n in (
            "archBriefPl", "archBriefBusy", "archXSig", "archBriefSlot", "archReqMs", "archReqRows", "archReqLive", "archReqLast", "archReqStopOk",
            "archReqWho", "archReqRowHtml", "archReqSlot")) + """
const ARCH_REQ_KEEP_MS = 3600000, ARCH_REQ_LBL = {sent: 'Sent', run: 'Running', stopping: 'Stopping', stopped: 'Stopped', done: 'Done', gone: 'No session'};
const now = Date.now(), row = (id, pl, st, at) => ({id, pipeline: pl, state: st, stage: 'draw', at, to: 'mb', sid: 'sid12345678'});
PLREQ = {'/r': [row('b1', 'arch-brief', 'run', now - 60000)]};
const live = [archBriefPl('/r'), archBriefBusy('/r'), archBriefSlot('/r', '', [])];
PLREQ = {'/r': [row('b1', 'arch-brief', 'run', now - 60000), row('a1', 'brief-ask', 'done', now)]};
const liveOverDone = archBriefPl('/r');
PLREQ = {'/r': [row('b1', 'arch-brief', 'done', now - 60000), row('a1', 'brief-ask', 'done', now)]};
const newer = [archBriefPl('/r'), archBriefBusy('/r')];
PLREQ = {};
process.stdout.write(JSON.stringify([live, liveOverDone, newer, archBriefPl('/r')]));"""
        r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        live, live_over_done, newer, empty = json.loads(r.stdout)
        self.assertEqual(live[:2], ["arch-brief", True])
        self.assertIn('data-arstop="b1"', live[2])
        self.assertEqual(live_over_done, "arch-brief")
        self.assertEqual(newer, ["brief-ask", False])
        self.assertEqual(empty, "brief-ask")

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

    def test_r3_done_row_refetches_once(self):
        """R3: a brief-ask row going sent -> done re-fetches /api/arch once; gone never fires and never revives; loading retries."""
        js = PRE + "\n" + "\n".join(js_fn(n) for n in ("archAskEdge", "archAskPoll")) + """
let ARCH_ASK_SEEN = {}; const ARCH = {cache: {'/a': {}, '/b': {}}, load: {}}, F = [];
function archFetch(p, force){ F.push([p, force]); }
const row = (id, st, pl) => ({id, pipeline: pl || 'brief-ask', state: st});
const out = [];
archAskPoll({'/a': [row('x1', 'sent'), row('m1', 'sent', 'arch-map')], '/b': [row('y1', 'sent')]}); out.push(F.length);
archAskPoll({'/a': [row('x1', 'done'), row('m1', 'done', 'arch-map')], '/b': [row('y1', 'gone')]}); out.push(F.slice());
archAskPoll({'/a': [row('x1', 'done')], '/b': [row('y1', 'sent')]}); out.push(F.length, ARCH_ASK_SEEN.y1);
archAskPoll({'/b': [row('y1', 'done')]}); out.push(F.length);
ARCH.load['/a'] = 1; archAskPoll({'/a': [row('x2', 'sent')]}); archAskPoll({'/a': [row('x2', 'done')]}); out.push(F.length);
delete ARCH.load['/a']; archAskPoll({'/a': [row('x2', 'done')]}); out.push(F.slice(-1));
process.stdout.write(JSON.stringify(out));"""
        r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        self.assertEqual(json.loads(r.stdout), [0, [["/a", True]], 1, "gone", 1, 1, [["/a", True]]])

    def test_preview_survives_repaint(self):
        """Poll rebuilds keep the preview and its pick; an ended pick moves to the next owning session; another project or a live
        record closes an idle preview."""
        js = PRE + "\n" + "\n".join(js_fn(n) for n in FNS + ("archXFix",)) + """
let BRIEFRUN = {}, SESS = []; const ARCH = {xm: '/r', breq: {p: '/r', sid: 's2', busy: false}, cache: {'/r': %s}};
const c = (sid, g) => ({sid, g}), out = [];
archXFix('/r', [c('s1', 0), c('s2', 0), c('o', 2)]); out.push(ARCH.breq && ARCH.breq.sid);
archXFix('/r', [c('o', 2), c('s1', 0)]); out.push(ARCH.breq && ARCH.breq.sid);
BRIEFRUN = {'/r': 1}; archXFix('/r', [c('s1', 0)]); out.push(ARCH.breq);
BRIEFRUN = {}; ARCH.breq = {p: '/r', sid: 's1', busy: false}; archXFix('/q', []); out.push(ARCH.breq, ARCH.xm);
process.stdout.write(JSON.stringify(out));""" % json.dumps(dict(MAP, ask=ASK))
        r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        self.assertEqual(json.loads(r.stdout), ["s2", "s1", None, None, ""])


if __name__ == "__main__":
    unittest.main()
