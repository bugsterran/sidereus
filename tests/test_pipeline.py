"""«파이프라인» (sidereus/pipeline.py): validation parity with the runner, GET listing, save dry/write/backup, guards.

⚠Projects, agents and backups live in a tmp dir: `known_projects` (pipeline_projects) and `BAK_DIR` (pipeline) are patched,
  `CLAUDE_DIR` on ctxsrc — never the live ~/.claude or the repo's own .claude/pipelines.
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import load, sidereus
from tests.test_prefs import get
from tests.test_routes_post import post, PORT, EVIL

cs = load()
PL = sidereus("pipeline")
PN = sidereus("pipeline_new")
F = sidereus("features")
CX = sidereus("ctxsrc")
PP = sidereus("pipeline_projects")
PS = sidereus("pipeline_schema")
ORIGIN = "http://127.0.0.1:%d" % PORT

SAMPLE = {
    "v": 1, "name": "demo", "title": "변경", "rules": "secret-rules-text",
    "defaults": {"model": "inherit", "retry": 0},
    "stages": [
        {"title": "설계", "agent": "designer", "task": "secret-task-text", "produces": "slices"},
        {"title": "구현", "agent": "impl", "fanout": "slices", "gate": "scripts/check.sh --fast"},
        {"title": "검증", "agent": "verifier", "model": "sonnet", "onFail": {"goto": "구현", "max": 2}},
        {"title": "리뷰", "agent": "reviewer", "onFail": {"goto": "구현", "max": 1, "then": "재검증"}},
        {"title": "재검증", "agent": "verifier", "model": "sonnet", "onlyOnJump": True},
    ],
}


def _copy():
    return json.loads(json.dumps(SAMPLE))


class Validate(unittest.TestCase):
    def test_sample_ok(self):
        self.assertEqual(PS.validate(_copy(), "demo"), [])

    def test_rules(self):
        cases = [
            (lambda P: P.update(v=True), "v must be 1"),
            (lambda P: P.update(name="other"), "name must equal"),
            (lambda P: P["defaults"].update(model="gpt"), "defaults.model"),
            (lambda P: P["defaults"].update(retry=4), "defaults.retry"),
            (lambda P: P.update(use="a\nb"), "use: one line"),
            (lambda P: P.update(use="x" * 121), "use: one line"),
            (lambda P: P.update(use=" "), "use: one line"),
            (lambda P: P.update(use=5), "use: one line"),
            (lambda P: P["stages"][0].update(title="사용자 단계 1"), "reserved"),
            (lambda P: P["stages"][1].update(title="배포 확인"), "required for a custom stage"),   # custom title, no task
            (lambda P: P["stages"][0].update(title="x" * 41), "1-40 chars"),
            (lambda P: P["stages"][1].update(title="설계"), "duplicated"),
            (lambda P: P["stages"][0].update(agent="bad\n"), ".agent"),       # ⚠Python `$` would pass this
            (lambda P: P["stages"][0].update(skill="Bad X"), ".skill"),
            (lambda P: P["stages"][0].update(skill="ship\n"), ".skill"),
            (lambda P: P["stages"][2].update(model="gpt"), ".model"),
            (lambda P: P["stages"][2].update(retry=True), ".retry"),
            (lambda P: P["stages"][2]["onFail"].update(goto="리뷰"), "earlier stage"),
            (lambda P: P["stages"][3]["onFail"].update(then="구현"), "later stage"),
            (lambda P: P["stages"][2]["onFail"].update(max=6), "onFail.max"),
            (lambda P: P["stages"][0].pop("produces"), "fanout needs"),
            (lambda P: P["stages"][1].update(gate="a\nb"), ".gate"),
            (lambda P: P["stages"][0].update(onlyOnJump=True), "stages[0] cannot"),
            (lambda P: P["stages"][0].update(ui={"x": 1}), ".ui"),
            (lambda P: P["stages"][0].update(ui={"x": True, "y": 1}), ".ui"),
            (lambda P: P["stages"][0].update(ui={"x": 1, "y": 1, "color": "#ABCDEF"}), ".ui"),   # lower-case hex only
            (lambda P: P["stages"][0].update(ui={"x": 1, "y": 1, "color": "#abcdef\n"}), ".ui"),
        ]
        for mut, want in cases:
            P = _copy()
            mut(P)
            errs = PS.validate(P, "demo")
            self.assertTrue(any(want in e for e in errs), (want, errs))

    def test_custom_title_ok(self):
        P = _copy()
        P["stages"][1].update(title="문서 정리", task="update the docs")
        P["stages"][2]["onFail"]["goto"] = "문서 정리"
        P["stages"][3]["onFail"]["goto"] = "문서 정리"
        self.assertEqual(PS.validate(P, "demo"), [])

    def test_dump_round_trip(self):
        text = PS.dump(_copy())
        self.assertEqual(json.loads(text), SAMPLE)
        self.assertEqual(PS.dump(json.loads(text)), text)
        self.assertIn('"onFail": { "goto": "구현", "max": 2 }', text)


class Suggest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-sug-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _sug(self, proj, names, user=()):
        d = os.path.join(self.tmp, proj)
        os.makedirs(d, exist_ok=True)
        ag = [{"name": n, "scope": "project"} for n in names] + [{"name": n, "scope": "user"} for n in user]
        out = PL.suggest(d, ag)
        for P in out:
            self.assertEqual(PS.validate(P, P["name"]), [], P)
        return {P["name"]: [(s["title"], s["agent"]) for s in P["stages"]] for P in out}, out

    def test_ledger(self):
        got, out = self._sug("ledger", ["ledger-triage", "ledger-bugfix", "ledger-gate", "ledger-reviewer"])
        self.assertEqual(got, {"bugfix": [("트리아지", "ledger-triage"), ("재현", "ledger-bugfix"), ("원인", "ledger-bugfix"),
                                          ("수정", "ledger-bugfix"), ("검증", "ledger-gate"), ("리뷰", "ledger-reviewer")]})
        self.assertEqual(out[0]["stages"][5]["onFail"], {"goto": "수정", "max": 1})
        self.assertEqual(out[0]["rules"], "Never commit or push.")

    def test_cart_api_global_by_dir_name(self):
        os.makedirs(os.path.join(self.tmp, "cart-api"))
        open(os.path.join(self.tmp, "cart-api", "AGENTS.md"), "w", encoding="utf-8").close()
        got, out = self._sug("cart-api", [], user=["cart-api-be", "cart-api-bugfix", "cart-api-qa", "cart-gate",
                                                    "cart-live-verify", "cart-triage", "ledger-probe"])
        self.assertEqual(got["bugfix"], [("재현", "cart-api-bugfix"), ("원인", "cart-api-bugfix"), ("수정", "cart-api-bugfix"),
                                         ("검증", "cart-api-qa")])                  # ⚠no «cart-» fallback
        self.assertEqual(got["change"], [("구현", "cart-api-be"), ("검증", "cart-api-qa")])
        self.assertEqual(out[0]["rules"], "Follow AGENTS.md in the repo.\nNever commit or push.")

    def test_cart_agent_own_then_shared_prefix(self):
        own = ["agent-runner", "ledger-append", "ledger-column", "ledger-ddl", "ledger-fix", "ledger-index", "ledger-live"]
        user = ["ledger-probe", "ledger-gate", "cart-triage", "cart-api-bugfix", "cart-api-qa", "cart-code-review",
                "cart-live-verify", "migration-spec-author"]
        got, out = self._sug("cart-agent", own, user=user)
        self.assertEqual(got, {"bugfix": [("재현", "ledger-probe"), ("원인", "ledger-fix"), ("수정", "ledger-fix"),
                                          ("검증", "ledger-gate"), ("라이브 검증", "ledger-live")]})
        self.assertEqual(out[0]["stages"][3]["model"], "sonnet")

    def test_sidereus(self):
        got, out = self._sug(".mailbox-mcp", ["sidereus-designer", "sidereus-implementer", "sidereus-verifier", "sidereus-reviewer"])
        self.assertEqual(got, {"change": [("설계", "sidereus-designer"), ("구현", "sidereus-implementer"), ("검증", "sidereus-verifier"),
                                          ("리뷰", "sidereus-reviewer")]})
        self.assertEqual(out[0]["stages"][2]["model"], "sonnet")
        self.assertEqual(self._sug("none", ["writer", "helper"])[0], {})


class Routes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-pipe-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(self.proj, ".claude", "pipelines"))
        os.makedirs(os.path.join(self.proj, ".claude", "agents"))
        os.makedirs(os.path.join(self.tmp, "home", "agents"))
        for n in ("designer", "impl", "verifier", "reviewer"):
            open(os.path.join(self.proj, ".claude", "agents", n + ".md"), "w", encoding="utf-8").close()
        open(os.path.join(self.tmp, "home", "agents", "helper.md"), "w", encoding="utf-8").close()
        self.file = os.path.join(self.proj, ".claude", "pipelines", "demo.json")
        self.raw = PS.dump(_copy())
        with open(self.file, "w", encoding="utf-8") as f:
            f.write(self.raw)
        self.repo = os.path.join(self.tmp, "repo-only")      # a live session's repo that is not its cwd
        os.makedirs(self.repo)
        for p in (mock.patch.object(PP, "known_projects", lambda: [self.proj]),
                  mock.patch.object(PP, "_allowed_cwds", lambda: {self.proj: {"cwd": self.proj, "repos": [self.proj, self.repo, "/no/such/dir"]}}),
                  mock.patch.object(PL, "CODE_DIR", self.proj),
                  mock.patch.object(PP, "CODE_DIR", self.proj),
                  mock.patch.object(PL, "BAK_DIR", os.path.join(self.tmp, "bak")),
                  mock.patch.object(PP, "PROJ_STORE", os.path.join(self.tmp, "pipeline-projects.json")),
                  mock.patch.object(PP, "USER_HOME", self.tmp),
                  mock.patch.object(PL, "_strftime", lambda fmt: "20261001-120000"),
                  mock.patch.object(CX, "CLAUDE_DIR", os.path.join(self.tmp, "home")),
                  mock.patch.object(F, "_TOGGLES", {}),
                  mock.patch.object(sidereus("prefs"), "CONFIG_PATH", os.path.join(self.tmp, "config.local.json"))):   # apply_get: never the live config
            p.start()
            self.addCleanup(p.stop)

    def _list(self):
        code, out = get("/api/pipelines?proj=" + self.proj)
        self.assertEqual(code, 200)
        return out

    def _save(self, body, origin=ORIGIN):
        b = dict({"proj": self.proj, "name": "demo", "base": self._list()["pipelines"][0]["sha"]}, **body)
        return post("/api/pipelines/save", b, origin=origin)

    def test_list_rows(self):
        out = self._list()
        row = out["pipelines"][0]
        self.assertTrue(row["ok"])
        self.assertEqual([s["title"] for s in row["stages"]], ["설계", "구현", "검증", "리뷰", "재검증"])
        self.assertEqual(row["stages"][2]["onFail"], {"goto": "구현", "max": 2})
        self.assertEqual(row["stages"][0]["instr"], "secret-task-text")      # stage task = editable config (step 4)
        self.assertNotIn("task", row["stages"][0])
        self.assertEqual([a["name"] for a in out["agents"]], ["designer", "impl", "reviewer", "verifier", "helper"])
        self.assertEqual(row["rules"], "secret-rules-text")                  # user-written config, editable (step 4)
        self.assertEqual(set(out["default_tasks"]), set(PS.STAGE_TITLES))     # parsed from the runner
        code, out = get("/api/pipelines")
        self.assertEqual(out["projects"], [{"path": self.proj, "n": 1}])

    def test_list_roles(self):
        ag = [{"name": n, "scope": "project"} for n in ("sidereus-designer", "sidereus-implementer", "sidereus-verifier", "sidereus-reviewer", "sidereus-ux-reviewer")]
        with mock.patch.object(PL, "_agents", lambda proj: ag):
            out = self._list()
        r = out["roles"]
        self.assertEqual((r["design"], r["build"], r["check"], r["review"], r["ux"]),
                         ("sidereus-designer", "sidereus-implementer", "sidereus-verifier", "sidereus-reviewer", "sidereus-ux-reviewer"))
        self.assertTrue(all(isinstance(v, str) for v in r.values()))                 # names only

    def test_unknown_project(self):
        self.assertEqual(get("/api/pipelines?proj=/etc")[0], 400)
        code, out, _ = post("/api/pipelines/save", {"proj": "/etc", "name": "demo", "base": ""}, origin=ORIGIN)
        self.assertEqual(code, 403)

    def test_invalid_file_listed_with_errors(self):
        P = _copy()
        P["stages"][0]["title"] = "사용자 단계 3"
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(P, f)
        row = self._list()["pipelines"][0]
        self.assertFalse(row["ok"])
        self.assertNotIn("stages", row)
        self.assertTrue(row["errs"])

    def test_save_dry_then_write(self):
        edit = {"stages": {"리뷰": {"model": "opus"}, "구현": {"agent": "helper"}}, "defaults": {"model": "sonnet"}}
        code, out, _ = self._save(dict(edit, dry=True))
        self.assertEqual(code, 200, out)
        self.assertTrue(out["dry"])
        self.assertIn('+      "model": "opus",', out["diff"])
        self.assertIn('+      "agent": "helper",', out["diff"])
        with open(self.file, encoding="utf-8") as f:
            self.assertEqual(f.read(), self.raw)                  # dry wrote nothing
        code, out, _ = self._save(dict(edit, dry=False))
        self.assertEqual(code, 200, out)
        with open(self.file, encoding="utf-8") as f:
            new = json.load(f)
        self.assertEqual(new["stages"][3]["model"], "opus")
        self.assertEqual(list(new["stages"][3])[:3], ["title", "agent", "model"])   # inserted after agent
        self.assertEqual(new["stages"][1]["agent"], "helper")
        self.assertEqual(new["defaults"]["model"], "sonnet")
        self.assertEqual(new["stages"][0]["task"], "secret-task-text")               # untouched fields kept
        with open(out["backup"], encoding="utf-8") as f:
            self.assertEqual(f.read(), self.raw)
        self.assertTrue(out["backup"].startswith(os.path.join(self.tmp, "bak", "20261001-120000")))

    def test_save_refuses_symlinked_pipelines_dir(self):
        base = self._list()["pipelines"][0]["sha"]
        d = os.path.join(self.proj, ".claude", "pipelines")
        out_dir = os.path.join(self.tmp, "outside")
        shutil.move(d, out_dir)
        os.symlink(out_dir, d)
        code, out, _ = post("/api/pipelines/save", {"proj": self.proj, "name": "demo", "base": base,
                                                    "stages": {"리뷰": {"model": "opus"}}, "dry": False}, origin=ORIGIN)
        self.assertEqual(code, 400, out)
        self.assertEqual(out["err"], "path leaves the project")
        with open(os.path.join(out_dir, "demo.json"), encoding="utf-8") as f:
            self.assertEqual(f.read(), self.raw)

    def _stages(self):
        return [dict(s) for s in self._list()["pipelines"][0]["stages"]]

    def test_canvas_save_whole_list(self):
        st = self._stages()
        st[1], st[2] = dict(st[1], retry=0, instr="do it", ui={"x": 10, "y": 20}), dict(st[2], model="")
        st = st[:4]                                   # drop 재검증; 리뷰's then must go with it
        del st[3]["onFail"]["then"]
        code, out, _ = self._save({"stages": st, "defaults": {"model": "opus", "retry": 1}, "dry": False})
        self.assertEqual(code, 200, out)
        with open(self.file, encoding="utf-8") as f:
            new = json.load(f)
        self.assertEqual([s["title"] for s in new["stages"]], ["설계", "구현", "검증", "리뷰"])
        self.assertEqual(new["stages"][1], {"title": "구현", "agent": "impl", "fanout": "slices", "gate": "scripts/check.sh --fast",
                                            "task": "do it", "retry": 0, "ui": {"x": 10, "y": 20}})
        self.assertNotIn("model", new["stages"][2])
        self.assertEqual(new["stages"][0]["task"], "secret-task-text")
        self.assertEqual((new["rules"], new["defaults"]), ("secret-rules-text", {"model": "opus", "retry": 1}))

    def test_stage_colour_round_trip_and_bad_dropped(self):
        st = self._stages()
        st[0] = dict(st[0], ui={"x": 1, "y": 2, "color": "#f472b6"})
        st[1] = dict(st[1], ui={"x": 3, "y": 4, "color": "red;background:url(x)"})
        code, out, _ = self._save({"stages": st, "dry": False})
        self.assertEqual(code, 200, out)
        rows = self._list()["pipelines"][0]
        self.assertTrue(rows["ok"], rows)
        self.assertEqual((rows["stages"][0]["ui"], rows["stages"][1]["ui"]), ({"x": 1, "y": 2, "color": "#f472b6"}, {"x": 3, "y": 4}))

    def test_rules_round_trip(self):
        st = self._stages()
        code, out, _ = self._save({"stages": st, "rules": "Never commit or push.\nextra", "dry": False})
        self.assertEqual(code, 200, out)
        self.assertEqual(self._list()["pipelines"][0]["rules"], "Never commit or push.\nextra")
        code, out, _ = self._save({"stages": st, "rules": "", "dry": False})
        self.assertEqual(code, 200, out)
        with open(self.file, encoding="utf-8") as f:
            self.assertNotIn("rules", json.load(f))
        code, out, _ = self._save({"stages": st, "rules": "back", "dry": False})
        with open(self.file, encoding="utf-8") as f:
            self.assertEqual(list(json.load(f))[:4], ["v", "name", "title", "rules"])   # new key right after title
        self.assertEqual(self._save({"stages": st, "rules": 5, "dry": True})[0], 400)

    def test_use_round_trip(self):
        st = self._stages()
        code, out, _ = self._save({"stages": st, "use": "viewer changes", "dry": False})
        self.assertEqual(code, 200, out)
        self.assertEqual(self._list()["pipelines"][0]["use"], "viewer changes")
        with open(self.file, encoding="utf-8") as f:
            self.assertEqual(list(json.load(f))[:5], ["v", "name", "title", "use", "rules"])   # use right after title
        self.assertEqual(self._save({"stages": st, "use": "a\nb", "dry": True})[0], 400)
        self.assertEqual(self._save({"stages": st, "use": 5, "dry": True})[0], 400)
        code, out, _ = self._save({"stages": st, "use": "", "dry": False})
        self.assertEqual(code, 200, out)
        with open(self.file, encoding="utf-8") as f:
            self.assertNotIn("use", json.load(f))

    def test_rename_title_with_references(self):
        P = _copy()
        for s in P["stages"]:
            s.setdefault("task", "t")                                                         # a renamed stage becomes custom: needs a task
        with open(self.file, "w", encoding="utf-8") as f:
            f.write(PS.dump(P))
        code, out, _ = self._save({"stages": {"구현": {"title": "  Build it  "}}, "dry": True})
        self.assertEqual(code, 200, out)
        self.assertIn('+      "title": "Build it",', out["diff"])
        code, out, _ = self._save({"stages": {"구현": {"title": "Build it"}, "재검증": {"title": "Again"}}, "dry": False})
        self.assertEqual(code, 200, out)
        with open(self.file, encoding="utf-8") as f:
            new = json.load(f)
        self.assertEqual([s["title"] for s in new["stages"]], ["설계", "Build it", "검증", "리뷰", "Again"])
        self.assertEqual(new["stages"][2]["onFail"]["goto"], "Build it")                     # every reference follows
        self.assertEqual((new["stages"][3]["onFail"]["goto"], new["stages"][3]["onFail"]["then"]), ("Build it", "Again"))
        self.assertTrue(os.path.isfile(out["backup"]))
        self.assertEqual(self._save({"stages": {"설계": {"title": "X"}}, "dry": True}, origin="http://evil.example")[0], 403)

    def test_rename_swap_and_refusals(self):
        code, out, _ = self._save({"stages": {"검증": {"title": "리뷰"}, "리뷰": {"title": "검증"}}, "dry": False})
        self.assertEqual(code, 200, out)                                                      # a swap never merges two stages
        with open(self.file, encoding="utf-8") as f:
            new = json.load(f)
        self.assertEqual([s["title"] for s in new["stages"]][2:4], ["리뷰", "검증"])
        self.assertEqual(new["stages"][3]["onFail"]["goto"], "구현")
        for t, why in (("", "empty"), ("   ", "empty"), ("x" * 25, "at most 24"), ("a/b", "no /"), ("a]b", "no /"), ("a|b", "no /"),
                       ("a\nb", "no /"), ("설계", "already used"), (3, "empty")):
            code, out, _ = self._save({"stages": {"구현": {"title": t}}, "dry": True})
            self.assertEqual(code, 400, (t, out))
            self.assertIn(why, out["err"], t)
        st = self._stages()
        st[1] = dict(st[1], title="y" * 25)                                                   # canvas path: same rules for a new title
        self.assertIn("at most 24", self._save({"stages": st, "dry": True})[1]["err"])
        st[1] = dict(st[1], title="설계")
        self.assertIn("already used", self._save({"stages": st, "dry": True})[1]["err"])

    def test_canvas_save_refusals(self):
        for bad in ([{"title": "설계", "agent": "designer", "prompt": "x"}],                  # unknown key
                    [{"title": "설계", "agent": "designer", "ui": {"x": "a", "y": 1}}],        # bad ui
                    [{"title": "구현", "agent": "impl", "fanout": "slices"}],                  # fanout without produces
                    []):
            code, out, _ = self._save({"stages": bad, "dry": True})
            self.assertEqual(code, 400, (bad, out))

    def _skill_dir(self, base, name, md=True):
        d = os.path.join(base, "skills", name)
        os.makedirs(d)
        if md:
            with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
                f.write("secret-skill-body")

    def test_stage_skill(self):
        self._skill_dir(os.path.join(self.proj, ".claude"), "proj-ship")
        self._skill_dir(os.path.join(self.tmp, "home"), "home-ship")
        self._skill_dir(os.path.join(self.tmp, "home"), "proj-ship")            # project copy wins
        self._skill_dir(os.path.join(self.tmp, "home"), "no-md", md=False)
        self._skill_dir(os.path.join(self.tmp, "home"), "Bad_Name")
        self._skill_dir(os.path.join(self.tmp, "home", "sidereus-off"), "parked")
        out = self._list()
        self.assertEqual(out["skills"], [{"name": "proj-ship", "scope": "project"}, {"name": "home-ship", "scope": "user"}])
        self.assertNotIn("secret-skill-body", json.dumps(out))                 # names only, SKILL.md never read
        st = self._stages()
        code, out, _ = self._save({"stages": [dict(st[0], skill="nope")] + st[1:], "dry": True})
        self.assertEqual((code, out.get("err")), (400, "unknown skill nope"))
        code, out, _ = self._save({"stages": [dict(st[0], skill="Bad X")] + st[1:], "dry": True})
        self.assertEqual(code, 400)
        self.assertTrue(any(".skill" in e for e in out["errs"]), out)
        for sk in ("home-ship", "proj-ship"):
            code, out, _ = self._save({"stages": [dict(st[0], skill=sk)] + st[1:], "dry": False})
            self.assertEqual(code, 200, out)
            row = self._list()["pipelines"][0]["stages"][0]
            self.assertEqual(row["skill"], sk)                                   # _replace -> file -> _stage_row
        with open(self.file, encoding="utf-8") as f:
            self.assertEqual(list(json.load(f)["stages"][0])[:5], ["title", "agent", "task", "produces", "skill"])
        shutil.rmtree(os.path.join(self.proj, ".claude", "skills", "proj-ship"))   # uninstalled since: unchanged stage still saves
        st = self._stages()
        code, out, _ = self._save({"stages": [st[0], dict(st[1], retry=1)] + st[2:], "dry": False})
        self.assertEqual(code, 200, out)

    def _create(self, body, origin=ORIGIN):
        return post("/api/pipelines/create", dict({"proj": self.proj, "title": "", "template": "change"}, **body), origin=origin)

    def test_create_templates(self):
        for tpl in PN.TEMPLATES:
            name = "t-" + tpl
            code, out, _ = self._create({"name": name, "template": tpl, "dry": True})
            self.assertEqual(code, 200, (tpl, out))
            self.assertTrue(out["diff"].startswith("--- /dev/null"))
            code, out, _ = self._create({"name": name, "template": tpl, "dry": False})
            self.assertEqual(code, 200, (tpl, out))
            with open(os.path.join(self.proj, ".claude", "pipelines", name + ".json"), encoding="utf-8") as f:
                P = json.load(f)
            self.assertEqual(PS.validate(P, name), [])
        row = [r for r in self._list()["pipelines"] if r["name"] == "t-change"][0]
        # project has no sidereus-* agents -> general-purpose; the designer/impl names here do not match the template's
        self.assertEqual({s["agent"] for s in row["stages"]}, {"general-purpose"})

    def test_create_keeps_existing_agents_and_makes_dir(self):
        shutil.rmtree(os.path.join(self.proj, ".claude", "pipelines"))
        open(os.path.join(self.proj, ".claude", "agents", "sidereus-verifier.md"), "w", encoding="utf-8").close()
        code, out, _ = self._create({"name": "fresh", "title": "새 것", "dry": False})
        self.assertEqual(code, 200, out)
        with open(os.path.join(self.proj, ".claude", "pipelines", "fresh.json"), encoding="utf-8") as f:
            P = json.load(f)
        self.assertEqual(P["title"], "새 것")
        self.assertEqual([s["agent"] for s in P["stages"]][2], "sidereus-verifier")

    def test_import_from_other_project(self):
        other = os.path.join(self.tmp, "other")
        os.makedirs(other)
        with mock.patch.object(PP, "known_projects", lambda: [self.proj, other]):
            code, out, _ = self._create({"proj": other, "name": "copy", "from": {"proj": self.proj, "name": "demo"}, "dry": True})
            self.assertEqual(code, 200, out)
            self.assertEqual(out["replaced"], ["designer", "impl", "reviewer", "verifier"])     # missing in `other`
            self.assertEqual(self._create({"proj": other, "name": "copy", "from": {"proj": self.proj, "name": "demo"}, "dry": False})[0], 200)
            with open(os.path.join(other, ".claude", "pipelines", "copy.json"), encoding="utf-8") as f:
                P = json.load(f)
            self.assertEqual((P["name"], {s["agent"] for s in P["stages"]}), ("copy", {"general-purpose"}))
            self.assertEqual(PS.validate(P, "copy"), [])
            self.assertEqual(self._create({"proj": other, "name": "copy", "from": {"proj": self.proj, "name": "demo"}, "dry": True})[0], 409)
            for src in ({"proj": "/etc", "name": "demo"}, {"proj": self.proj, "name": "../x"}, {"proj": self.proj, "name": "nope"}):
                self.assertEqual(self._create({"proj": other, "name": "c2", "from": src, "dry": True})[0], 400, src)

    def test_rule_files_and_workflows_names_only(self):
        open(os.path.join(self.proj, "AGENTS.md"), "w", encoding="utf-8").close()
        os.makedirs(os.path.join(self.proj, ".claude", "workflows"))
        for n in ("flow.js", "bad name.js", "notes.txt"):
            open(os.path.join(self.proj, ".claude", "workflows", n), "w", encoding="utf-8").close()
        out = self._list()
        self.assertEqual((out["rule_files"], out["workflows"]), (["AGENTS.md"], ["flow.js"]))

    def test_suggest_listed_and_created(self):
        open(os.path.join(self.proj, ".claude", "agents", "fixer.md"), "w", encoding="utf-8").close()
        open(os.path.join(self.proj, ".claude", "agents", "implementer.md"), "w", encoding="utf-8").close()
        sug = self._list()["suggest"]
        self.assertEqual([x["name"] for x in sug], ["bugfix", "change"])
        self.assertTrue(sug[0]["suggest"])
        self.assertEqual(self._create({"name": "bf", "template": "suggest:nope", "dry": True})[0], 400)
        code, out, _ = self._create({"name": "bf", "template": "suggest:bugfix", "dry": False})
        self.assertEqual(code, 200, out)
        with open(os.path.join(self.proj, ".claude", "pipelines", "bf.json"), encoding="utf-8") as f:
            P = json.load(f)
        self.assertEqual((P["name"], P["stages"][1]["agent"]), ("bf", "fixer"))

    def test_chip_sources_are_allowed(self):
        # chips = known projects ∪ session cwd/repos ∪ Sidereus (80-structure.js strProjList) -> all must open, nothing else
        allowed = PP.allowed_projects()
        self.assertTrue({self.proj, self.repo} <= set(allowed))
        self.assertNotIn("/no/such/dir", allowed)
        self.assertEqual(get("/api/pipelines?proj=" + self.repo)[0], 200)
        self.assertEqual(get("/api/pipelines?proj=/etc")[0], 400)

    def _padd(self, path, url="/api/pipelines/projects/add", origin=ORIGIN):
        return post(url, {"path": path}, origin=origin)

    def test_project_add_remove(self):
        # «+ 프로젝트 불러오기»: an added folder stays a chip/allowed with no live session; remove drops the entry only
        extra = os.path.join(self.tmp, "extra")
        os.makedirs(extra)
        real = os.path.realpath(extra)
        with mock.patch.object(PP, "_allowed_cwds", lambda: {}):
            self.assertNotIn(real, PP.allowed_projects())
            code, out, _ = self._padd(extra + "/")
            self.assertEqual(code, 200, out)
            self.assertEqual(out["added"], [real])
            got = get("/api/pipelines")[1]
            self.assertIn(real, [x["path"] for x in got["projects"]])
            self.assertEqual(got["added"], [real])
            self.assertEqual(get("/api/pipelines?proj=" + real)[0], 200)
            code, out, _ = self._padd(real, "/api/pipelines/projects/remove")
            self.assertEqual((code, out["added"]), (200, []))
            self.assertTrue(os.path.isdir(extra))
            self.assertNotIn(real, PP.allowed_projects())
            self.assertEqual(self._padd(real, "/api/pipelines/projects/remove")[0], 400)

    def test_project_add_refusals(self):
        os.makedirs(os.path.join(self.tmp, "ok"))
        for path in ("rel/dir", os.path.join(self.tmp, "nope"), "/etc", "/", self.tmp, "", None):
            self.assertEqual(self._padd(path)[0], 400, path)
        for origin in (None, EVIL):
            self.assertEqual(self._padd(os.path.join(self.tmp, "ok"), origin=origin)[0], 403)
        self.assertEqual(PP._read_store(), [])

    def test_listing_stores_nothing(self):
        # listing/opening/saving never remembers a project (explicit list only)
        get("/api/pipelines")
        get("/api/pipelines?proj=" + self.repo)
        self._save({"stages": {"검증": {"model": ""}}, "dry": False})
        self.assertFalse(os.path.exists(PP._store_path()))

    def test_create_refusals(self):
        self.assertEqual(self._create({"name": "demo", "dry": True})[0], 409)          # exists: never overwrite
        self.assertEqual(self._create({"name": "demo", "dry": False})[0], 409)
        with open(self.file, encoding="utf-8") as f:
            self.assertEqual(f.read(), self.raw)
        for body in ({"name": "Bad Name"}, {"name": "x\n"}, {"name": "ok", "template": "nope"}, {"name": "ok", "title": "a\nb"}):
            self.assertEqual(self._create(dict(body, dry=False))[0], 400, body)
        self.assertEqual(self._create({"name": "ok", "proj": "/etc", "dry": False})[0], 403)
        for origin in (None, EVIL):
            self.assertEqual(self._create({"name": "ok", "dry": False}, origin=origin)[0], 403)
        self.assertFalse(os.path.exists(os.path.join(self.proj, ".claude", "pipelines", "ok.json")))

    def _del(self, body, origin=ORIGIN):
        return post("/api/pipelines/delete", dict({"proj": self.proj, "name": "demo"}, **body), origin=origin)

    def test_delete_dry_then_move(self):
        code, out, _ = self._del({"dry": True})
        self.assertEqual(code, 200, out)
        self.assertEqual(out["path"], self.file)
        self.assertEqual(out["to"], os.path.join(self.tmp, "bak", "20261001-120000", "proj--demo.json"))
        self.assertTrue(os.path.exists(self.file))                      # dry moves nothing
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "bak")))
        code, out, _ = self._del({"dry": False})
        self.assertEqual(code, 200, out)
        self.assertFalse(os.path.exists(self.file))
        with open(out["backup"], encoding="utf-8") as f:                 # moved, not deleted: undo = move it back
            self.assertEqual(f.read(), self.raw)
        self.assertTrue(out["backup"].startswith(os.path.join(self.tmp, "bak") + os.sep))
        self.assertEqual(self._list()["pipelines"], [])
        self.assertEqual(self._del({"dry": False})[0], 404)

    def test_delete_refusals(self):
        for body in ({"name": "../demo"}, {"name": "Demo"}, {"name": "demo\n"}, {"name": ""}, {"name": 3}):
            self.assertEqual(self._del(dict(body, dry=False))[0], 400, body)
        self.assertEqual(self._del({"proj": "/etc", "dry": False})[0], 403)
        self.assertEqual(self._del({"name": "nope", "dry": False})[0], 404)
        for origin in (None, EVIL):
            self.assertEqual(self._del({"dry": False}, origin=origin)[0], 403)
        out = os.path.join(self.tmp, "outside.json")                   # symlink pointing outside the project
        with open(out, "w", encoding="utf-8") as f:
            f.write("{}")
        os.symlink(out, os.path.join(self.proj, ".claude", "pipelines", "lnk.json"))
        self.assertEqual(self._del({"name": "lnk", "dry": False})[0], 400)
        self.assertTrue(os.path.exists(self.file) and os.path.exists(out))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "bak")))

    def test_drop_stage_model(self):
        code, out, _ = self._save({"stages": {"검증": {"model": ""}}, "dry": False})
        self.assertEqual(code, 200, out)
        with open(self.file, encoding="utf-8") as f:
            self.assertNotIn("model", json.load(f)["stages"][2])

    def test_refusals(self):
        for body in ({"stages": {"리뷰": {"task": "x"}}}, {"stages": {"리뷰": {"model": "gpt"}}},
                     {"stages": {"리뷰": {"agent": "Bad Name"}}}, {"stages": {"배포": {"model": "opus"}}},
                     {"defaults": {"retry": 2}}, {"stages": {}}):
            code, out, _ = self._save(dict(body, dry=False))
            self.assertEqual(code, 400, (body, out))
        code, out, _ = self._save({"stages": {"리뷰": {"model": "opus"}}, "base": "stale", "dry": False})
        self.assertEqual(code, 409)
        code, out, _ = post("/api/pipelines/save", {"proj": self.proj, "name": "../x", "base": ""}, origin=ORIGIN)
        self.assertEqual(code, 400)
        with open(self.file, encoding="utf-8") as f:
            self.assertEqual(f.read(), self.raw)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "bak")))

    def test_origin_required(self):
        for origin in (None, EVIL):
            code, out, _ = self._save({"stages": {"리뷰": {"model": "opus"}}, "dry": False}, origin=origin)
            self.assertEqual(code, 403)
        with open(self.file, encoding="utf-8") as f:
            self.assertEqual(f.read(), self.raw)

    def test_feature_off_404(self):
        with mock.patch.object(F, "_TOGGLES", {"pipeline": False}):
            self.assertEqual(get("/api/pipelines"), (404, {"error": "feature off"}))
            code, out, _ = post("/api/pipelines/save", {"proj": self.proj}, origin=ORIGIN)
            self.assertEqual((code, out), (404, {"error": "feature off"}))


if __name__ == "__main__":
    unittest.main()
