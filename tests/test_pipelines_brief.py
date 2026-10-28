"""SessionStart hook hooks/pipelines_brief.py: one line per pipeline, missing agents, size cap, empty / bad files skipped. Tmp dirs only."""
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

_P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "pipelines_brief.py")
_spec = importlib.util.spec_from_file_location("pipelines_brief", _P)
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)


def _pipe(name, title="변경", use=None, agents=("designer", "impl")):
    P = {"v": 1, "name": name, "title": title, "rules": "secret-rules", "defaults": {"model": "inherit", "retry": 0},
         "stages": [{"title": "설계", "agent": agents[0], "task": "secret-task"}, {"title": "구현", "agent": agents[1]}]}
    if use:
        P["use"] = use
    return P


class Brief(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.dir = os.path.join(self.tmp, ".claude", "pipelines")
        os.makedirs(self.dir)
        self.user = os.path.join(self.tmp, "home-claude")
        self.cfg = os.path.join(self.tmp, "config.local.json")   # ⚠never the live Sidereus config
        self.bdir = os.path.join(self.tmp, "plbrief")   # ⚠never the live data dir
        for p in (mock.patch.object(H, "CLAUDE_DIR", self.user), mock.patch.object(H, "CONFIG_PATH", self.cfg),
                  mock.patch.object(H, "BRIEF_DIR", self.bdir)):
            p.start()
            self.addCleanup(p.stop)

    def _w(self, name, P):
        with open(os.path.join(self.dir, name + ".json"), "w", encoding="utf-8") as f:
            f.write(P if isinstance(P, str) else json.dumps(P, ensure_ascii=False))

    def _agent(self, root, name):
        d = os.path.join(root, "agents")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name + ".md"), "w", encoding="utf-8") as f:
            f.write("---\nname: %s\n---\n" % name)

    def test_lines_and_instruction(self):
        self._agent(os.path.join(self.tmp, ".claude"), "designer")
        self._agent(self.user, "impl")
        self._w("change", _pipe("change", use="viewer UI or server changes"))
        self._w("solo", _pipe("solo", title="혼자", agents=("Explore", "general-purpose")))
        t = H.brief(self.tmp)
        self.assertIn("- change — 변경 · when: viewer UI or server changes · stages: 설계 → 구현\n", t)
        self.assertIn("- solo — 혼자 · stages: 설계 → 구현\n", t)
        self.assertNotIn("missing", t)   # project, user and builtin agents all count as present
        self.assertIn("[pl:<name>/<stage title>]", t)
        self.assertIn("general-purpose", H.HOW)
        self.assertNotIn("secret", t)   # metadata only

    def test_builtin_hidden_only_in_sidereus_repo(self):
        self._w("change", _pipe("change"))
        self._w("security-checks", dict(_pipe("security-checks"), builtin=True))
        os.makedirs(os.path.join(self.tmp, "sidereus"))
        open(os.path.join(self.tmp, "sidereus", "config.py"), "w", encoding="utf-8").close()
        with mock.patch.object(H, "CODE_DIR", self.tmp):
            t = H.brief(self.tmp)
            self.assertIn("- change —", t)
            self.assertNotIn("security-checks", t)
        other = os.path.join(self.tmp, "code")   # ⚠another repo: the key is ignored, the file is offered
        os.makedirs(os.path.join(other, "sidereus"))
        open(os.path.join(other, "sidereus", "config.py"), "w", encoding="utf-8").close()
        with mock.patch.object(H, "CODE_DIR", other):
            self.assertIn("security-checks", H.brief(self.tmp))
        with mock.patch.object(H, "CODE_DIR", os.path.join(self.tmp, "nowhere")):   # unresolved = not hidden
            self.assertIn("security-checks", H.brief(self.tmp))

    def test_missing_agents_listed(self):
        self._agent(self.user, "impl")
        self._w("change", _pipe("change", agents=("ghost", "impl")))
        self._w("two", _pipe("two", agents=("x-a", "x-b")))
        t = H.brief(self.tmp)
        self.assertIn("- change — 변경 · stages: 설계 → 구현 · missing agents (run as general-purpose): ghost\n", t)
        self.assertIn("missing agents (run as general-purpose): x-a, x-b", t)
        self.assertNotIn("impl", t.split("\n")[1])

    def test_orchestrator_agents_not_missing(self):
        self._w("change", _pipe("change", agents=("main", "claude")))
        self._w("two", _pipe("two", agents=("main", "ghost")))
        t = H.brief(self.tmp)
        self.assertIn("- change — 변경 · stages: 설계 → 구현\n", t)
        self.assertIn("missing agents (run as general-purpose): ghost", t)
        self.assertNotIn(": main", t)

    def test_stage_skill_shown_by_name(self):
        P = _pipe("ship")
        P["stages"][1]["skill"] = "sidereus-ship"
        P["stages"][0]["skill"] = "bad name;x"                  # not a file-stem shape: not echoed
        self._w("ship", P)
        t = H.brief(self.tmp)
        self.assertIn("stages: 설계 → 구현 (skill sidereus-ship)", t)
        self.assertNotIn("bad name", t)
        self.assertIn("Follow the <skill> skill.", t)

    def test_six_korean_pipelines_fit(self):
        titles = ["요구사항 정리", "설계와 분할", "구현 조각별", "검증 전체", "리뷰와 보안", "라이브 확인"]
        for k in range(6):
            self._agent(self.user, "agent-%d" % k)
        for i in range(6):
            P = {"v": 1, "name": "pipe-%d" % i, "title": "한국어 파이프라인 제목 %d" % i, "use": "뷰어 화면이나 서버를 바꿀 때 쓰는 흐름입니다",
                 "rules": "SECRET-RULES-%d" % i,
                 "stages": [{"title": t, "agent": "agent-%d" % k, "task": "SECRET-TASK-%d" % k} for k, t in enumerate(titles)]}
            self._w("pipe-%d" % i, P)
        t = H.brief(self.tmp)
        self.assertLessEqual(len(t.encode("utf-8")), H.MAX_BYTES)
        self.assertNotIn("more (see", t)
        for i in range(6):
            self.assertIn("- pipe-%d — " % i, t)
        self.assertNotIn("SECRET", t)

    def test_pick_line_once_and_strict_only_with_policy(self):
        self._w("ok", _pipe("ok"))
        t = H.brief(self.tmp)
        self.assertEqual(t.count(H.PICK), 1)
        self.assertNotIn(H.STRICT, t)
        for bad in ("{bad", json.dumps({"enforce": "off"}), "[1]"):
            self._w("_policy", bad)
            self.assertNotIn(H.STRICT, H.brief(self.tmp), bad)
        self._w("_policy", {"enforce": "writes"})
        t = H.brief(self.tmp)
        self.assertEqual(t.count(H.STRICT), 1)
        self.assertEqual(t.count(H.PICK), 1)
        self.assertNotIn("_policy", t)   # not listed as a pipeline
        self._mode({"mode": "ask"})
        self.assertIn(H.STRICT, H.brief(self.tmp))

    def test_no_pipelines_prints_nothing(self):
        self.assertEqual(H.brief(self.tmp), "")
        self.assertEqual(H.brief(os.path.join(self.tmp, "nope")), "")
        self.assertEqual(H.brief("relative/path"), "")
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps({"cwd": self.tmp}))), mock.patch("sys.stdout", out):
            self.assertEqual(H.main(), 0)
        self.assertEqual(out.getvalue(), "")

    def test_bad_json_and_reserved_names_skipped(self):
        self._w("broken", "{not json")
        self._w("list", "[1, 2]")
        self._w("_defaults", {"설계": "x"})
        self.assertEqual(H.brief(self.tmp), "")
        self._w("ok", _pipe("ok"))
        t = H.brief(self.tmp)
        self.assertIn("- ok — ", t)
        self.assertNotIn("broken", t)

    def test_size_cap(self):
        for i in range(30):
            self._w("p%02d" % i, _pipe("p%02d" % i, title="긴 제목 " * 10, use="u" * 120))
        t = H.brief(self.tmp)
        self.assertLessEqual(len(t.encode("utf-8")), H.MAX_BYTES)
        self.assertIn("more (see .claude/pipelines/)", t)
        self.assertTrue(t.endswith(H.HOW))

    def test_main_json_shape_and_bad_stdin(self):
        self._w("ok", _pipe("ok"))
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps({"cwd": self.tmp}))), mock.patch("sys.stdout", out):
            self.assertEqual(H.main(), 0)
        o = json.loads(out.getvalue())["hookSpecificOutput"]
        self.assertEqual(o["hookEventName"], "SessionStart")
        self.assertIn("- ok — ", o["additionalContext"])
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO("garbage")), mock.patch("sys.stdout", out):
            self.assertEqual(H.main(), 0)
        self.assertEqual(out.getvalue(), "")

    def _mode(self, v):
        with open(self.cfg, "w", encoding="utf-8") as f:
            f.write(v if isinstance(v, str) else json.dumps({"pipeline_apply": v}))

    def test_apply_modes(self):
        self._w("ok", _pipe("ok"))
        self.assertTrue(H.brief(self.tmp).endswith(H.HOW))                  # no config = auto
        self._mode({"mode": "ask"})
        t = H.brief(self.tmp)
        self.assertTrue(t.endswith(H.HOW_ASK) and "AskUserQuestion" in t and "- ok — " in t)
        self._mode({"mode": "off"})
        self.assertEqual(H.brief(self.tmp), "")
        self._mode({"mode": "off", "projects": {self.tmp: "ask"}})         # exact-cwd override wins
        self.assertTrue(H.brief(self.tmp).endswith(H.HOW_ASK))
        self._mode({"mode": "ask", "projects": {self.tmp + "/sub": "off"}})
        self.assertTrue(H.brief(self.tmp).endswith(H.HOW_ASK))

    def test_bad_config_is_auto(self):
        self._w("ok", _pipe("ok"))
        for bad in ("garbage", "[1]", json.dumps({"pipeline_apply": "off"}), json.dumps({"pipeline_apply": {"mode": "loud"}}),
                    json.dumps({"pipeline_apply": {"mode": "off", "projects": "x"}})):
            self._mode(bad)
            self.assertTrue(H.brief(self.tmp).endswith(H.HOW), bad)

    def test_ask_size_cap(self):
        self._mode({"mode": "ask"})
        for i in range(30):
            self._w("p%02d" % i, _pipe("p%02d" % i, title="긴 제목 " * 10, use="u" * 120))
        t = H.brief(self.tmp)
        self.assertLessEqual(len(t.encode("utf-8")), H.MAX_BYTES)
        self.assertTrue(t.endswith(H.HOW_ASK))

    def _run(self, event, sid="sess-0001"):
        out = io.StringIO()
        ev = {"cwd": self.tmp, "session_id": sid, "hook_event_name": event}
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out):
            self.assertEqual(H.main(), 0)
        v = out.getvalue()
        return json.loads(v)["hookSpecificOutput"] if v else None

    def test_rebrief_only_on_change(self):
        self._w("ok", _pipe("ok"))
        o = self._run("SessionStart")
        self.assertEqual(o["hookEventName"], "SessionStart")
        self.assertIsNone(self._run("UserPromptSubmit"))                    # unchanged: silent
        self._w("db", _pipe("db"))                                          # created mid-session
        o = self._run("UserPromptSubmit")
        self.assertEqual(o["hookEventName"], "UserPromptSubmit")
        self.assertIn("- db — ", o["additionalContext"])
        self.assertIsNone(self._run("UserPromptSubmit"))                    # once
        P = _pipe("db")
        P["stages"][0]["task"] = "other secret"                             # same names + titles
        self._w("db", P)
        self.assertIsNone(self._run("UserPromptSubmit"))
        P["stages"][1]["title"] = "검증 단계"                                # stage title edited
        self._w("db", P)
        self.assertIn("검증 단계", self._run("UserPromptSubmit")["additionalContext"])
        os.remove(os.path.join(self.dir, "db.json"))                        # removed
        self.assertNotIn("- db — ", self._run("UserPromptSubmit")["additionalContext"])
        with open(os.path.join(self.bdir, "sess-0001"), encoding="utf-8") as f:
            self.assertNotIn("ok", f.read().replace("\"s\"", "").replace("\"c\"", ""))   # hashes only

    def test_prompt_without_record(self):
        self.assertIsNone(self._run("UserPromptSubmit", "sess-0002"))       # no pipelines: silent
        self._w("ok", _pipe("ok"))
        self.assertIn("- ok — ", self._run("UserPromptSubmit", "sess-0003")["additionalContext"])
        self.assertIsNone(self._run("UserPromptSubmit", "sess-0003"))
        self.assertIsNone(self._run("UserPromptSubmit", "../bad"))          # bad sid: prompts stay silent


if __name__ == "__main__":
    unittest.main()
