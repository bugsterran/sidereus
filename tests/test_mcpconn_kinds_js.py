"""«Connections» kind chips (web/js/47k chips · 47m nodes and cards · 47l send): R1 chips + persisted pick · R2 used/unused
nodes and bars · R3 hook card, no command text · R4 Task-only detail, confirm-only send · R5 many items never overlap ·
Non-goal: unsupported CLI says so. Pure functions under node, stubs only."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import sidereus
from tests._node import node_e
from tests.test_mcpconn_js import _EV, _FS, _PRE, _ROW, _read

_SK = [{"name": "docs", "kind": "skill", "scope": "project", "plug": "", "path": "~/w/proj/.claude/skills/docs/SKILL.md", "n": 5, "last": 9900},
       {"name": "<b>x", "kind": "skill", "scope": "user", "plug": "", "path": "~/.claude/skills/x/SKILL.md", "n": 0, "last": 0},
       {"name": "ship", "kind": "cmd", "scope": "user", "plug": "", "path": "~/.claude/commands/ship.md", "n": 2, "last": 9000},
       {"name": "lint", "kind": "skill", "scope": "plugin", "plug": "tools", "path": "~/.claude/plugins/tools/skills/lint/SKILL.md", "n": 9, "last": 5000}]
_AG = [{"name": "reviewer", "scope": "project", "plug": "", "path": "~/w/proj/.claude/agents/reviewer.md", "n": 1, "last": 9990},
       {"name": "Explore", "scope": "seen", "plug": "", "path": "", "n": 3, "last": 9000}]
_HK = [{"name": "PreToolUse", "scope": "user", "plug": "", "path": "~/.claude/settings.json", "n": 7, "last": 9950,
        "command": "SECRET-CMD run.sh", "files": [{"scope": "user", "path": "~/.claude/settings.json", "matcher": "Bash", "command": "SECRET-CMD"}],
        "subs": [{"name": "PreToolUse:Bash", "n": 5, "last": 9950}, {"name": "PreToolUse:Edit", "n": 2, "last": 9000}]},
       {"name": "Stop", "scope": "project", "plug": "", "path": "~/w/proj/.claude/settings.json", "n": 0, "last": 0, "files": [], "subs": []}]
_DATA = {"ok": True, "now": 10000, "sid": _ROW["sid"], "plat": "cc", "supported": True, "counts": True, "scanning": False, "checked": 9000,
         "servers": [{"name": "ctx7", "scope": "user", "plug": "", "transport": "stdio", "on": True, "state": "ok", "err": "", "at": 9000, "n": 3, "last": 9800}],
         "totals": {"ok": 1, "fail": 0, "auth": 0, "unknown": 0},
         "kinds": {"skill": {"supported": True, "items": _SK, "more": 0}, "agent": {"supported": True, "items": _AG, "more": 0},
                   "hook": {"supported": True, "items": _HK, "more": 0}}}
_UNSUP = dict(_DATA, plat="pi", kinds={k: {"supported": False, "items": [], "more": 0} for k in ("skill", "agent", "hook")})


def _js(body, pre=""):
    src = _PRE + pre
    for p in _FS:
        src += _read(p) + "\n"
    r = subprocess.run(node_e(src + body), capture_output=True, text=True, encoding="utf-8", timeout=30)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def _set(kind, data=_DATA, row=_ROW):
    return "SESS = [%s]; const D = %s; MCPC.sid = D.sid; MCPC.data = D; MCPC.kind = '%s';" % (json.dumps(row), json.dumps(data), kind)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class McpConnKindsJs(unittest.TestCase):
    def test_R1_four_chips_and_persisted_pick(self):
        out = _js(_EV + _set("mcp") + " const a = mcpcKindsHtml(D); fire('click', {'data-mcpck': {mcpck: 'skill'}});"
                  " const b = mcpcKindsHtml(D); fire('click', {'data-mcpck': {mcpck: 'bogus'}});"
                  " console.log(JSON.stringify({a, b, kind: MCPC.kind, store: STORE['sidereus.mcpckind'],"
                  " old: mcpcKindsHtml(Object.assign({}, D, {kinds: undefined})), un: mcpcKindsHtml(%s)}))" % json.dumps(_UNSUP))
        self.assertEqual(re.findall(r'data-mcpck="(\w+)"', out["a"]), ["mcp", "skill", "agent", "hook"])
        self.assertIn('data-mcpck="mcp" aria-pressed="true"', out["a"])
        self.assertIn('data-mcpck="skill" aria-pressed="true"', out["b"])
        self.assertIn("<span>스킬</span><b>4</b>", out["b"])
        self.assertEqual((out["kind"], out["store"]), ("skill", "skill"))       # a bad chip value changes nothing
        self.assertIn('data-mcpck="mcp" aria-pressed="true"', out["old"])     # older server: MCP only
        self.assertIn('data-mcpck="skill" aria-pressed="false" disabled', out["old"])
        self.assertIn("<span>훅</span><b>—</b>", out["un"])                    # unsupported = «—», never 0
        self.assertTrue(sidereus("ui_prefs").KEY_RE.match("sidereus.mcpckind"))

    def test_R1_bad_stored_kind_falls_back(self):
        out = _js("console.log(JSON.stringify(MCPC.kind))", pre="STORE['sidereus.mcpckind'] = 'evil';\n")
        self.assertEqual(out, "mcp")
        out = _js("console.log(JSON.stringify(MCPC.kind))", pre="STORE['sidereus.mcpckind'] = 'hook';\n")
        self.assertEqual(out, "hook")

    def test_R2_used_unused_nodes_and_sorted_bars(self):
        out = _js(_set("skill") + " console.log(JSON.stringify([mcpcStage(SESS[0], D, 1000, 620), mcpcKindCalls(D, 'skill'), mcpcCoreSum(D)]))")
        st, bars, core = out
        self.assertRegex(st, r'class="mcpcn kind st-used used"[^>]*data-mcpcn="docs"')
        self.assertRegex(st, r'class="mcpcn kind st-unused"[^>]*data-mcpcn="&lt;b&gt;x"')
        self.assertIn("호출 5", st)
        self.assertIn("안 씀", st)
        self.assertIn(">/ship<", st)                                          # slash command under the Skills chip
        self.assertNotIn("<b>x", st)
        self.assertEqual(re.findall(r'class=mcpcbn title="([^"]+)"', bars), ["lint", "docs", "/ship"])
        self.assertEqual(core, "씀 3 · 안 씀 1")

    def test_R3_hook_card_names_runs_no_command(self):
        out = _js(_set("hook") + " MCPC.sel = 'PreToolUse'; console.log(JSON.stringify([mcpcStage(SESS[0], D, 1000, 620), mcpcSideHtml(D, SESS[0])]))")
        st, side = out
        self.assertIn("실행 7", st)
        for s in ("PreToolUse:Bash", "PreToolUse:Edit", "~/.claude/settings.json", ">Bash<", "매처"):
            self.assertIn(s, side)
        self.assertLess(side.index("PreToolUse:Bash"), side.index("PreToolUse:Edit"))
        self.assertNotIn("SECRET", st + side)

    def test_R4_detail_task_only_and_confirm_send(self):
        both = "".join(_read(p) for p in _FS)
        self.assertEqual(both.count("postJSON("), 1)
        out = _js(_EV + _set("skill") + " fire('click', {'data-mcpcn': {mcpcn: 'docs'}}); const h0 = mcpcSideHtml(D, SESS[0]);"
                  " MCPC.note['skill:docs'] = 'update the readme'; const h = mcpcKindDetail(D, SESS[0], 'skill'); const before = POSTS.length;"
                  " const want = mcpcKindBody('skill', D.kinds.skill.items[0], 'update the readme');"
                  " fire('click', {'data-mcpcgo': {}});"
                  " setTimeout(() => console.log(JSON.stringify({h0, h, before, posts: POSTS, want, log: MCPC.log, note: MCPC.note})), 0);")
        h = out["h"]
        for s in ("프로젝트", "~/w/proj/.claude/skills/docs/SKILL.md", "호출 5", 'data-mcpcka="task"'):
            self.assertIn(s, h)
        self.assertEqual(re.findall(r"data-mcpca=", h), [])                  # no Diagnose / Restart / Reconnect
        self.assertNotIn("data-mcpcgo disabled", h)
        self.assertIn("data-mcpcgo disabled", out["h0"])                      # no note yet: nothing to send
        self.assertEqual(out["before"], 0)
        self.assertEqual(len(out["posts"]), 1)
        u, b = out["posts"][0]
        self.assertEqual(u, "/api/dm")
        self.assertEqual(b, {"to": "mb-a", "body": out["want"], "relay": True, "sid": _ROW["sid"], "thread": "skill:docs"})
        self.assertEqual(out["want"], "Use the docs skill for this: update the readme")
        self.assertTrue(sidereus("bus").DM_THREAD.match(b["thread"]))
        self.assertEqual((out["log"][0]["k"], out["log"][0]["a"], out["log"][0]["s"]), ("skill", "task", "docs"))
        self.assertEqual(out["note"]["skill:docs"], "")

    def test_R4_bodies_name_and_note_only(self):
        out = _js("const S = %s, A = %s, H = %s; console.log(JSON.stringify([mcpcKindBody('skill', S[2], 'go'), mcpcKindBody('agent', A[0], 'look'),"
                  " mcpcKindBody('hook', H[0], 'why slow'), mcpcKindBody('skill', S[0], ''), mcpcThread('a/b c', 'hook'), mcpcThread('x'.repeat(90), 'agent')]))"
                  % (json.dumps(_SK), json.dumps(_AG), json.dumps(_HK)))
        self.assertEqual(out[:3], ["Use the /ship command for this: go", "Use the reviewer agent for this: look", "About the PreToolUse hooks: why slow"])
        self.assertIn("(one-line request needed)", out[3])
        for b in out[:4]:
            for s in ("~/", "project", "SECRET", "9900"):
                self.assertNotIn(s, b)
        self.assertEqual(out[4], "hook:a-b c")
        self.assertEqual(len(out[5]), 60)
        for t in out[4:]:
            self.assertTrue(sidereus("bus").DM_THREAD.match(t))

    def test_R4_not_logged_in_disables(self):
        row = dict(_ROW, mboxSrc="env")
        out = _js(_EV + _set("agent", row=row) + " MCPC.sel = 'reviewer'; MCPC.note['agent:reviewer'] = 'x';"
                  " const h = mcpcKindDetail(D, SESS[0], 'agent'); fire('click', {'data-mcpcgo': {}});"
                  " setTimeout(() => console.log(JSON.stringify({h, n: POSTS.length})), 0);")
        self.assertEqual(out["n"], 0)
        self.assertIn("data-mcpcgo disabled", out["h"])
        self.assertIn("메일박스에 로그인하지 않았습니다", out["h"])

    def test_R5_many_items_never_overlap(self):
        out = _js("const R = []; for(const [W, H, n] of [[1406, 834, 60], [986, 834, 60], [1018, 620, 60], [818, 520, 60], [818, 520, 150]]){"
                  " const w = 84, h = mcpcGrowH(W, H, n, 0, true), g = mcpcGeo(W, h, n, 0, true), ps = g.inner;"
                  " R.push([W, H, n, h, ps.filter(Boolean).length, mcpcHits(ps, w * 2), ps.filter(p => p.x - w < 0 || p.x + w > W || p.y - 14 < 0 || p.y + 68 > h).length]); }"
                  " const items = Array.from({length: 60}, (_, i) => ({name: 'toolkit:task-' + i, kind: 'skill', scope: 'plugin', plug: 'toolkit', path: '', n: i % 3, last: 9000}));"
                  " const D = {ok: true, now: 10000, sid: 's', kinds: {skill: {supported: true, items, more: 0}}}; MCPC.kind = 'skill';"
                  " const st = mcpcStage({sid: 's', plat: 'cc', project: 'p'}, D, 818, mcpcGrowH(818, 520, 60, 0, true));"
                  " console.log(JSON.stringify({R, nodes: (st.match(/<button[^>]*data-mcpcn=/g) || []).length, undef: st.indexOf('undefined') >= 0 || st.indexOf('NaN') >= 0}))")
        for W, H, n, h, placed, hits, outside in out["R"]:
            self.assertEqual((placed, hits, outside), (n, 0, 0), (W, H, n, h))
            self.assertLess(h, 8000)
        self.assertEqual(out["nodes"], 60)
        self.assertFalse(out["undef"])

    def test_R2_label_full_without_plugin_prefix(self):
        out = _js("console.log(JSON.stringify([mcpcKindLabel('skill', {name: 'plugx:ask', plug: 'plugx'}),"
                  " mcpcKindLabel('skill', {name: 'plugx:deep', plug: 'plugx', kind: 'cmd'}),"
                  " mcpcKindLabel('hook', {name: 'PostToolUseFailure', plug: ''}), mcpcKindLabel('skill', {name: 'other:x', plug: 'plugx'})]))")
        self.assertEqual(out, ['<span class="mcpct">ask</span>', '<span class="mcpct">/deep</span>',
                               '<span class="mcpct l2">PostToolUseFailure</span>', '<span class="mcpct">other:x</span>'])

    def test_nongoal_unsupported_says_so(self):
        out = _js(_set("skill", data=_UNSUP) + " const a = mcpcStage(SESS[0], D, 1000, 620), s = mcpcSideHtml(D, SESS[0]);"
                  " LANG = 'en'; console.log(JSON.stringify([a, s, mcpcStage(SESS[0], D, 1000, 620), mcpcCoreSum(D)]))")
        ko, side, en, core = out
        self.assertIn("이 CLI 는 아직 읽지 않습니다", ko)
        self.assertIn("Not read for this CLI yet", en)
        self.assertNotIn("data-mcpcn=", ko)
        self.assertIn("<b>—</b>", side)
        self.assertNotIn("<b>0</b>", side)
        self.assertEqual(core, "")

    def test_poll_keeps_kind_and_selection(self):
        out = _js(_set("agent") + " MCPC.sel = 'reviewer'; const h = mcpcSideHtml(D, SESS[0]); mcpcPick('other');"
                  " console.log(JSON.stringify([h.indexOf('mcpcdet') >= 0 && h.indexOf('reviewer.md') >= 0, MCPC.kind, MCPC.sel]))")
        self.assertEqual(out, [True, "agent", ""])                           # kind survives a session pick; sel does not


if __name__ == "__main__":
    unittest.main()
