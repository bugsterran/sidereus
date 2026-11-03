"""Session identity row groups (40ba sessIdRow): chips sit in [identity][usage][work][actions] groups (R1),
usage/work are always emitted as placeholders (R2), «To-do n» never forms a group alone and sessFit drops only
size · cost · model (R3). Pure functions under node with stubs."""
import glob
import json
import os
import re
from html.parser import HTMLParser
import shutil
import subprocess
import unittest

from tests._load import ROOT, js_fn
from tests.test_saver_quota_js import jconst
from tests._node import node_e

PRE = r"""
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const T = s => s;
const TV = o => o.msg.replace(/\{(\w+)\}/g, (_, k) => o.vars[k]);
function platName(k){ return String(k); }
function aiLogo(p){ return '<i class=ailg></i>'; }
function sessBranchHtml(){ return ''; } function acctChip(){ return ''; }
function extTid(){ return ''; } function sz(n){ return n + 'B'; } function money(n){ return '$' + n; }
function fmtTok(n){ return String(n); } function extCostTip(){ return ''; }
function resumeCmd(){ return 'rc'; }
function termBtnHtml(x){ return x.term ? '<button class="stm" data-term="s">›_</button>' : ''; }
function stodoChip(x){ return x.todo ? '<span class="stdc" data-todo="k">To-do 2</span>' : ''; }
"""
FNS = "\n".join(js_fn(n) for n in ("sessIdRow", "sessGitChip", "sessUsage", "extTokChip", "sessWorkBadges",
                                    "sessActs", "sessPlChip", "sessFit")) + "\n" + jconst("SX_DROP") + "\n"
GROUPS = ("sxid", "sxus", "sxwk", "sxac")


