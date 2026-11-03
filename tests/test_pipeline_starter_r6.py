"""R6: «Start with recommended setup» — three default pipelines, gate detected or given, O_EXCL, policy only if ticked."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests import _load

_load.load()
from sidereus import pipeline_schema as PS, pipeline_starter as ST, routes_post  # noqa: E402

NAMES = ("quick-fix", "change", "bugfix")


class Starter(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-starter-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(self.proj)
        self.agents = []
        for k, v in (("_proj_ok", lambda p: p == self.proj), ("_agents", lambda p: self.agents)):
            m = mock.patch.object(ST, k, v)
            m.start()
            self.addCleanup(m.stop)

    def w(self, rel, text=""):
        fp = os.path.join(self.proj, rel)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(text)

    def pdir(self):
        return os.path.join(self.proj, ".claude", "pipelines")

    def test_detect_test(self):
        self.assertIsNone(ST.detect_test(self.proj))
        self.w("Makefile", "build:\n\ttrue\ntest: build\n\ttrue\n")
        self.assertEqual(ST.detect_test(self.proj), "make test")
        self.w("go.mod", "module x\n")
        self.assertEqual(ST.detect_test(self.proj), "go test ./...")
        self.w("Cargo.toml", "")
        self.assertEqual(ST.detect_test(self.proj), "cargo test")
        os.makedirs(os.path.join(self.proj, "tests"))
        self.assertEqual(ST.detect_test(self.proj), "python3 -m pytest -q")
        self.w("package.json", json.dumps({"scripts": {"test": 'echo "Error: no test specified" && exit 1'}}))
        self.assertEqual(ST.detect_test(self.proj), "python3 -m pytest -q")   # npm init stub is not a test
        self.w("package.json", json.dumps({"scripts": {"test": "jest"}}))
        self.assertEqual(ST.detect_test(self.proj), "npm test")

    def test_resolve_agent(self):
        self.assertEqual(ST.resolve_agent("review", ["x-reviewer", "a-fixer"]), "x-reviewer")
        self.assertEqual(ST.resolve_agent("review", []), "general-purpose")
        self.assertEqual(ST.resolve_agent("nope", ["x-reviewer"]), "general-purpose")

    def test_dry_no_gate_then_write_valid_files(self):
        self.agents = [{"name": "my-reviewer", "scope": "project"}]
        c, b = ST.starter({"proj": self.proj})
        self.assertEqual((c, b["dry"], b["gate"], b["detected"]), (200, True, None, None))
        self.assertEqual([f["rel"] for f in b["files"]], [".claude/pipelines/%s.json" % n for n in NAMES])
        self.assertNotIn('"gate"', b["diff"])
        self.assertFalse(os.path.exists(self.pdir()))   # dry writes nothing
        c, b = ST.starter({"proj": self.proj, "dry": False})
        self.assertEqual([f["state"] for f in b["files"]], ["written"] * 3)
        self.assertEqual(sorted(os.listdir(self.pdir())), sorted(n + ".json" for n in NAMES))   # no _policy.json, no settings
        for n in NAMES:
            with open(os.path.join(self.pdir(), n + ".json"), encoding="utf-8") as f:
                P = json.load(f)
            self.assertEqual(PS.validate(P, n), [], n)
            self.assertTrue(all("gate" not in s for s in P["stages"]))
            self.assertTrue(all(ord(ch) < 128 for ch in json.dumps(P, ensure_ascii=False)), n)   # English titles
        with open(os.path.join(self.pdir(), "bugfix.json"), encoding="utf-8") as f:
            bf = json.load(f)
        self.assertEqual([s["title"] for s in bf["stages"]], ["Reproduce", "Cause", "Fix", "Regression"])
        self.assertEqual(bf.get("catch"), "person")
        with open(os.path.join(self.pdir(), "change.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["stages"][-1]["agent"], "my-reviewer")

    def test_detected_gate_and_override(self):
        self.w("go.mod", "module x\n")
        b = ST.starter({"proj": self.proj})[1]
        self.assertEqual((b["gate"], b["detected"]), ("go test ./...", "go test ./..."))
        self.assertIn('"gate": "go test ./..."', b["diff"])
        b = ST.starter({"proj": self.proj, "gate": "make check"})[1]
        self.assertEqual((b["gate"], b["detected"]), ("make check", "go test ./..."))
        self.assertNotIn("go test", b["diff"])
        for bad in ("", " ", "a\nb", "x" * 201, 3):
            self.assertEqual(ST.starter({"proj": self.proj, "gate": bad})[0], 400, bad)
        ST.starter({"proj": self.proj, "gate": "make check", "dry": False})
        with open(os.path.join(self.pdir(), "bugfix.json"), encoding="utf-8") as f:
            self.assertEqual([s.get("gate") for s in json.load(f)["stages"]], [None, None, "make check", "make check"])

    def test_policy_only_when_ticked_and_existing_kept(self):
        self.w(".claude/pipelines/change.json", "mine\n")
        b = ST.starter({"proj": self.proj, "policy": True})[1]
        self.assertEqual([f["state"] for f in b["files"]], ["new", "exists", "new", "new"])
        self.assertNotIn("change.json", b["diff"])
        ST.starter({"proj": self.proj, "policy": True, "dry": False})
        with open(os.path.join(self.pdir(), "change.json"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "mine\n")   # never overwritten
        with open(os.path.join(self.pdir(), "_policy.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"enforce": "writes"})
        b = ST.starter({"proj": self.proj, "policy": True, "dry": False})[1]
        self.assertEqual({f["state"] for f in b["files"]}, {"exists"})

    def test_guards(self):
        self.assertEqual(ST.starter({"proj": "/elsewhere"})[0], 403)
        self.assertEqual(ST.starter(None)[0], 400)
        out = os.path.join(self.tmp, "out")
        os.makedirs(out)
        os.symlink(out, os.path.join(self.proj, ".claude"))
        self.assertEqual(ST.starter({"proj": self.proj, "dry": False})[0], 400)   # symlinked .claude leaves the project
        self.assertEqual(os.listdir(out), [])   # nothing created through the link

    def test_route_wired_behind_origin(self):
        with open(routes_post.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('"/api/pipelines/starter": _p_pipelines_save', src)
        self.assertIn('"/api/pipelines/starter": pipeline_starter', src)


if __name__ == "__main__":
    unittest.main()
