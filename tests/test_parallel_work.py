"""Parallel-work copy commands (web/js/89-branch-worktree.js brQ/brPwCheck/brPwCmd/brWrmHtml), run through node. Copy-only: no server route."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import js_all   # all web/js joined - functions are found by name, whichever file holds them
from tests._node import node_e


def _fn(src, name):
    return re.search(r"^function " + name + r"\(.*?^}", src, re.S | re.M).group(0)


def _run(br, expr):
    src = js_all()
    js = "\n".join([
        "const T = s => s, esc = s => String(s); let brRepo = '/r';",
        "let BR = " + json.dumps(br) + ";",
        re.search(r"^const BR_PW_RE = .*$", src, re.M).group(0),
        re.search(r"^const BR_PW_TYPES = .*$", src, re.M).group(0),
        _fn(src, "brQ"), _fn(src, "brPwMain"), _fn(src, "brPwCheck"), _fn(src, "brPwCmd"),
        _fn(src, "brPwFlow"), _fn(src, "brPwPlan"),
        "function brWtSig(w){ return (BR.wtSig || {})[w.path] || null; }", _fn(src, "brWrmHtml"),
        "console.log(JSON.stringify(" + expr + "));",
    ])
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


MAIN = "/w/it's a repo"
BR = {"ok": True, "cwd": MAIN,
      "worktrees": [{"path": MAIN, "main": True, "branch": "main"},
                    {"path": MAIN + "/.claude/worktrees/feat-a", "branch": "worktree-feat-a"}],
      "branches": [{"name": "main", "kind": "local"}, {"name": "fix-b", "kind": "local"},
                   {"name": "origin/remote-only", "kind": "remote"}],
      "wtSig": {MAIN + "/.claude/worktrees/feat-a": {"dirty": 3}}}


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ParallelWork(unittest.TestCase):
    def check(self, name):
        return _run(BR, "brPwCheck(%s, BR.worktrees, BR.branches)" % json.dumps(name))

    def test_good_name(self):
        self.assertEqual(self.check("feat-x.2_y"), {"ok": True, "err": "", "warn": ""})

    def test_bad_names_blocked(self):
        for n in ["", "Feat", "a b", "a;rm", "$(x)", "a/b", "..", "한글"]:
            self.assertFalse(self.check(n)["ok"], n)

    def test_leading_dash_and_uppercase(self):
        for n in ["-x", "_x", "-"]:   # a leading '-' is read as an option by claude -w / git -b
            self.assertEqual(self.check(n)["err"], "The name must start with a lowercase letter or a digit", n)   # English source; T() is a pass-through here
        self.assertEqual(self.check("Feat")["err"], "Lowercase letters only")
        self.assertEqual(self.check("A b")["err"], "Only lowercase letters, digits and . _ - (blocks characters the shell would interpret)")

    def test_collision_warns_but_allows(self):
        for n in ["feat-a", "fix-b"]:
            c = self.check(n)
            self.assertTrue(c["ok"], n)
            self.assertTrue(c["warn"], n)
        self.assertEqual(self.check("remote-only")["warn"], "")   # remote branches do not collide

    def test_command_quotes_path_with_space_and_quote(self):
        cmd = _run(BR, "brPwCmd('feat-x')")
        self.assertEqual(cmd, "cd '/w/it'\\''s a repo' && claude -w feat-x --tmux")
        out = subprocess.run(["sh", "-c", "printf %s " + cmd.split(" && ")[0][3:]], capture_output=True, text=True).stdout
        self.assertEqual(out, MAIN)

    def plan(self, typ, name, flow):
        return _run(dict(BR, flow=flow), "brPwPlan(%s, %s, brPwFlow(), brPwMain())" % (json.dumps(typ), json.dumps(name)))

    def test_flow_base_per_type(self):
        f = {"develop": "develop", "master": "main", "prefix": {"feature": "feat/"}, "src": "gitflow-config"}
        got = {t: self.plan(t, "1.4.0", f) for t in ["feature", "bugfix", "release", "hotfix"]}
        self.assertEqual(got["feature"]["branch"], "feat/1.4.0")          # configured prefix wins
        self.assertEqual(got["bugfix"]["branch"], "bugfix/1.4.0")          # missing key -> default
        self.assertEqual({t: p["base"] for t, p in got.items()},
                         {"feature": "develop", "bugfix": "develop", "release": "develop", "hotfix": "main"})
        self.assertEqual(got["release"]["folder"], MAIN + ".wt/release-1.4.0")
        self.assertFalse(any(p["noDev"] for p in got.values()))

    def test_no_develop_falls_back_to_master(self):
        p = self.plan("feature", "x", {"develop": None, "master": "master"})
        self.assertEqual((p["base"], p["noDev"]), ("master", True))
        self.assertFalse(self.plan("hotfix", "x", {"develop": None, "master": "master"})["noDev"])
        self.assertEqual(_run({"ok": True}, "brPwFlow().prefix.hotfix"), "hotfix/")   # old payload without flow

    def test_remote_only_develop(self):
        f = {"develop": "origin/develop", "devRemote": "origin", "devName": "develop", "master": "main"}
        p = self.plan("feature", "x", f)
        self.assertEqual((p["base"], p["noDev"], p["remote"]), ("origin/develop", False, True))
        self.assertFalse(self.plan("hotfix", "x", f)["remote"])
        cmd = _run(BR, "brPwCmd('x', %s)" % json.dumps(p))
        self.assertIn(" worktree add --no-track ", cmd)
        self.assertIn(" -b 'feature/x' 'origin/develop' && ", cmd)
        h = self.plan("hotfix", "x", dict(f, master="origin/main", mstRemote="origin"))
        self.assertEqual((h["base"], h["remote"]), ("origin/main", True))

    def test_flow_command_quoting(self):
        p = self.plan("feature", "login", {"develop": "develop", "master": "main"})
        cmd = _run(BR, "brPwCmd('login', %s)" % json.dumps(p))
        q = "'/w/it'\\''s a repo"
        self.assertEqual(cmd, "git -C " + q + "' worktree add " + q + ".wt/feature-login' -b 'feature/login' 'develop'"
                         " && cd " + q + ".wt/feature-login' && claude")
        argv = subprocess.run(["sh", "-c", "for a in " + cmd.split(" && ")[0][4:] + "; do printf '%s\\n' \"$a\"; done"],
                              capture_output=True, text=True).stdout.splitlines()
        self.assertEqual(argv, ["-C", MAIN, "worktree", "add", MAIN + ".wt/feature-login", "-b", "feature/login", "develop"])

    def test_flow_collisions(self):
        wt = MAIN + ".wt/feature-a"
        br = dict(BR, worktrees=BR["worktrees"] + [{"path": wt + "/", "branch": "feature/a"}],
                  branches=BR["branches"] + [{"name": "feature/b", "kind": "local"}])
        chk = lambda n: _run(br, "brPwCheck(%s, BR.worktrees, BR.branches, brPwPlan('feature', %s, brPwFlow(), brPwMain()))"
                             % (json.dumps(n), json.dumps(n)))
        self.assertIn("worktree", chk("a")["warn"])
        self.assertIn("branch", chk("b")["warn"])
        self.assertEqual(chk("fix-b")["warn"], "")                         # plain fix-b is not feature/fix-b
        for n in [".x", "x.", "a..b", "x.lock"]:
            self.assertFalse(chk(n)["ok"], n)

    def test_cleanup_command_no_force_and_dirty_warning(self):
        h = _run(BR, "brWrmHtml(BR.worktrees[1])")
        self.assertIn("git -C '/w/it'\\''s a repo' worktree remove '/w/it'\\''s a repo/.claude/worktrees/feat-a'", h)
        self.assertNotIn("--force", h)
        self.assertIn("3 uncommitted", h)

    def test_no_error_before_first_input(self):
        src = js_all()
        pre = "(() => { " + _fn(src, "brPwCur") + _fn(src, "brPwOk") + _fn(src, "brPwMsg")
        msg = lambda st: _run(BR, pre + " brPw = " + json.dumps(st) + "; return brPwMsg(); })()")
        self.assertEqual(msg({"name": "", "type": "w"}), "")                       # just opened
        self.assertIn("Enter a name", msg({"name": "", "type": "w", "touched": 1}))   # typed then cleared / Enter
        self.assertIn("claude -w ok", msg({"name": "ok", "type": "w", "touched": 1}))


if __name__ == "__main__":
    unittest.main()