def run(body):
    r = subprocess.run(node_e(PRE + FNS + body), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def group_of(h, needle):
    """Group class whose span contains `needle` (groups are siblings, so the last one opened before it)."""
    i = h.index(needle)
    seen = [(h.find('class="sxg ' + g + '"'), g) for g in GROUPS]
    return max((p, g) for p, g in seen if 0 <= p < i)[1]


def parents(h):
    """{class: parent group class} for every .sxg/.sxtl span (actual nesting, not text order)."""
    out, stack = {}, []

    class P(HTMLParser):
        def handle_starttag(self, tag, attrs):
            c = (dict(attrs).get("class") or "").split()
            name = c[1] if c[:1] == ["sxg"] else ("sxtl" if c == ["sxtl"] else (c[0] if c[:1] == ["sxgs"] else None))
            if name and name not in out:
                out[name] = next((s for s in reversed(stack) if s), None)
            stack.append(name)

        def handle_endtag(self, tag):
            stack.pop()
    P().feed(h)
    return out


FULL = ("{project: 'p', cwd: '/r', sid: 'abcdefghij', state: 'wait', ctx: 120000, win: 1000000, bytes: 10,"
        " cost: 2, model: 'm1', err: 1, wreck: 1, term: 1, todo: 1, plrun: [{name: 'pl', cur: 'impl'}]}")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SessRowGroups(unittest.TestCase):
    def test_r1_chips_in_their_group(self):
        h = run("console.log(JSON.stringify(sessIdRow(" + FULL + ")));")
        self.assertEqual(group_of(h, "class=sp"), "sxid")
        self.assertEqual(group_of(h, 'class="sg hit"'), "sxid")       # no-branch diff chip stays with identity
        for c in ('class="sc', 'class="sz', "class=sk", "class=sm"):
            self.assertEqual(group_of(h, c), "sxus", c)
        for c in ("class=se", "class=swr", 'class="spl splr"', 'class="stdc"'):
            self.assertEqual(group_of(h, c), "sxwk", c)
        self.assertEqual(group_of(h, "class=srz"), "sxac")
        self.assertEqual(group_of(h, 'class="stm"'), "sxac")
        self.assertLess(h.index('class="spl splr"'), h.index('class="stdc"'))   # pipeline chip, then «To-do n»

    def test_r2_placeholders_keep_columns(self):
        h = run("console.log(JSON.stringify(sessIdRow({project: 'p', state: 'done'})));")
        for g in ("sxid", "sxus", "sxwk"):
            self.assertIn('class="sxg ' + g + '"', h)
        self.assertIn('<span class="sxg sxus"></span><span class="sxg sxwk"></span>', h)
        self.assertNotIn("sxac", h)                                       # trailing empty action group omitted

    def test_r3_todo_never_alone(self):
        a, b = run("console.log(JSON.stringify([sessIdRow({project: 'p', state: 'wait', model: 'm1', todo: 1}),"
                   " sessIdRow({project: 'p', state: 'wait', todo: 1})]));")
        self.assertEqual(group_of(a, 'class="stdc"'), "sxus")             # joins usage when work is empty
        self.assertIn('<span class="sxg sxwk"></span>', a)
        self.assertEqual(group_of(b, 'class="stdc"'), "sxid")             # no usage either: joins identity

    def test_r3_actions_glued_to_last_group(self):
        a, b, c = run("console.log(JSON.stringify([sessIdRow(" + FULL + "),"
                      " sessIdRow({project: 'p', cwd: '/r', sid: 'abcdefghij', state: 'wait', model: 'm1', term: 1}),"
                      " sessIdRow({project: 'p', cwd: '/r', sid: 'abcdefghij', state: 'done'})]));")
        self.assertEqual(parents(a)["sxac"], "sxwk")                     # with work chips: inside the work group
        self.assertEqual(parents(b)["sxtl"], "sxus")                     # no work chips: glued to usage
        self.assertEqual(parents(b)["sxac"], "sxtl")
        self.assertEqual(parents(c)["sxtl"], "sxid")                     # nothing else: glued to identity
        for h in (a, b, c):
            self.assertNotEqual(parents(h)["sxac"], "sxgs")              # never a top-level group that can wrap alone

    def test_r3_drop_order(self):
        self.assertEqual(run("console.log(JSON.stringify(SX_DROP));"), ["sz", "sk", "sm"])


def fake(w, sp="null"):
    """Stub element: subpixel getBoundingClientRect width, integer-rounded offsetWidth (as browsers do)."""
    return ("{getBoundingClientRect: () => ({width: %s}), offsetWidth: Math.round(%s), offsetTop: 0, offsetHeight: 16,"
            " firstChild: 1, querySelector: s => s === '.sp' ? %s : null}" % (w, w, sp))


def fit(idw, gs=735, spw=None):
    return run(r"""const window = {};
const props = {};
const mk = () => { const id = %s, us = %s, l = %s, gs = {clientWidth: %d};
  return {clientWidth: 791, querySelector: s => ({'.sxid': id, '.sxus': us, '.sxl': l, '.sxgs': gs})[s] || null,
          querySelectorAll: () => [id, us]}; };
const rows = [mk(), mk()];
const box = {clientWidth: 791, style: {setProperty: (k, v) => { props[k] = v; }, removeProperty: k => { delete props[k]; }},
             classList: {add() {}, remove() {}}, querySelectorAll: () => rows};
sessFit(box);
console.log(JSON.stringify(props));
""" % (fake(idw, fake(spw) if spw else "null"), fake(120.2), fake(18.6), gs))


def px(v):
    return int(v[:-2])


@unittest.skipUnless(shutil.which("node"), "node not installed")
class SessFitWidths(unittest.TestCase):
    """sessFit measures at subpixel precision and rounds up: 225.4 px must not become a 225 px column."""
    def test_fractional_width_rounds_up(self):
        p = fit(225.4)
        self.assertGreaterEqual(px(p["--sxidw"]), 226)
        self.assertGreaterEqual(px(p["--sxusw"]), 121)
        self.assertGreaterEqual(px(p["--sxlead"]), 19)

    def test_cap_still_applies(self):
        self.assertLessEqual(px(fit(500.0, spw=300.0)["--sxidw"]), 332)   # 45% of 735 = 330.75 > needed 296

    def test_cap_floor_is_min_needed(self):
        # cap 45% of 413 = 186; identity 260 with a 147px name -> needs 260 - (147 - 96) = 209 with the name ellipsized
        v = px(fit(260.0, gs=413, spw=147.0)["--sxidw"])
        self.assertGreaterEqual(v, 209)
        self.assertLess(v, 260)
        self.assertLessEqual(px(fit(260.0, gs=413, spw=60.0)["--sxidw"]), 262)   # short name: never above natural


class SxidNoWrap(unittest.TestCase):
    def test_no_wrap_rule_for_sxid(self):
        for f in sorted(glob.glob(os.path.join(ROOT, "web", "css", "*.css"))):
            with open(f, encoding="utf-8") as fh:
                css = re.sub(r"/\*.*?\*/", "", fh.read(), flags=re.S)
            for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
                # rules whose subject is .sxid itself (optionally with :has()/:not() pseudo-classes)
                if any(re.search(r"\.sxid(:[\w-]+(\([^)]*\))?)*$", s.strip()) for s in sel.split(",")):
                    self.assertNotRegex(body, r"flex-wrap\s*:\s*wrap", "%s: %s" % (os.path.basename(f), sel.strip()))

    def test_name_ellipsizes_with_floor(self):
        with open(os.path.join(ROOT, "web", "css", "60-sessions.css"), encoding="utf-8") as fh:
            m = re.search(r"\.sx \.sxid > \.sp\{([^}]*)\}", fh.read())
        self.assertIsNotNone(m)
        for d in ("min-width:96px", "overflow:hidden", "text-overflow:ellipsis"):
            self.assertIn(d, m.group(1))


if __name__ == "__main__":
    unittest.main()
