"""Pipeline tab «적용» mode: config `pipeline_apply` (sidereus/prefs.py), POST /api/pipelines/apply, GET apply row, 48-pipeline.js render.

⚠Project, config and store are tmp files (test_pipeline.Routes setUp) — never the live config.local.json.
"""
import json
import os
import subprocess
import unittest

from tests import test_pipeline as TP
from tests._i18n_js import i18n_prelude
from tests._load import ROOT, sidereus
from tests.test_routes_post import post, EVIL
from tests._node import node_e

PR = sidereus("prefs")


class Apply(unittest.TestCase):
    setUp = TP.Routes.setUp

    def _set(self, body, origin=TP.ORIGIN):
        return post("/api/pipelines/apply", body, origin=origin)

    def _cfg(self):
        with open(PR.CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)["pipeline_apply"]

    def test_default_and_listing(self):
        code, out = TP.get("/api/pipelines?proj=" + self.proj)
        self.assertEqual((code, out["apply"]), (200, {"mode": "auto", "global": "auto", "own": None}))

    def test_global_then_project_override(self):
        code, out, _ = self._set({"mode": "ask"})
        self.assertEqual((code, out["apply"]["mode"]), (200, "ask"), out)
        code, out, _ = self._set({"proj": self.proj, "mode": "off"})
        self.assertEqual((code, out["apply"]), (200, {"mode": "off", "global": "ask", "own": "off"}))
        self.assertEqual(self._cfg(), {"mode": "ask", "projects": {self.proj: "off"}})
        code, out, _ = self._set({"proj": self.proj, "mode": None})   # drop the override
        self.assertEqual((code, out["apply"]), (200, {"mode": "ask", "global": "ask", "own": None}))
        self.assertEqual(self._cfg(), {"mode": "ask", "projects": {}})

    def test_refusals(self):
        for body in ({"mode": "never"}, {"mode": None}, {"proj": "/etc", "mode": "ask"}, {"proj": self.proj, "mode": 1}, []):
            self.assertEqual(self._set(body)[0], 400, body)
        for origin in (None, EVIL):
            self.assertEqual(self._set({"mode": "off"}, origin=origin)[0], 403)
        self.assertFalse(os.path.exists(PR.CONFIG_PATH))

    def test_bad_config_value_reads_default(self):
        with open(PR.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"pipeline_apply": {"mode": "loud"}}, f)
        self.assertEqual(sidereus("pipeline_projects").apply_get(self.proj)["mode"], "auto")


_F = os.path.join(ROOT, "web", "js", "48-pipeline.js")
_STUB = """
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[c]);
function lsGet(k, d){ return d; } function lsSet(){}
const document = {addEventListener(){}};
"""


