"""Config-format tests: .claude/agents/*.md and skills/*/SKILL.md frontmatter, features/*.json manifests.

Variants: minimal, full, extra keys, wrong types, missing optional keys, empty file, BOM, CRLF — the reader must
neither crash nor mis-read. ⚠Synthetic files in a temp dir only; ctxsrc paths and features.warn_once are patched.
Pipelines (.claude/pipelines/*.json) are covered by tests/test_pipeline.py.
"""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import load, sidereus

load()
cx = sidereus("ctxsrc")
tv = sidereus("toolinv")
hn = sidereus("harness")
pl = sidereus("pipeline")
F = sidereus("features")

BOM = "﻿"
AGENT_FULL = ("---\nname: reviewer\ndescription: \"Reviews a diff: rules, security\"\ntools: Read, Grep, Bash\n"
              "model: opus\ncolor: blue\nfutureKey: [1, 2]\n---\n\nBody with name: not-this\n")


class _Base(unittest.TestCase):
    def setUp(self):
        t = self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-fmtfm-"))
        self.home = os.path.join(t, "home", ".claude")
        self.proj = os.path.join(t, "work", "repo")
        os.makedirs(self.home)
        os.makedirs(os.path.join(self.proj, ".claude"))
        self.saved = (cx.CLAUDE_DIR, cx.CLAUDE_JSON, tv._allowed_cwds)
        cx.CLAUDE_DIR, cx.CLAUDE_JSON = self.home, os.path.join(t, "home", ".claude.json")
        tv._allowed_cwds = lambda: {}

    def tearDown(self):
        cx.CLAUDE_DIR, cx.CLAUDE_JSON, tv._allowed_cwds = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def w(self, p, text, mode="w"):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if mode == "wb":
            with open(p, "wb") as f:
                f.write(text)
        else:
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        return p


class AgentFrontmatter(_Base):
    def agent(self, text, fn="rev.md", mode="w"):
        return self.w(os.path.join(self.home, "agents", fn), text, mode)

    def names(self):
        return [it["name"] for it in tv._md_items(self.home, "user", "", {}) if it["kind"] == "agent"]

    def test_full_minimal_missing(self):
        p = self.agent(AGENT_FULL)
        self.assertEqual(tv._front(p), {"name": "reviewer", "description": "Reviews a diff: rules, security"})
        self.assertEqual(self.names(), ["reviewer"])           # body «name:» line is past the closing ---
        self.agent("---\nname: r2\n---\n")
        self.assertEqual(self.names(), ["r2"])
        self.agent("---\ndescription: d\ntools: Read\n---\n")   # name missing -> file name
        self.assertEqual(self.names(), ["rev"])
        self.agent("---\nname:\n---\n")
        self.assertEqual(self.names(), ["rev"])
        self.agent("no frontmatter at all\nname: x\n")
        self.assertEqual(self.names(), ["rev"])

    def test_empty_bom_crlf_binary(self):
        self.agent(AGENT_FULL.replace("\n", "\r\n"))
        self.assertEqual(self.names(), ["reviewer"])
        self.assertEqual(tv._front(os.path.join(self.home, "agents", "rev.md"))["description"],
                         "Reviews a diff: rules, security")
        for text in ("", "---", "---\n", "---\nname: never-closed\n" + "x: y\n" * 2000):
            self.agent(text)
            self.assertIn(self.names()[0], ("rev", "never-closed"), repr(text[:12]))
        self.agent(BOM + AGENT_FULL)
        self.assertEqual(self.names(), ["reviewer"])            # leading BOM stripped (ctxsrc.read_text)
        self.agent(b"---\nname: \xff\xfe bad\n---\n", mode="wb")
        self.assertEqual(len(self.names()), 1)
        self.assertEqual(cx._count_agents(os.path.join(self.home, "agents")), 1)

    def test_quotes_and_wrong_types(self):
        for line, want in (("name: 'q'", "q"), ('name: "dq"', "dq"), ("name: 123", "123"),
                           ("name: [a, b]", "[a, b]"), ("name:tight", "tight")):
            self.agent("---\n%s\n---\n" % line)
            self.assertEqual(self.names(), [want], line)

    def test_nested_name_not_top_level(self):
        # ⚠toolinv._front reads column-0 keys only — a nested `name:` (e.g. under `metadata:`) must not override it.
        self.agent("---\nname: reviewer\nmetadata:\n  name: other\n---\n")
        self.assertEqual(self.names(), ["reviewer"])

    def test_harness_agent_uses_frontmatter_name(self):
        # ⚠The Agent tool's subagent_type is the frontmatter `name`: rev.md with `name: reviewer` is keyed «reviewer»
        #   in pipeline/harness exactly as in toolinv (shared toolinv.agent_name), and its file still opens.
        p = self.agent(AGENT_FULL)
        rows = hn._agent_rows(self.proj, {"agent:reviewer": {"n": 3, "last": 1}}, {})
        self.assertEqual([(r["name"], r["n"]) for r in rows], [("reviewer", 3)])
        self.assertEqual(hn._agent_path(self.proj, "reviewer"), p)
        self.assertEqual(hn._agent_path(self.proj, "rev"), "")

    def test_pipeline_agent_names_by_file(self):
        self.agent(AGENT_FULL, fn="good-name.md")
        self.agent("x", fn="Bad Name.md")
        self.w(os.path.join(self.proj, ".claude", "agents", "good-name.md"), "")
        got = pl._agents(self.proj)
        # project wins on the same name; the user file is keyed by its frontmatter name; odd file names skipped
        self.assertEqual([{"name": r["name"], "scope": r["scope"]} for r in got],
                         [{"name": "good-name", "scope": "project"}, {"name": "reviewer", "scope": "user"}])
        # desc only when the frontmatter has one (the empty project file has none)
        self.assertNotIn("desc", got[0])
        self.assertTrue(got[1].get("desc"))


