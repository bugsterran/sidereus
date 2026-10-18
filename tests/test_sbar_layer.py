"""Status-bar layer (60b-sbar-layer.js): per-account quota rows, sessions line, last-hour failures, bar wiring."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests.test_saver_quota_js import i18n, jconst
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STUBS = """
var document = {getElementById: () => null};
let QLAST = null, ACCTS = [], CONN = {};
let MAIN = '';
const UIS = {getItem: () => MAIN};
const connStaleNote = () => '';
const acctCls = l => 'acc-' + l;
const sesCount = () => ({open: 7, work: 3, need: 2, idle: 2, think: 1, tool: 1, subw: 1, oth: 0});
let PUTS = [], REDRAW = 0, PAINT = 0;
const mpPut = (k, v) => { PUTS.push([k, v]); MAIN = v || ''; return true; };
const mpMainAcctRedraw = () => { REDRAW++; };
const sblPaint = () => { PAINT++; };
let BURN = null, BURNM_B = null;
const burnFor = () => BURNM_B;
const fmtTok = n => (n / 1e6).toFixed(1) + 'M';
"""
FNS = ("fmtPct", "acctList", "mainAcct", "mainAcctOk", "sblAccRows", "sblHtml", "sbPctCls", "sblMakeMain",
       "sblEst", "sblEstHtml", "burnEst", "burnEstTip", "burnWkEst")

N = "Date.parse('2030-01-01T00:00:00Z')"
QUOTA = """
const N = %s;
QLAST = {q: {five_hour: {pct: 38, resets_at: new Date(N + 9e6).toISOString()}, seven_day: {pct: 33},
             accounts: [{label: '<w>&', five_hour: {pct: 90, resets_at: (N + 36e5) / 1000}, seven_day: {pct: 20}},
                        {label: 'gone'}]}};
ACCTS = [{label: 'me', primary: true}, {label: '<w>&'}, {label: 'gone'}];
""" % N


def read(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SbarLayer(unittest.TestCase):
    def run_js(self, body):
        src = STUBS + i18n() + "\n" + jconst("esc") + "\n" \
            + "\n".join(js_fn(f) for f in FNS) + "\n" + body
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, env=dict(os.environ, TZ="UTC"), encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        return json.loads(r.stdout)

    def test_rows_per_account(self):
        # R2: primary first, one row per account, left = 100 - pct, missing pct -> '—', exactly one main mark.
        rows, main = self.run_js(QUOTA + """
const a = sblAccRows(QLAST.q, acctList(), mainAcct());
MAIN = '<w>&';
process.stdout.write(JSON.stringify([a, sblAccRows(QLAST.q, acctList(), mainAcct())]));
""")
        self.assertEqual([r["label"] for r in rows], ["me", "<w>&", "gone"])
        self.assertEqual([(r["l5"], r["l7"]) for r in rows], [("62%", "67%"), ("10%", "80%"), ("—", "—")])
        self.assertEqual([r["main"] for r in rows], [True, False, False])       # no main set -> primary
        self.assertEqual([r["main"] for r in main], [False, True, False])
        self.assertEqual(self.run_js("process.stdout.write(JSON.stringify(sblAccRows(null, null, '')));"), [])

    def test_html_accounts_escaped(self):
        # R2: both labels escaped, reset times shown (ISO and epoch seconds), unknown reset '—'.
        h = self.run_js(QUOTA + "process.stdout.write(JSON.stringify(sblHtml(N)));")
        self.assertIn(">me<em class=sbl-badge>", h)   # main row: name then the «Main» badge
        self.assertIn("&lt;w&gt;&amp;</span>", h)
        self.assertNotIn("<w>", h)
        self.assertIn("02:30</small>", h)      # N + 2.5h, UTC
        self.assertIn("01:00</small>", h)      # N + 1h from epoch seconds
        self.assertEqual(h.count("class=sbl-main"), 1)
        self.assertIn("data-sdrw>할당량 상세</button>", h)

    def test_html_sessions_no_failures(self):
        # sesCount numbers; the last-hour failures section is gone from the layer.
        h = self.run_js(QUOTA + "process.stdout.write(JSON.stringify(sblHtml(N)));")
        self.assertRegex(h, r"열린 세션 <b>7</b> · 작업 중 3 · 유휴 2 · 나를 기다림 <b>2</b>")
        for gone in ("sbl-fail", "sbl-kinds", "실패"):
            self.assertNotIn(gone, h)

    def test_make_main_switch(self):
        # R1: a non-main row stores its label (same UIS key as Preferences) and repaints; current main and junk do nothing.
        r = self.run_js(QUOTA + """
