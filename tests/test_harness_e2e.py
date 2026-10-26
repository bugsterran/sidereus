"""Harness end-to-end replays (tests/fixtures/harness_e2e/<case>/case.json): real recorder → harness_plat._results → flow node.

Guard: hooks/pl_flow.py main() (which loads hooks/pl_guard.py) writes plmark/<sid>.runs.json. Gate/Kept: scripts/evidence_rec.py
writes evidence.jsonl rows as check.sh does. Tmp dirs only, fixed clock; git only in a temp repo with fixed dates.
"""
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tests._clock import NOW
from tests._load import ROOT, load, sidereus

load()
HP, HF, HE, HT = sidereus("harness_plat"), sidereus("harness_flow"), sidereus("harness_evidence"), sidereus("harness_trail")
FX = os.path.join(ROOT, "tests", "fixtures", "harness_e2e")
SID = "e2e-sess-0001"
T0 = NOW - 900


def _mod(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


H = _mod("pl_flow_e2e_t", "hooks/pl_flow.py")
REC = _mod("evidence_rec_e2e_t", "scripts/evidence_rec.py")


def case(name):
    with open(os.path.join(FX, name, "case.json"), encoding="utf-8") as f:
        return json.load(f)


def screen_line(node):
    """English text the Harness strip draws for `node` (web/js/47c-harness-flow.js hnFLine)."""
    from tests.test_harness_flow_js import _js
    html = _js("LANG = 'en'; console.log(JSON.stringify(hnFLine(%s)))" % json.dumps(node))
    return re.sub(r"<[^>]*>", "", html)   # visible text only: wrapper spans are layout, the counts are the claim


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="hfe2e-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.proj = os.path.join(self.tmp, "proj")
        self.marks = os.path.join(self.tmp, "plmark")
        self.evf = os.path.join(self.tmp, "evidence.jsonl")
        os.makedirs(self.marks)
        os.makedirs(self.proj)
        self.t = T0
        env = dict((k, v) for k, v in os.environ.items() if k != "SIDEREUS_EVIDENCE")
        for obj, k, v in ((H, "MARK_DIR", self.marks), (H, "CONFIG_PATH", os.path.join(self.tmp, "cfg.json")),
                          (H, "_now", lambda: self.t), (H, "CLAUDE_DIR", os.path.join(self.tmp, "u")), (H, "HOME_DIR", self.tmp),
                          (H, "DIRS_DIR", os.path.join(self.tmp, "plbrief")), (H, "DATA_DIR", self.tmp),
                          (H, "_spawn", lambda argv: None), (HF, "HF_DIR", self.marks), (HF, "_now", lambda: NOW),
                          (HE, "EV_FILE", self.evf), (HE, "_now", lambda: NOW), (HT, "_now", lambda: NOW)):
            p = mock.patch.object(obj, k, v)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(os.environ, env, clear=True)
        p.start()
        self.addCleanup(p.stop)
        for c in (HF._HF_CACHE, HT._TR_CACHE, HE._CM_CACHE):
            c.clear()
            self.addCleanup(c.clear)

    def nodes(self):
        fl = HP._results(self.proj)["flow"]
        self.assertEqual(len(fl), 1)
        return dict((n["k"], n) for n in fl[0]["nodes"])

    def record(self, mode, rc, steps, head="", dirty=False, ts=NOW):
        """One check.sh evidence row through scripts/evidence_rec.py (the recorder check.sh's EXIT trap calls)."""
        tsv = os.path.join(self.tmp, "steps.tsv")
        with open(tsv, "w", encoding="utf-8") as f:
            f.write("".join("%s\t%d\t%d\t%d\t%d\n" % tuple(s) for s in steps))
        REC.main([self.evf, mode, str(rc), self.proj, head, "1" if dirty else "0", tsv], ts=ts)


class Cases(unittest.TestCase):
    """Every case carries the self-check fields and a pair with the opposite outcome under the same guard."""

    def test_fields_and_pairs(self):
        names = sorted(n for n in os.listdir(FX) if os.path.isdir(os.path.join(FX, n)))
        with open(os.path.join(FX, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        for n in names:
            fx = case(n)
            self.assertEqual([k for k in ("guard", "situation", "expect", "pair") if not isinstance(fx.get(k), str)], [], n)
            self.assertIn(fx["guard"], ("guard", "gate", "keep"), n)
            p = case(fx["pair"])
            self.assertEqual(p["guard"], fx["guard"], n)
            self.assertNotEqual(p["expect"], fx["expect"], n)
            # mutual, or a shared control whose own partner is another case with this case's outcome
            self.assertTrue(p["pair"] == n or case(p["pair"])["expect"] == fx["expect"], n)
            self.assertIn("`%s`" % n, readme, n)


class Guard(_Base):
    """R1: the guard hook's deny reaches the guard node."""

    def replay(self, fx):
        pipe = fx["pipe"]
        os.makedirs(os.path.join(self.proj, ".claude", "pipelines"))
        with open(os.path.join(self.proj, ".claude", "pipelines", pipe["name"] + ".json"), "w", encoding="utf-8") as f:
            json.dump(pipe, f)
        agents = dict((s["title"], s["agent"]) for s in pipe["stages"])
        denied = []
        for e in fx["ev"]:
            self.t += 10
            if "check" in e:   # the stage's gate run, recorded by check.sh's recorder
                self.record(e["check"]["mode"], e["check"]["rc"], [["tests", e["check"]["rc"], 10, 0, 1]], ts=self.t)
                continue
            if e["tool"] == "Bash":
                ti = {"command": e["cmd"], "description": e.get("desc", "x")}
            else:
                ti = {"description": "[pl:%s/%s] x" % (pipe["name"], e["stage"]), "subagent_type": agents[e["stage"]]}
            ev = {"hook_event_name": "PreToolUse" if e["e"] == "pre" else "PostToolUse", "tool_name": e["tool"],
                  "session_id": SID, "cwd": self.proj, "tool_input": ti}
            if e["e"] == "post":
                ev["tool_response"] = {"content": [{"type": "text", "text": "ok"}]}
            out = io.StringIO()
            with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out):
                H.main()
            o = json.loads(out.getvalue())["hookSpecificOutput"] if out.getvalue() else {}
            if e["e"] == "pre":
                denied.append(int(o.get("permissionDecision") == "deny"))
        self.assertEqual(denied, [e["denied"] for e in fx["ev"] if e.get("e") == "pre"])
        fp = os.path.join(self.marks, SID + ".runs.json")
        os.utime(fp, (NOW, NOW))
        return self.nodes()["guard"]

    def run_case(self, name):
        fx = case(name)
        g = self.replay(fx)
        self.assertEqual("blocked" if g["v"]["deny"] else "allowed", fx["expect"])
        want = fx["node"]["guard"]
        self.assertEqual((g["st"], g["v"]["deny"]), (want["st"], want["deny"]))
        self.assertEqual([r["code"] for r in g["rec"] if r["k"] == "deny"], want["codes"])
        self.assertEqual(screen_line(g), want["text"])

    def test_jump(self):
        self.run_case("guard-jump")

    def test_jump_declared(self):
        self.run_case("guard-jump-declared")

    def test_commit_before_gate(self):
        self.run_case("guard-commit")

    def test_commit_after_fail(self):
        self.run_case("guard-commit-after-fail")

    def test_commit_after_pass(self):
        self.run_case("guard-commit-after-pass")

    def test_skip_of_required_gate(self):
        self.run_case("guard-skip-required")

    def test_skip_declared(self):
        self.run_case("guard-skip-declared")


class Gate(_Base):
    """R2: check.sh evidence rows reach the gate node; Red->Green only after a FAIL."""

    def setUp(self):
        super(Gate, self).setUp()
        os.makedirs(os.path.join(self.proj, ".git"))   # git root marker only; every git read fails and is skipped

    def run_case(self, name):
        fx = case(name)
        for r in fx["rows"]:
            self.record(r["mode"], r["rc"], r["steps"], head="abc1234", ts=NOW - 300 + r["dt"])
        g = self.nodes()["gate"]
        self.assertEqual("r2g" if g["v"]["r2g"] else "no r2g", fx["expect"])
        want = fx["node"]["gate"]
        self.assertEqual((g["st"], g["v"]["r2g"], g["v"]["rows"]), (want["st"], want["r2g"], want["rows"]))

    def test_red_green(self):
        self.run_case("gate-red-green")

    def test_pass_only(self):
        self.run_case("gate-pass-only")


class Kept(_Base):
    """R3: a PASS at commit A, judged by harness_trail against a real temp repo, reaches the keep node."""

    def git(self, *args):
        env = {"PATH": os.environ.get("PATH", ""), "HOME": self.tmp, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
               "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
               "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        return subprocess.run(["git", "-C", self.proj] + list(args), env=env, check=True, capture_output=True,
                              text=True, encoding="utf-8").stdout.strip()

    def run_case(self, name):
        fx = case(name)
        self.git("init", "-q")
        ts = NOW - 600
        for i, s in enumerate(fx["steps"]):
            ts += 60
            if "commit" in s:
                for fn, body in s["commit"].items():
                    with open(os.path.join(self.proj, fn), "w", encoding="utf-8") as f:
                        f.write(body)
                self.git("add", "-A")
                self.git("commit", "-q", "--allow-empty", "-m", "c%d" % i)
            else:
                head = self.git("rev-parse", "--short", "HEAD")   # same as check.sh
                self.record(s["check"]["mode"], s["check"]["rc"], [["tests", s["check"]["rc"], 10, 0, 1]], head=head, ts=ts)
        k = self.nodes()["keep"]
        self.assertEqual((k["v"] or {}).get("state"), fx["expect"])
        want = fx["node"]["keep"]
        self.assertEqual((k["st"], (k["v"] or {}).get("state")), (want["st"], want["state"]))

    def test_held(self):
        self.run_case("keep-held")

    def test_reverted(self):
        self.run_case("keep-reverted")


if __name__ == "__main__":
    unittest.main()