class SkillFrontmatter(_Base):
    def skill(self, d, text, base=None, mode="w"):
        return self.w(os.path.join(base or self.home, "skills", d, "SKILL.md"), text, mode)

    def test_name_is_the_folder(self):
        self.skill("ship", "---\nname: something-else\ndescription: d\nallowed-tools: Read\nextra: 1\n---\nbody")
        self.skill("empty", "")
        self.skill("bom", BOM + "---\nname: bom\n---\n")
        self.skill("crlf", "---\r\nname: crlf\r\n---\r\n")
        self.skill("bin", b"\x00\xff\xfe", mode="wb")
        self.skill("Upper_Case", "---\nname: u\n---\n")
        os.makedirs(os.path.join(self.home, "skills", "nofile"))
        self.w(os.path.join(self.home, "skills", "loose.md"), "x")
        items = [it["name"] for it in tv._md_items(self.home, "user", "", {}) if it["kind"] == "skill"]
        self.assertEqual(items, ["Upper_Case", "bin", "bom", "crlf", "empty", "ship"])   # SKILL.md text never decides the name
        self.assertEqual([s["name"] for s in tv.skill_names("")], ["bin", "bom", "crlf", "empty", "ship"])   # stage-name shape only
        self.assertEqual(cx._count_skills(os.path.join(self.home, "skills")), 6)

    def test_overrides_and_project_precedence(self):
        self.skill("a", "---\nname: a\n---\n")
        self.skill("a", "---\nname: a\n---\n", base=os.path.join(self.proj, ".claude"))
        got = tv.skill_names(self.proj)
        self.assertEqual(got, [{"name": "a", "scope": "project"}])
        on = {it["name"]: it["on"] for it in tv._md_items(self.home, "user", "", {"a": "off"}) if it["kind"] == "skill"}
        self.assertEqual(on, {"a": False})
        on = {it["name"]: it["on"] for it in tv._md_items(self.home, "user", "", {"a": 1}) if it["kind"] == "skill"}
        self.assertEqual(on, {"a": True})     # a non-"off" override value is not «off»


class FeatureManifests(_Base):
    def setUp(self):
        super().setUp()
        self.d = os.path.join(self.tmp, "features")
        os.makedirs(self.d)
        self.warned = []
        self._warn = F.warn_once
        F.warn_once = lambda key, msg, **kw: self.warned.append(key)

    def tearDown(self):
        F.warn_once = self._warn
        super().tearDown()

    def m(self, fn, body):
        self.w(os.path.join(self.d, fn), body if isinstance(body, str) else json.dumps(body))

    def test_full_minimal_extra(self):
        self.m("full.json", {"id": "full", "title": "Full", "deps": ["mini"], "modules": ["sidereus.x"], "routes": ["/api/x*"],
                             "threads": ["t"], "state_keys": ["k"], "web": ["js/x.js"], "settings": ["s"],
                             "default_on_public": True, "futureKey": {"a": 1}})
        self.m("mini.json", {"id": "mini"})
        self.m("crlf.json", json.dumps({"id": "crlf", "routes": ["/r"]}, indent=2).replace("\n", "\r\n"))
        got = F._load(self.d)
        self.assertEqual(sorted(got), ["crlf", "full", "mini"])
        self.assertEqual(got["mini"]["deps"], [])                  # missing list fields default to []
        self.assertIs(got["mini"]["default_on_public"], False)
        self.assertIs(got["full"]["default_on_public"], True)
        self.assertEqual(got["crlf"]["routes"], ["/r"])
        self.assertEqual(self.warned, [])

    def test_bad_manifests_skipped_with_warning(self):
        bad = {"empty.json": "", "trunc.json": "{", "list.json": "[]", "noid.json": {"title": "x"},
               "numid.json": {"id": 5}, "badid.json": {"id": "Bad-Id"}, "routes.json": {"id": "r1", "routes": "/x"},
               "items.json": {"id": "r2", "deps": [1]}, "bom.json": BOM + '{"id": "bom1"}',
               "dpub.json": {"id": "dp", "default_on_public": "yes"}}
        for fn, body in bad.items():
            self.m(fn, body)
        self.m("ok.json", {"id": "ok"})
        self.m("dup.json", {"id": "ok"})    # sorted before ok.json: the first one wins, the second is skipped
        self.w(os.path.join(self.d, "bin.json"), b"\xff\xfe\x00", mode="wb")
        got = F._load(self.d)
        self.assertIn("ok", got)
        self.assertIs(got["dp"]["default_on_public"], False)       # only literal true counts
        self.assertNotIn("r1", got)
        self.assertNotIn("r2", got)
        self.assertTrue(set(got) <= {"ok", "dp", "bom1"}, got)       # BOM: read or skipped, never fatal
        for fn in ("empty.json", "trunc.json", "list.json", "noid.json", "numid.json", "badid.json",
                   "routes.json", "items.json", "bin.json", "ok.json"):
            self.assertIn("feature:" + fn, self.warned, fn)

    def test_id_with_trailing_newline_refused(self):
        # ⚠features._ID_RE ends in \Z: `$` would accept "abc\n", which never equals the route/toggle id "abc".
        self.m("nl.json", {"id": "abc\n"})
        self.assertEqual(F._load(self.d), {})


if __name__ == "__main__":
    unittest.main()