class EffortEdits(unittest.TestCase):
    """R1/R3: stage and defaults `effort` round-trip through _apply (per-stage edit) and _replace (canvas save)."""
    PL = sidereus("pipeline")

    def test_apply_order_and_drop(self):
        P = TP._copy()
        new = self.PL._apply(P, {"stages": {"검증": {"effort": "max"}, "구현": {"effort": "low"}}, "defaults": {"effort": "high"}})
        self.assertEqual(list(new["stages"][2]), ["title", "agent", "model", "effort", "onFail"])   # right after model
        self.assertEqual(list(new["stages"][1])[:3], ["title", "agent", "effort"])                 # no model: after agent
        self.assertEqual(list(new["defaults"]), ["model", "effort", "retry"])
        new = self.PL._apply(new, {"stages": {"구현": {"model": "opus"}}})
        self.assertEqual(list(new["stages"][1])[:4], ["title", "agent", "model", "effort"])
        back = self.PL._apply(new, {"stages": {"검증": {"effort": ""}, "구현": {"effort": "", "model": ""}}, "defaults": {"effort": ""}})
        self.assertEqual(back, P)
        for req in ({"stages": {"검증": {"task": "x"}}}, {"defaults": {"retry": 1}}):
            with self.assertRaises(ValueError):
                self.PL._apply(P, req)

    def test_replace_round_trip(self):
        P = TP._copy()
        rows = [self.PL._stage_row(s) for s in P["stages"]]
        rows[2]["effort"], rows[0]["effort"] = "xhigh", "medium"
        new = self.PL._replace(P, {"stages": rows, "defaults": {"model": "inherit", "retry": 0, "effort": "max"}})
        self.assertEqual(new["stages"][2]["effort"], "xhigh")
        self.assertLess(list(new["stages"][2]).index("model"), list(new["stages"][2]).index("effort"))
        self.assertEqual(list(new["defaults"]), ["model", "effort", "retry"])
        self.assertEqual(self.PL._stage_row(new["stages"][2])["effort"], "xhigh")
        fresh = self.PL._replace(P, {"stages": rows[:2] + [{"title": "검증", "effort": "low", "model": "opus", "agent": "v"}]})
        self.assertEqual(list(fresh["stages"][2])[:4], ["title", "agent", "model", "effort"])   # file order kept, the new key after
        rows[2]["effort"], rows[0]["effort"] = "", ""
        back = self.PL._replace(new, {"stages": rows, "defaults": {"effort": ""}})
        self.assertEqual(back, P)
        with self.assertRaises(ValueError):
            self.PL._replace(P, {"stages": [dict(rows[0], effortLevel="high")]})
        with self.assertRaises(ValueError):
            self.PL._replace(P, {"stages": rows, "defaults": {"effortLevel": "high"}})


class ApplyJs(unittest.TestCase):
    def _html(self, d):
        with open(_F, encoding="utf-8") as f:
            src = _STUB + i18n_prelude("'ko'", ("T", "TV", "U")) + f.read() + "\nconsole.log(JSON.stringify(plApplySeg(%s)))" % json.dumps(d)
        return json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True, encoding="utf-8").stdout)

    def test_render(self):
        h = self._html({"ok": True, "apply": {"mode": "ask", "global": "auto", "own": "ask"}})
        self.assertIn('class="wkrgb on" data-plap="ask"', h)
        self.assertEqual(h.count('data-plap='), 3)
        self.assertNotIn("data-plapown", h)                   # «This project only» checkbox removed
        self.assertNotIn("checkbox", h)
        self.assertIn("새로 시작하는 세션부터 적용됩니다", h)
        h = self._html({"ok": True, "apply": {"mode": "auto", "global": "auto", "own": None}})
        self.assertIn('class="wkrgb on" data-plap="auto"', h)
        self.assertNotIn("checked", h)
        self.assertEqual(self._html({"ok": False}), "")

    def test_set_always_posts_proj(self):
        # Pipelines are per project: Apply always posts {proj, mode}, and other projects' cache stays.
        with open(_F, encoding="utf-8") as f:
            src = (_STUB + i18n_prelude("'ko'", ("T", "TV", "U")) + f.read()
                   + "\nlet POSTS = [], ASKED = []; globalThis.confirm = m => { ASKED.push(m); return true; }; globalThis.alert = () => {};"
                   "\nasync function postJSON(u, b){ POSTS.push([u, b]); return {ok: true, apply: {mode: b.mode}}; } function plPaint(){}"
                   "\nPLS.proj = '/w/a'; PLS.data = {'/w/a': {ok: true, apply: {mode: 'auto', global: 'auto', own: null}}, '/w/b': {ok: true}};"
                   "\nplApplySet('off').then(ok => console.log(JSON.stringify([ok, POSTS, Object.keys(PLS.data), ASKED[0]])));")
        ok, posts, keys, asked = json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True, encoding="utf-8").stdout)
        self.assertTrue(ok)
        self.assertEqual(posts, [["/api/pipelines/apply", {"proj": "/w/a", "mode": "off"}]])
        self.assertEqual(keys, ["/w/a", "/w/b"])
        self.assertIn("/w/a", asked)


if __name__ == "__main__":
    unittest.main()