sblMakeMain('<w>&'); const a = [PUTS.slice(), REDRAW, PAINT];
sblMakeMain('<w>&'); sblMakeMain('nope'); const b = [PUTS.length, REDRAW];
sblMakeMain(''); const c = PUTS[PUTS.length - 1];
process.stdout.write(JSON.stringify([a, b, c]));
""")
        self.assertEqual(r[0], [[["mbMainAcct", "<w>&"]], 1, 0])   # buildSbar (in the redraw) repaints the layer
        self.assertEqual(r[1], [1, 1])                  # current main no-op · junk refused
        self.assertEqual(r[2], ["mbMainAcct", None])    # primary row clears the key

    def test_rows_switchable_and_coloured(self):
        # R1/R3: only non-main rows are controls; % cells use the bar's classes.
        h = self.run_js(QUOTA + "process.stdout.write(JSON.stringify(sblHtml(N)));")
        self.assertEqual(h.count("role=button tabindex=0"), 2)
        self.assertIn('data-acct="&lt;w&gt;&amp;" title="메인 계정으로 지정"', h)
        self.assertNotIn('data-acct=""', h)            # primary is main -> not a control
        self.assertIn("<b class=sbok>62%</b>", h)
        self.assertIn("<b class=sberr>10%</b>", h)
        self.assertIn("<b>—</b>", h)                   # unknown % stays uncoloured

    def test_main_badge_and_hint(self):
        # R1: the main row has the «Main» badge and no hint; R2: every switchable row carries the hint element.
        h = self.run_js(QUOTA + "process.stdout.write(JSON.stringify(sblHtml(N)));")
        rows = re.findall(r"<div class=\"sbl-acc(?! sbl-hd)[^>]*>.*?</div>", h)
        main = [r for r in rows if "sbl-main" in r]
        self.assertEqual(len(main), 1)
        self.assertIn("<em class=sbl-badge>메인</em>", main[0])
        self.assertNotIn("sbl-hint", main[0])
        sw = [r for r in rows if "sbl-sw" in r]
        self.assertEqual(len(sw), 2)
        for r in sw:
            self.assertIn("<em class=sbl-hint aria-hidden=true>메인으로</em>", r)

    def test_token_estimate_per_row(self):
        # Primary row from BURN, the non-primary main row from its own body; low est says so in the tooltip.
        low = "{ok: true, cur: {now_pct: 90}, est: {low: true, h5_left: 7e6, wk_left: 1.6e8, wk_used: 4e7}}"
        h = self.run_js(QUOTA + "MAIN = '<w>&'; BURNM_B = " + low + ";"
                        "BURN = {ok: true, cur: {now_pct: 38, used_local: 1e6}, est: {h5_left: 2.5e7, h5_n: 5, h5_src: 'med'}};"
                        "process.stdout.write(JSON.stringify(sblHtml(N)));")
        self.assertIn(">≈ 25.0M 남음</small>", h)          # primary 5h
        self.assertIn(">≈ 7.0M 남음</small>", h)           # main account 5h (own window, low)
        self.assertIn(">≈ 160.0M 남음</small>", h)         # main account 7d
        self.assertEqual(h.count("class=sbl-est"), 3)     # no 7d est for the primary; none for the third row
        self.assertIn("정확도 낮음", h)
        h2 = self.run_js(QUOTA + "BURNM_B = " + low + "; process.stdout.write(JSON.stringify(sblHtml(N)));")
        self.assertNotIn("sbl-est", h2)                   # not main: its body is not fetched -> nothing

    def test_single_account_not_switchable(self):
        # Switchable rows need 2+ signed-in accounts.
        h = self.run_js(QUOTA + "ACCTS = [{label: 'me', primary: true}]; QLAST.q.accounts = [];"
                        "process.stdout.write(JSON.stringify(sblHtml(N)));")
        self.assertNotIn("sbl-sw", h)
        self.assertNotIn("sbl-hint", h)


class SbarLayerWiring(unittest.TestCase):
    def test_bar_opens_layer(self):
        # R1: bar click/Enter -> layer, registered for outside-click/Esc close, repainted only while open.
        sb, lay = read("web/js/60-statusbar.js"), read("web/js/60b-sbar-layer.js")
        self.assertIn("bar.onclick = () => sblToggle();", sb)
        self.assertRegex(sb, r"bar\.onkeydown = .*'Enter'.*sblToggle\(\)")
        self.assertNotRegex(sb, r"bar\.onclick = .*sdrwSet")
        self.assertIn("if(popIsOpen('sblpop')) sblPaint();", js_fn("buildSbar"))
        self.assertIn("popReg('sblpop', '#sbar, #sblpop', sblClose);", lay)
        self.assertNotIn("FAIL1H", read("web/js/95-poll.js") + lay)

    def test_hint_css_only_on_hover_focus(self):
        # R2/R3: hint hidden by default, shown only on :hover/:focus-visible, absolutely positioned (no layout shift).
        css = read("web/css/90-main-ui.css")
        base = re.search(r"\.sbl-sw > \.sbl-hint\{([^}]*)\}", css).group(1)
        self.assertIn("visibility:hidden", base)
        self.assertIn("position:absolute", base)
        self.assertIn(".sbl-sw:is(:hover,:focus-visible) > .sbl-hint{visibility:visible}", css)
        self.assertEqual(len(re.findall(r"sbl-hint\{[^}]*visibility:visible", css)), 1)
        self.assertNotRegex(read("web/js/60b-sbar-layer.js"), r"mouseenter|mouseover|onmouse")

    def test_columns_shared_grid(self):
        # Header and account rows sit in one grid (rows = subgrid), so badge / reset text width never shifts the % columns.
        css, lay = read("web/css/90-main-ui.css"), read("web/js/60b-sbar-layer.js")
        self.assertIn("'<div class=sbl-tbl><div class=\"sbl-acc sbl-hd\">", lay)
        tbl = re.search(r"\.sblpop \.sbl-tbl\{([^}]*)\}", css).group(1)
        self.assertIn("display:grid", tbl)
        self.assertIn("grid-template-columns:", tbl)
        acc = re.search(r"\.sblpop \.sbl-acc\{([^}]*)\}", css).group(1)
        self.assertIn("grid-template-columns:subgrid", acc)
        self.assertIn("grid-column:1/-1", acc)
        self.assertIn(".sbl-acc > :not(:first-child){text-align:right}", css)

    def test_main_row_blue(self):
        # Main row name, badge and dot use the theme info blue; non-main rows keep --acc.
        css, lay = read("web/css/90-main-ui.css"), read("web/js/60b-sbar-layer.js")
        self.assertIn("(r.main ? ' sbl-me' : '')", lay)
        for sel, prop in ((r"\.sbl-me > :first-child", "color"), (r"\.sbl-me \.sbl-badge", "color"), (r"\.sbl-me \.sbl-main", "background")):
            body = re.search(sel + r"\{([^}]*)\}", css).group(1)
            self.assertIn(prop + ":var(--nx-info)", body)
            self.assertNotIn("--acc", body)
        self.assertIn(".sbl-acc > :first-child{color:var(--acc", css)


if __name__ == "__main__":
    unittest.main()
