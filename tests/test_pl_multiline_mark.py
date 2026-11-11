"""Shell markers on a later line of a multi-line command (pi): hooks/pl_mark.py and hooks/pl_flow.py. Tmp dirs only."""
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

_HOOKS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks")


def _load(name):
    spec = importlib.util.spec_from_file_location(name + "_multiline_t", os.path.join(_HOOKS, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


M = _load("pl_mark")
F = _load("pl_flow")
SID = "c0ffee00-1234-5678-9abc-def012345679"
PL = "security-checks"
PIPE = {"stages": [{"title": "scan", "agent": "main"}, {"title": "review", "agent": "main"}]}
END = 'cd /tmp\npython3 scan.py --last\necho "[pl-end:%s/review]"\necho "[pl:-]"' % PL


class MarkMatch(unittest.TestCase):
    def test_block_identical(self):
        def blk(mod):
            with open(mod.__file__, encoding="utf-8") as f:
                s = f.read()
            return s[s.index("# --- later-line marker"):s.index("# --- end later-line marker ---")]
        self.assertEqual(blk(M), blk(F))

    def test_cases(self):
        for mod in (M, F):
            mm = mod.mark_match
            m = mm(END)
            self.assertEqual((m.group(1), m.group(3), m.group(4)), ("-end", PL, "review"))   # first marker wins
            self.assertEqual(mm("ls\n  printf '[pl:x/a]'").group(3), "x")
            self.assertIsNone(mm('ls\ngrep "[pl:x/y]" f'))
            self.assertIsNone(mm('ls\necho "done [pl-end:x/y]"'))
            self.assertIsNone(mm('ls\n[pl-end:x/y]'))
            self.assertIsNone(mm("cat > f <<'EOF'\necho \"[pl-end:x/y]\"\nEOF"))
            self.assertEqual(mm("cat > f <<EOF\nbody\nEOF\necho [pl-end:x/y]").group(4), "y")   # after the heredoc ends
            self.assertEqual(mm('ls\necho "[pl-skip:x/a] r"\necho "[pl-end:x/y]"').group(4), "y")
            self.assertEqual(mm('echo "[pl:x/a]"\necho "[pl-end:x/y]"').group(4), "a")   # line 1 unchanged

    def test_segments(self):
        for mod in (M, F):
            mm = mod.mark_match
            self.assertEqual(mm('cd /d; echo "[pl:p/s]"').group(3), "p")
            self.assertEqual(mm('cd /d && echo "[pl-end:p/s]"').group(1), "-end")
            self.assertEqual(mm('cd /d\na | b; echo "[pl-end:p/s]"').group(4), "s")
            self.assertEqual(mm('cd /d || echo "[pl:p/a]"; echo "[pl:p/b]"').group(4), "a")   # first wins
            for c in ('grep "[pl:p/s]" f; true', 'a | grep "[pl:p/s]"', 'echo "x; [pl:p/s]"', "ls; echo 'a;' [pl:p/s]",
                      'ls # ; echo "[pl:p/s]"', 'ls\na | echo "[pl:p/s]"'):
                self.assertIsNone(mm(c), c)


class Hooks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(self.proj, ".claude", "pipelines"))
        os.makedirs(os.path.join(self.proj, ".git"))   # the ledger is written for git repos only
        with open(os.path.join(self.proj, ".claude", "pipelines", PL + ".json"), "w", encoding="utf-8") as f:
            json.dump(PIPE, f)
        self.marks = os.path.join(self.tmp, "plmark")
        self.t = 1000.0
        cfg = os.path.join(self.tmp, "config.local.json")
        common = (("MARK_DIR", self.marks), ("CONFIG_PATH", cfg), ("HOME_DIR", self.tmp), ("DATA_DIR", self.tmp),
                  ("DIRS_DIR", os.path.join(self.tmp, "plbrief")))
        flow = (("_now", lambda: self.t), ("CLAUDE_DIR", os.path.join(self.tmp, "uc")), ("_spawn", lambda argv: None),
                ("CLAUDE_JSON", os.path.join(self.tmp, ".claude.json")), ("PROJ_STORE", os.path.join(self.tmp, "pp.json")),
                ("_head", lambda proj: "abc1234"))
        for mod, pairs in ((M, common), (F, common + flow)):
            for k, v in pairs:
                if hasattr(mod, k):
                    p = mock.patch.object(mod, k, v)
                    p.start()
                    self.addCleanup(p.stop)

    def _run(self, mod, event, cmd):
        ev = {"hook_event_name": event, "session_id": SID, "cwd": self.proj, "tool_name": "bash",
              "tool_input": {"command": cmd}}
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(ev))), mock.patch("sys.stdout", out):
            mod.main(["--platform", "pi"])
        return out.getvalue()

    def _runs(self):
        with open(os.path.join(self.marks, SID + ".runs.json"), encoding="utf-8") as f:
            return json.load(f)["runs"]

    def _rows(self):
        d = os.path.join(self.tmp, "eval")
        rows = []
        for root, _dirs, files in os.walk(d):
            for n in files:
                if n == "runs.jsonl":
                    with open(os.path.join(root, n), encoding="utf-8") as f:
                        rows += [json.loads(x) for x in f if x.strip()]
        return rows

    def _stage(self, title, end_cmd):
        for ev in ("PreToolUse", "PostToolUse"):
            self._run(F, ev, 'echo "[pl:%s/%s]"' % (PL, title))
        self.t += 1
        for ev in ("PreToolUse", "PostToolUse"):
            self._run(F, ev, end_cmd)
        self.t += 1

    def test_flow_closes_on_later_line_end(self):
        self._stage("scan", 'echo "[pl-end:%s/scan]"' % PL)
        self.assertFalse(self._runs()[PL].get("end"))
        self._stage("review", END)
        self.assertTrue(self._runs()[PL].get("end"))
        self.assertEqual(len(self._rows()), 1)

    def test_flow_opens_on_one_line_segment(self):
        self._run(F, "PreToolUse", 'cd %s; echo "[pl:%s/scan]"' % (self.proj, PL))
        self.assertEqual(self._runs()[PL]["st"]["scan"]["s"], "run")

    def test_flow_ignores_grep_on_later_line(self):
        self._stage("scan", 'echo "[pl-end:%s/scan]"' % PL)
        self._stage("review", 'ls\ngrep "[pl-end:%s/review]" f' % PL)
        self.assertFalse(self._runs()[PL].get("end"))
        self.assertEqual(self._rows(), [])

    def test_mark_later_line(self):
        p = os.path.join(self.marks, SID + ".json")
        self._run(M, "PreToolUse", 'cd x\necho "[pl:%s/scan]"' % PL)
        with open(p, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["title"], "scan")
        self._run(M, "PreToolUse", 'cd x\ngrep "[pl:-]" f')
        self.assertTrue(os.path.exists(p))   # grep is not a clear
        self._run(M, "PreToolUse", 'cd x\necho "[pl:-]"')
        self.assertFalse(os.path.exists(p))


if __name__ == "__main__":
    unittest.main()
