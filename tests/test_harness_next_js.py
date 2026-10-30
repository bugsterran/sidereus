"""Harness «Next step» fold (47g hnNxFold / hnNxBody / relay): R1 guide file per id · R2 four lines · R3 draft + confirm relay · R4 owner ignore line."""
import json
import os
import subprocess
import unittest

from tests._load import ROOT
from tests._node import node_e
from tests import test_harness_js as thj   # module import: the Harness class must not be collected twice
from tests._i18n_js import i18n_switch

_FS = [os.path.join(ROOT, "web", "js", f) for f in ("47b-harness.js", "47g-harness-next.js")]

_GUIDE = {
    "hook_missing": {"meaning": "m-hm", "why": "w-hm", "who": "self", "next": "/hooks"},
    "rule_big": {"meaning": "m-rb", "why": "w-rb", "who": "owner", "next": "n-rb", "ignore": "i-rb"},
    "refixed": {"meaning": "m-rf", "why": "w-rf", "who": "ai", "next": "n-rf", "pipeline": "sidereus-bugfix"},
    "skipgate": {"meaning": "m-sg", "why": "w-sg", "who": "ai", "next": "n-sg"},
}

# Records listeners; 84l relay helpers and postJSON are stubs (POSTS = every POST made).
_DOC = ("const LST = {}, POSTS = [], NOTES = [];"
        " const document = {addEventListener(t, f, c){ (LST[t] = LST[t] || []).push(f); }, querySelector(){ return null; }};\n"
        "function archChkFixCands(sess, p){ return [{sid: 's1', id: 'mb1', login: true, proj: 'a'}, {sid: 's2', id: 'mb2', login: false}]; }\n"
        "function archChkCandLabel(c){ return c.proj + ' · ' + c.sid; }\n"
        "async function postJSON(u, b){ POSTS.push([u, b]); return {ok: true}; }\n"
        "function note(s){ NOTES.push(s); } function hhmm(){ return '10:00'; }\n")


