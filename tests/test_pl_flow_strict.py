"""hooks/pl_flow.py strict mode (_policy.json {"enforce": "writes"}): edits / main commits denied every time with no
open run (R1); [pl-none:explore] only, other categories refused (R2); missing/unknown switch keeps deny-once.
Tmp dirs only, fixed clock."""
import json
import os
import unittest

from tests import test_pl_flow_none as N   # ⚠not `from … import PlNone`: its tests would run again here

H = N.H
SID = N.SID


# Reuse PlNone's fixture without re-running its tests: borrow its helpers onto a fresh TestCase.
class Strict(unittest.TestCase):
    _ev = N.PlNone._ev
    edit = N.PlNone.edit
    bash = N.PlNone.bash
    denied = N.PlNone.denied

    def policy(self, d):
        with open(os.path.join(self.proj, ".claude", "pipelines", "_policy.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def setUp(self):
        N.PlNone.setUp(self)
        with open(os.path.join(self.proj, ".claude", "pipelines", "alpha.json"), "w", encoding="utf-8") as f:
            json.dump({"v": 1, "name": "alpha", "use": "Alpha work " + "x" * 200,
                       "stages": [{"title": "s1", "agent": "general-purpose"}]}, f)
        self.policy({"enforce": "writes"})

    def tool(self, name):
        fp = os.path.join(self.proj, "src", "a.py")
        ti = {"notebook_path": fp} if name == "NotebookEdit" else {"file_path": fp, "content": "y"}
        return self._ev(name, ti)

    def open_run(self, t1=990.0):
        os.makedirs(self.marks, exist_ok=True)
        with open(os.path.join(self.marks, SID + ".runs.json"), "w", encoding="utf-8") as f:
            json.dump({"v": 1, "runs": {"alpha": {"cur": "s1", "end": 0, "t1": t1}}}, f)

    def test_r1_edits_denied_every_time(self):
        for name in H.EDITS:
            for _ in range(2):
                o = self.tool(name)
                self.assertTrue(self.denied(o), name)
                why = o["permissionDecisionReason"]
                self.assertIn("alpha: Alpha work", why)
                self.assertIn("beta", why)
                self.assertIn("quick-fix", why)
                self.assertNotIn("retrying proceeds", why)
                self.assertNotIn("x" * 80, why)   # use text clipped to 80
        self.assertFalse(os.path.exists(self.nf))   # no nudge stamp

    def test_r1_main_commit_denied_every_time(self):
        self.assertTrue(self.denied(self.bash("git commit -m x", "commit")))
        self.assertTrue(self.denied(self.bash("git commit -m x", "commit")))

    def test_r1_tagged_commit_without_run_denied(self):
        for desc in ("[pl:-] commit", "[pl:nonexistent/x] c", "[pl-skip:a/b] c", "[pl] c"):
            self.assertTrue(self.denied(self.bash("git commit -m x", desc)), desc)

    def test_r1_commit_grace_after_run_ended(self):
        os.makedirs(self.marks, exist_ok=True)
        with open(os.path.join(self.marks, SID + ".runs.json"), "w", encoding="utf-8") as f:
            json.dump({"v": 1, "runs": {"alpha": {"cur": "s1", "end": 900.0, "t1": 900.0}}}, f)
        self.assertFalse(self.denied(self.bash("git commit -m x", "commit")))   # 100 s after end
        self.t = 900.0 + H.STRICT_GRACE_S + 1
        self.assertTrue(self.denied(self.bash("git commit -m x", "commit")))
        self.assertTrue(self.denied(self.edit()))

    def test_r1_reads_bash_agent_dry_run_pass(self):
        self.assertIsNone(self._ev("Read", {"file_path": os.path.join(self.proj, "a.py")}))
        self.assertFalse(self.denied(self.bash("ls", "list")))
        self.assertFalse(self.denied(self.bash("git commit --dry-run -m x", "dry")))
        self.assertFalse(self.denied(self._ev("Agent", {"description": "look around", "subagent_type": "Explore"})))

    def test_commit_forms_are_gated(self):
        # Path prefix, global options and a «--dry-run» inside the message are still real commits under strict mode.
        for cmd in ("/usr/bin/git commit -m x", "git -c user.name=a commit -m x", "git --no-pager commit -m x",
                    'git commit -m "skip --dry-run next time"'):
            self.assertTrue(self.denied(self.bash(cmd, "commit")), cmd)

    def test_r1_open_run_passes(self):
        self.open_run()
        self.assertFalse(self.denied(self.edit()))
        self.assertFalse(self.denied(self.bash("git commit -m x", "commit")))

    def test_r2_explore_accepted_but_edits_stay_denied(self):
        self.assertFalse(self.denied(self.bash("ls", "[pl-none:explore]")))
        self.assertEqual(H._none_load(self.nf).get("cat"), "explore")
        self.assertTrue(self.denied(self.edit()))
        self.assertTrue(self.denied(self.bash("git commit -m x", "[pl-none:explore] commit")))

    def test_r2_other_categories_refused(self):
        for c in ("small-fix", "no-fit", "other"):
            o = self.bash("ls", "[pl-none:%s] x" % c)
            self.assertTrue(self.denied(o), c)
            self.assertIn("quick-fix", o["permissionDecisionReason"])
        self.assertFalse(os.path.exists(self.nf))

    def test_r1_subagent_denied_without_run_passes_with_stale_open_run(self):
        self.assertTrue(self.denied(self.edit(agent="agent-1")))
        self.assertTrue(self.denied(self.bash("git commit -m x", "commit", agent="agent-1")))
        self.open_run(t1=1000.0 - H.IDLE_S - 10)   # un-ended but idle: a long stage still counts
        self.assertFalse(self.denied(self.edit(agent="agent-1")))
        self.assertFalse(self.denied(self.bash("git commit -m x", "commit", agent="agent-1")))

    def test_nongoal_unknown_or_missing_switch_denies_once(self):
        for pol in ({"enforce": "all"}, None, ["writes"]):
            if os.path.exists(self.nf):
                os.remove(self.nf)
            path = os.path.join(self.proj, ".claude", "pipelines", "_policy.json")
            if pol is None:
                os.remove(path)
            else:
                self.policy(pol)
            o = self.edit()
            self.assertTrue(self.denied(o))
            self.assertIn("retrying proceeds", o["permissionDecisionReason"])
            self.assertFalse(self.denied(self.edit()))
            self.assertFalse(self.denied(self.edit(agent="agent-1")))
        self.assertFalse(self.denied(self.bash("ls", "[pl-none:small-fix]")))

    def test_apply_off_bypasses(self):
        with open(H.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"pipeline_apply": {"mode": "off"}}, f)
        self.assertFalse(self.denied(self.edit()))
        self.assertFalse(self.denied(self.bash("git commit -m x", "commit")))
        self.assertFalse(self.denied(self.bash("ls", "[pl-none:small-fix]")))

    def test_strict_helper(self):
        self.assertTrue(H._strict(self.proj))
        self.assertFalse(H._strict(self.bare))

    def _review(self, readonly=True, end=0, t1=990.0):
        with open(os.path.join(self.proj, ".claude", "pipelines", "review.json"), "w", encoding="utf-8") as f:
            json.dump({"v": 1, "name": "review", "readonly": readonly,
                       "stages": [{"title": "r1", "agent": "general-purpose"}]}, f)
        os.makedirs(self.marks, exist_ok=True)
        with open(os.path.join(self.marks, SID + ".runs.json"), "w", encoding="utf-8") as f:
            json.dump({"v": 1, "runs": {"review": {"cur": "r1", "end": end, "t1": t1, "cwd": self.proj}}}, f)

    def test_r5_readonly_run_does_not_license_edits(self):
        self._review()
        self.assertTrue(self.denied(self.edit()))
        self.assertTrue(self.denied(self.bash("git commit -m x", "[pl:review/r1] commit")))
        self.assertTrue(self.denied(self.edit(agent="agent-1")))

    def test_r5_readonly_run_denied_within_grace(self):
        self._review(end=900.0, t1=900.0)   # ended 100 s ago, inside STRICT_GRACE_S
        self.assertTrue(self.denied(self.edit()))
        self.assertTrue(self.denied(self.bash("git commit -m x", "commit")))

    def test_r5_non_readonly_run_passes(self):
        self._review(readonly=False)
        self.assertFalse(self.denied(self.edit()))
        self.assertFalse(self.denied(self.bash("git commit -m x", "commit")))

    def _tmpdir(self):
        td = os.path.join(self.tmp, "tmpdir")
        os.makedirs(td, exist_ok=True)
        old = os.environ.get("TMPDIR")
        os.environ["TMPDIR"] = td
        self.addCleanup(lambda: os.environ.__setitem__("TMPDIR", old) if old is not None else os.environ.pop("TMPDIR", None))

    WRITES = ("sed -i s/a/b/ f.py", "sed -i '' s/a/b/ src/a.py", "echo x > f.py", "echo x >> f.py", "cat a | tee f.py",
              "cat a | tee -a f.py", "echo x &> f.py", "true;>f.py")
    PASSES = ("ls >/dev/null 2>&1", "echo x > /tmp/x", "echo x > $TMPDIR/x", "ls 2>&1", "sed s/a/b/ f.py",
              "cat f.py | grep tee", "echo 'unclosed > f.py")

    def test_r6_bash_writes_denied_without_run(self):
        self._tmpdir()
        for c in self.WRITES:
            self.assertTrue(self.denied(self.bash(c, "x")), c)
        for c in self.PASSES:
            self.assertFalse(self.denied(self.bash(c, "x")), c)

    def test_r6_l1_newline_separates_commands(self):
        self.assertTrue(self.denied(self.bash("echo hi\nsed -i s/a/b/ f.py", "x")))
        self.assertFalse(self.denied(self.bash("echo 'a\nsed -i s/a/b/ f.py'", "x")))   # quoted newline is data

    def test_r6_l2_heredoc_body_is_data(self):
        out = os.path.join(self.tmp, "outside", "x.py")
        self.assertFalse(self.denied(self.bash("cat > %s <<'EOF'\nif n > 0:\n    pass\nEOF" % out, "x")))
        self.assertFalse(self.denied(self.bash("cat > %s <<-EOF\nx > f.py\n\tEOF\nls" % out, "x")))
        self.assertTrue(self.denied(self.bash("cat > f.py <<EOF\nhi\nEOF", "x")))
        self.assertTrue(self.denied(self.bash("cat <<EOF\nhi\nEOF\necho x > f.py", "x")))

    def test_r6_l3_cd_moves_relative_targets(self):
        out = os.path.join(self.tmp, "outside")
        os.makedirs(out, exist_ok=True)
        self.assertFalse(self.denied(self.bash("cd %s && echo x > out" % out, "x")))
        self.assertTrue(self.denied(self.bash("cd src && echo x > out", "x")))
        for c in ("cd $X && echo x > out", "cd ~ && echo x > out", "cd - && echo x > out", "cd && echo x > out"):
            self.assertFalse(self.denied(self.bash(c, "x")), c)   # unknown dir: fail-open
        self.assertTrue(self.denied(self.bash("cd $X && echo x > %s" % os.path.join(self.proj, "f.py"), "x")))

    def test_r6_l4_prefixed_commands(self):   # keywords, assignments and env come before the real command
        for c in ("if true; then sed -i s/a/b/ f.py; fi", "for x in a; do tee f.py; done", "X=1 tee f.py",
                  "env tee f.py", "env -i A=1 -u B sed -i s/a/b/ f.py", "true && ! tee f.py", "{ tee f.py; }"):
            self.assertTrue(self.denied(self.bash(c, "x")), c)
        for c in ("if true; then echo then > /dev/null; fi", "X=1 sed s/a/b/ f.py", "echo env tee f.py"):
            self.assertFalse(self.denied(self.bash(c, "x")), c)

    def test_r6_bash_write_passes_with_open_run(self):
        self.open_run()
        self.assertFalse(self.denied(self.bash("echo x > f.py", "x")))

    def test_r7_non_strict_bash_writes_untouched(self):
        self._tmpdir()
        os.remove(os.path.join(self.proj, ".claude", "pipelines", "_policy.json"))
        for c in self.WRITES + self.PASSES:
            self.assertFalse(self.denied(self.bash(c, "x")), c)
        self.assertFalse(os.path.exists(self.nf))   # no nudge stamp: Bash writes are not gated off strict

    def test_r7_non_strict_review_run_still_licenses(self):
        os.remove(os.path.join(self.proj, ".claude", "pipelines", "_policy.json"))
        self._review()
        self.assertFalse(self.denied(self.edit()))

    def test_plugin_copy_identical(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "hooks", "pl_flow.py"), "rb") as a, \
                open(os.path.join(root, "plugin", "hooks", "pl_flow.py"), "rb") as b:
            self.assertEqual(a.read(), b.read())

    def test_schema_readonly_must_be_bool(self):
        from sidereus import pipeline_schema as PS
        P = {"v": 1, "name": "x", "title": "X", "defaults": {"model": "inherit", "retry": 0},
             "stages": [{"title": "s", "agent": "general-purpose"}]}
        self.assertNotIn("readonly: true|false", PS.validate(dict(P, readonly=True), "x"))
        self.assertIn("readonly: true|false", PS.validate(dict(P, readonly="yes"), "x"))


if __name__ == "__main__":
    unittest.main()