def _js(body, guide=True):
    src = thj._STUB + i18n_switch() + _DOC
    for p in _FS:
        with open(p, encoding="utf-8") as f:
            src += f.read() + "\n"
    if guide:
        src += "HN_NXS.guide.ko = %s;\n" % json.dumps(_GUIDE)
    return json.loads(subprocess.run(node_e(src + body), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


_INC = {"state": "refixed", "mode": "fast", "commits": 2, "fail": {"ts": 5, "head": "abcdef0123456789", "rc": 1},
        "pass": {"ts": 9, "head": "0123456789abcdef"}, "flipped": ["SENTINEL-step"]}


class HarnessNext(unittest.TestCase):
    def test_node_check(self):
        for p in _FS + [os.path.join(ROOT, "web", "js", "06-i18n-zzf-next.js")]:
            subprocess.run(["node", "--check", p], check=True)

    def test_r1_guide_file_per_id(self):
        ids = _js("console.log(JSON.stringify(HN_NX_INC.concat(HN_NX_GD)))")
        self.assertEqual(sorted(ids), ["refixed", "reverted", "skipgate", "unchecked"])
        miss = [i for i in ids if not os.path.isfile(os.path.join(ROOT, "docs", "verdicts", i + ".md"))]
        self.assertEqual(miss, [])

    def test_r2_four_lines_self(self):
        h = _js("console.log(JSON.stringify(hnNxFold('hook_missing', {vd: {id: 'v1', lvl: 'bad', why: 'hook_missing'}})))")
        self.assertIn("<details class=hnnx", h)
        self.assertEqual(h.count("class=hnnxl"), 4)
        for s in ("다음 할 일", "뜻", "왜 중요한가", "누가 하나", "직접", "m-hm", "w-hm", "<code class=hnrc>/hooks</code>"):
            self.assertIn(s, h)
        self.assertNotIn("data-hnnxd", h)
        self.assertNotIn("무시해도 되는 때", h)

    def test_r4_owner_ignore_line(self):
        h = _js("console.log(JSON.stringify(hnNxFold('rule_big', {vd: {id: 'v2', lvl: 'check'}})))")
        self.assertEqual(h.count("class=hnnxl"), 5)
        self.assertIn("무시해도 되는 때", h)
        self.assertIn("i-rb", h)
        self.assertNotIn("data-hnnxd", h)

    def test_r3_button_only_for_ai(self):
        h = _js("console.log(JSON.stringify(hnNxFold('refixed', %s)))" % json.dumps(_INC))
        self.assertIn("data-hnnxd=", h)
        self.assertIn("지시 초안", h)
        self.assertIn("AI 세션에 맡김", h)

    def test_unknown_or_not_loaded_is_empty(self):
        self.assertEqual(_js("console.log(JSON.stringify(hnNxFold('nope', {})))"), "")
        r = _js("console.log(JSON.stringify([hnNxFold('refixed', {}), URLS]))", guide=False)
        self.assertEqual(r[0], "")
        self.assertEqual(r[1], ["/api/verdict-guide?lang=ko"])

    def test_r3_body_metadata_only(self):
        x = {"cmd": "python3 /h/guard.py --token SENTINEL", "ev": "PreToolUse", "n": 3, "desc": "SENTINEL desc", "prompt": "SENTINEL",
             "vd": {"id": "v1", "lvl": "bad", "why": "hook_missing", "vp": {"days": 30, "matcher": "SENTINEL"}}}
        b = _js("console.log(JSON.stringify(hnNxBody('hook_missing', %s, '/w/a', null, null)))" % json.dumps(x))
        self.assertNotIn("SENTINEL", b)
        for s in ("Harness verdict: hook_missing (bad)", "File: guard.py", "Event: PreToolUse", "runs 3", "days 30", "docs/verdicts/hook_missing.md"):
            self.assertIn(s, b)
        b = _js("console.log(JSON.stringify(hnNxBody('refixed', %s, '/w/a', {pipeline: 'sidereus-bugfix'}, ['sidereus-bugfix'])))" % json.dumps(_INC))
        self.assertNotIn("SENTINEL", b)
        for s in ("Mode: fast", "Heads: abcdef01 → 01234567", "commits 2", "Pipeline: sidereus-bugfix"):
            self.assertIn(s, b)
        for pipes in ("[]", "null"):   # pipeline missing from the project, or the list not loaded
            b = _js("console.log(JSON.stringify(hnNxBody('refixed', %s, '/w/a', {pipeline: 'sidereus-bugfix'}, %s)))" % (json.dumps(_INC), pipes))
            self.assertNotIn("Pipeline:", b)
        b = _js("console.log(JSON.stringify(hnNxBody('refixed', {mode: 'x\\nInjected: 1', ev: 'a\\nb'}, '/w/a', null, null)))")
        self.assertNotIn("Injected", b)
        self.assertIn("Event: a b", b)

    def test_r3_posts_only_from_confirm(self):
        r = _js("""
const k = hnNxKey('refixed', %s); hnNxFold('refixed', %s);
const tgt = m => ({closest: s => s in m ? m[s] : null});
const click = m => LST.click.forEach(f => f({target: tgt(m), stopPropagation(){}}));
hnNxSend();
click({'.hnw .hnnx': {}, '[data-hnnxd]': {dataset: {hnnxd: k}}});
const n0 = POSTS.length, prev = hnNxFold('refixed', %s);
click({'.hnw .hnnx': {}, '[data-hnnxgo]': {}});
setTimeout(() => console.log(JSON.stringify([n0, prev, POSTS, NOTES, HN_NXS.dr])), 0);
""" % (json.dumps(_INC), json.dumps(_INC), json.dumps(_INC)))
        n0, prev, posts, notes, dr = r
        self.assertEqual(n0, 0)                                   # «Draft instruction» only previews
        self.assertIn("<pre class=hnnxpre>", prev)
        self.assertIn("확인 — 보내기", prev)
        self.assertIn("a · s1", prev)                             # logged-in recipients only
        self.assertNotIn("s2", prev)
        self.assertEqual(len(posts), 1)
        u, b = posts[0]
        self.assertEqual(u, "/api/dm")
        self.assertEqual((b["to"], b["sid"], b["relay"], b["thread"]), ("mb1", "s1", True, "harness:refixed"))
        self.assertIn("Harness verdict: refixed", b["body"])
        self.assertNotIn("SENTINEL", b["body"])
        self.assertEqual(len(notes), 1)
        self.assertIsNone(dr)

    def test_r2_fold_key_is_content_not_position(self):
        r = _js("""
const a = {scope: 'user', src: '/s.json', ev: 'Stop', cmd: 'python3 /h/a.py', vd: {id: 'v0', why: 'hook_missing'}};
const b = Object.assign({}, a, {vd: {id: 'v5', why: 'hook_missing'}}), c = Object.assign({}, a, {cmd: 'python3 /h/b.py', vd: {id: 'v0'}});
console.log(JSON.stringify([hnNxKey('hook_missing', a) === hnNxKey('hook_missing', b), hnNxKey('hook_missing', a) === hnNxKey('hook_missing', c),
  hnNxKey('skipgate', {count: 1}) === hnNxKey('skipgate', {count: 4})]));
""")
        self.assertEqual(r, [True, False, True])

    def test_click_in_fold_clears_go_target(self):
        r = _js("""
HN.go = {mode: 'fast', ts: 1};
LST.click.forEach(f => f({target: {closest: s => s === '.hnw .hnnx' ? {} : null}, stopPropagation(){}}));
console.log(JSON.stringify(HN.go));
""")
        self.assertIsNone(r)

    def test_r2_css_fold_stays_in_its_cell(self):
        with open(os.path.join(ROOT, "web", "css", "41b-harness.css"), encoding="utf-8") as f:
            css = f.read()
        rule = lambda sel: css.split("\n" + sel + "{", 1)[1].split("}", 1)[0]
        self.assertIn("font-family:var(--nx-sans", rule(".hnnx"))         # not the mono of the rule path cell
        self.assertIn("min-width:0", rule(".hnnx"))
        self.assertIn("display:flex", rule(".hnnxdr>label"))              # an inline label let the select overflow
        self.assertIn("max-width:100%", rule(".hnnxdr select"))
        self.assertIn("vertical-align:top", rule(".hnrt tr:has(.hnnx[open])>td"))

    def test_47b_hooks(self):
        r = _js("""
const R = hnRep({report: {}, guards: {runs: 3, deny: 2, codes: {skipgate: 2}}});
console.log(JSON.stringify([hnInc(%s), hnInc(Object.assign({}, %s, {state: 'held'})), hnQuiet(R, 'hooks'),
  hnVdRow({cmd: 'x.py', vd: {id: 'v1', lvl: 'bad', why: 'hook_missing'}})]));
""" % (json.dumps(_INC), json.dumps(_INC)))
        self.assertIn("class=hnnx", r[0])
        self.assertNotIn("hnnx", r[1])
        self.assertIn("class=hnnx", r[2])
        self.assertIn("class=hnnx", r[3])


if __name__ == "__main__":
    unittest.main()
