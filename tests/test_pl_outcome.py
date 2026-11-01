"""Pipeline result layer (sidereus/pl_outcome.py): ledger, loop-back split, broke / fix-followed PASSes, sentences.
`_git`, `_now`, `OC_EVAL_DIR` and `harness_evidence.EV_FILE` are patched; no real git, clock or live files."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import load, sidereus

load()
OC = sidereus("pl_outcome")
EV = sidereus("harness_evidence")
TR = sidereus("harness_trail")
D = 86400
P = 1000000000.0   # PASS time
N = "change"
FILL = [("%040x" % (k + 1), int(P - 5000 - k), ["old%d.py" % k]) for k in range(3)]   # unrelated older commits
FIX = "bugfix"   # bug-fix pipeline name passed as outcome(fix=...)
BASE = {"name": N, "t0": P - 100, "end": P + 10, "lb": [], "deny": 0, "dc": {}}


def fixrun(ct, name=FIX):
    """Ledger row of a run whose commit lands at `ct` (ends 10 s before it)."""
    return {"name": name, "t0": ct - 100, "end": ct - 10}


# R3: offline copy of the measured «fix followed» cases of this repo (read-only git + eval/<key>/runs.jsonl; R3_NOW =
# the measuring time). Bug-fix pipelines there are quick-fix and sidereus-bugfix.
R3_NOW = 1793493926
R3_LOG = [   # newest first; file names cut to those the measured PASS commits touched
    ('cd7b6594d6ff', 1793452278, ['refactor/STAGE3.md', 'sidereus/bgtasks_parse.py']),
    ('10695f2416b9', 1793450241, ['sidereus/bgtasks_parse.py', 'tests/test_bg_stop.py']),
    ('8512a7470bf9', 1793447079, ['docs/GUIDE.ko.md', 'docs/GUIDE.md', 'docs/HOOKS.ko.md', 'docs/HOOKS.md',
                                  'docs/dev/FILEMAP.md', 'docs/dev/traps/platform.md', 'refactor/STAGE3.md',
                                  'scripts/screen_baseline/1100-en.json', 'scripts/screen_baseline/1100-ko.json',
                                  'scripts/screen_baseline/1440-en.json', 'scripts/screen_baseline/1440-ko.json',
                                  'scripts/screen_baseline/1920-en.json', 'scripts/screen_baseline/1920-ko.json',
                                  'scripts/screen_baseline/900-en.json', 'scripts/screen_baseline/900-ko.json',
                                  'sidereus/demo.py', 'sidereus/demo_data.py', 'sidereus/ext.py',
                                  'sidereus/ext_presence.py', 'sidereus/ext_store.py', 'sidereus/plat_copilot.py',
                                  'sidereus/timeline_ext.py', 'tests/test_ext_copilot_tok.py',
                                  'tests/test_plat_copilot_usage.py', 'tests/test_sbar_copilot_js.py',
                                  'tests/test_tl_presence.py', 'web/js/06-i18n-zzj-copilot.js',
                                  'web/js/46-tokens-tab.js', 'web/js/60-statusbar.js']),
    ('1b06431a7fed', 1793440707, ['refactor/STAGE3.md', 'sidereus/timeline_ext.py', 'tests/test_tl_presence.py']),
    ('5902fb686e86', 1793440319, ['docs/HOOKS.ko.md', 'docs/HOOKS.md']),
    ('bf73cd2e2642', 1793440216, ['docs/HOOKS.ko.md', 'docs/HOOKS.md', 'web/js/06-i18n-zt-hookconn.js',
                                  'web/js/90f-hookconn.js']),
    ('ffa3c88bd60b', 1793436683, ['docs/GUIDE.ko.md', 'docs/GUIDE.md', 'docs/HOOKS.ko.md', 'docs/HOOKS.md',
                                  'docs/dev/FILEMAP.md', 'docs/dev/traps/platform.md', 'refactor/STAGE3.md',
                                  'scripts/screen_baseline/1100-en.json', 'scripts/screen_baseline/1100-ko.json',
                                  'scripts/screen_baseline/1440-en.json', 'scripts/screen_baseline/1440-ko.json',
                                  'scripts/screen_baseline/1920-en.json', 'scripts/screen_baseline/1920-ko.json',
                                  'scripts/screen_baseline/900-en.json', 'scripts/screen_baseline/900-ko.json',
                                  'sidereus/demo.py', 'sidereus/demo_data.py', 'sidereus/ext_presence.py',
                                  'sidereus/ext_store.py', 'sidereus/plat_copilot.py', 'tests/test_hook_connect.py',
                                  'web/css/93-header-toolbar.css', 'web/js/90f-hookconn.js']),
    ('b7512c449aeb', 1793434533, ['sidereus/hook_connect.py', 'tests/test_hook_connect.py']),
    ('6580f96de993', 1793433937, ['docs/HOOKS.ko.md', 'docs/HOOKS.md', 'setup.py', 'sidereus/hook_connect.py',
                                  'tests/test_wheel_build.py']),
    ('90fe4f3d1122', 1793433202, ['web/css/93-header-toolbar.css']),
    ('a103c8f64ca4', 1793422223, ['scripts/screen_baseline/1100-en.json', 'scripts/screen_baseline/1100-ko.json',
                                  'scripts/screen_baseline/1440-en.json', 'scripts/screen_baseline/1440-ko.json',
                                  'scripts/screen_baseline/1920-en.json', 'scripts/screen_baseline/1920-ko.json',
                                  'scripts/screen_baseline/900-en.json', 'scripts/screen_baseline/900-ko.json',
                                  'scripts/screen_check.mjs']),
    ('82dca1e2d686', 1793421651, ['docs/dev/TRAPS.md']),
    ('36cec2577539', 1793416584, ['docs/HOOKS.ko.md', 'docs/HOOKS.md', 'docs/dev/TRAPS.md',
                                  'docs/dev/traps/platform.md', 'ext-hooks/copilot-hooks-example.json',
                                  'hooks/pl_flow.py', 'hooks/pl_mark.py', 'plugin/hooks/pl_flow.py',
                                  'plugin/hooks/pl_mark.py', 'tests/test_hook_connect.py', 'tests/test_pl_flow.py',
                                  'tests/test_pl_mark_hook.py']),
    ('b0daaa0f4831', 1793413339, ['docs/GUIDE.ko.md', 'docs/GUIDE.md', 'refactor/STAGE3.md',
                                  'sidereus/bgtasks_parse.py', 'sidereus/demo.py']),
    ('f6ed56bc38d3', 1793411479, ['sidereus/ext.py']),
    ('3e09e0996625', 1793411229, ['CHANGELOG.md', 'docs/HOOKS.ko.md', 'docs/HOOKS.md', 'docs/dev/FILEMAP.md',
                                  'docs/dev/traps/platform.md', 'ext-hooks/copilot-hooks-example.json',
                                  'sidereus/hook_connect.py', 'tests/test_hook_connect.py', 'web/js/90f-hookconn.js']),
    ('c4b44c5968d0', 1793409258, ['docs/GUIDE.ko.md', 'docs/GUIDE.md', 'docs/dev/FILEMAP.md', 'hooks/pl_flow.py',
                                  'plugin/hooks/pl_flow.py', 'refactor/STAGE3.md', 'sidereus/pl_reqs.py',
                                  'tests/test_pl_flow.py', 'tests/test_pl_reqs.py', 'web/css/41b-harness.css']),
    ('7756711c4555', 1793408057, ['docs/dev/FILEMAP.md', 'web/css/41b-harness.css']),
    ('c514e6d40e36', 1793407617, ['hooks/pl_flow.py', 'plugin/hooks/pl_flow.py']),
    ('21a75b6273de', 1793406538, ['hooks/pl_flow.py', 'plugin/hooks/pl_flow.py', 'sidereus/pl_reqs.py',
                                  'tests/test_pl_flow_strict.py', 'tests/test_pl_reqs.py']),
    ('11a2673c9ccb', 1793405329, ['CHANGELOG.md']),
    ('96f5d91cb96d', 1793403269, ['CHANGELOG.md', 'sidereus/hook_connect.py', 'tests/test_hook_connect.py',
                                  'tests/test_hook_remove.py']),
    ('b1e06c9f08bd', 1793365607, ['CHANGELOG.md', 'docs/GUIDE.ko.md', 'docs/GUIDE.md', 'docs/dev/FILEMAP.md',
                                  'docs/dev/TRAPS.md', 'refactor/STAGE3.md', 'tests/test_hook_remove.py',
                                  'web/css/41b-harness.css']),
    ('b77abf81dc86', 1793359410, ['CHANGELOG.md', 'docs/GUIDE.ko.md', 'docs/GUIDE.md', 'docs/dev/FILEMAP.md',
                                  'docs/dev/TRAPS.md', 'refactor/STAGE3.md']),
    ('366c9e032ca7', 1793339641, ['docs/GUIDE.ko.md', 'docs/GUIDE.md', 'tests/test_harness_next_js.py',
                                  'web/css/41b-harness.css']),
]
R3_RUNS = [   # ledger rows (name, t0, end) of every pipeline in the period
    ('quick-fix', 1793339576, 1793339637), ('sidereus-change', 1793358306, 1793359406),
    ('sidereus-bugfix', 1793403023, 1793403260), ('release', 1793404327, 1793404451),
    ('quick-fix', 1793406425, 1793406533), ('sidereus-change', 1793406709, 1793408115),
    ('sidereus-change', 1793408115, 1793410468), ('sidereus-bugfix', 1793411637, 1793412170),
    ('sidereus-change', 1793412185, 1793413169), ('sidereus-change', 1793414818, 1793416576),
    ('quick-fix', 1793417547, 1793417596), ('quick-fix', 1793421635, 1793421648),
    ('quick-fix', 1793421677, 1793421706), ('quick-fix', 1793421706, 1793421856),
    ('quick-fix', 1793421856, 1793421888), ('quick-fix', 1793421923, 1793422188),
    ('docs', 1793423826, 1793423837), ('quick-fix', 1793433166, 1793433197),
    ('sidereus-bugfix', 1793433284, 1793433928), ('quick-fix', 1793434479, 1793434519),
    ('sidereus-change', 1793434650, 1793436505), ('quick-fix', 1793440171, 1793440209),
    ('docs', 1793440296, 1793440307), ('sidereus-change', 1793445599, 1793447070),
    ('sidereus-bugfix', 1793440353, 1793448909), ('sidereus-bugfix', 1793448909, 1793449186),
    ('sidereus-bugfix', 1793449824, 1793450234), ('sidereus-bugfix', 1793450258, 1793450757),
    ('quick-fix', 1793452864, 1793452878),
]
R3_CASES = [   # (pipeline, PASS commit, [(PASS ts, head, dirty)])
    ('docs', '5902fb686e86', [(1793440319, 'bf73cd2e', True)]),
    ('quick-fix', 'bf73cd2e2642', [(1793440196, 'ffa3c88b', True)]),
    ('quick-fix', 'b7512c449aeb', [(1793434503, '6580f96d', True)]),
    ('quick-fix', '90fe4f3d1122', [(1793433171, 'ab8f88d8', True)]),
    ('quick-fix', 'a103c8f64ca4', [(1793422223, '853665bf', True)]),
    ('quick-fix', '21a75b6273de', [(1793406520, '11a2673c', True)]),
    ('quick-fix', '366c9e032ca7', [(1793339594, 'c7720e47', True)]),
    ('release', '96f5d91cb96d', [(1793404431, '96f5d91c', False)]),
    ('sidereus-bugfix', '10695f2416b9', [
        (1793450222, '23e17fdc', True), (1793450133, '23e17fdc', True), (1793450059, '23e17fdc', True),
        (1793449965, '23e17fdc', True),
    ]),
    ('sidereus-bugfix', '8512a7470bf9', [
        (1793447035, '1b06431a', True), (1793446947, '1b06431a', True), (1793446649, '1b06431a', True),
        (1793446480, '1b06431a', True), (1793446320, '1b06431a', True), (1793445996, '1b06431a', True),
        (1793445963, '1b06431a', True), (1793440711, 'be9e4b36', True),
    ]),
    ('sidereus-bugfix', '1b06431a7fed', [(1793440707, '5902fb68', True)]),
    ('sidereus-bugfix', '6580f96de993', [(1793433911, '90fe4f3d', True), (1793433812, '90fe4f3d', True)]),
    ('sidereus-change', '8512a7470bf9', [
        (1793447035, '1b06431a', True), (1793446947, '1b06431a', True), (1793446649, '1b06431a', True),
        (1793446480, '1b06431a', True), (1793446320, '1b06431a', True), (1793445996, '1b06431a', True),
        (1793445963, '1b06431a', True),
    ]),
    ('sidereus-change', '36cec2577539', [
        (1793415517, 'b0daaa0f', True), (1793415414, 'b0daaa0f', True), (1793415270, 'b0daaa0f', True),
        (1793415181, 'b0daaa0f', True), (1793415052, 'b0daaa0f', True), (1793415034, 'b0daaa0f', True),
        (1793415008, 'b0daaa0f', True),
    ]),
]


class Git(object):
    """Fake git: rev-parse HEAD + one `log --name-only` built from [(sha, ct, files)] newest first."""

    def __init__(self, commits):
        self.commits, self.calls, self.side = commits, [], set()

    def __call__(self, repo, args):
        self.calls.append(list(args))
        if args[0] == "rev-parse":
            return 0, "f" * 40 + "\n"
        if args[0] == "log":
            return 0, "".join("\x1e%s\x1f%d\n\n%s\n" % (s, ct, "\n".join(fs)) for s, ct, fs in self.commits)
        if args[0] == "rev-list":   # linear history: everything newer than C, minus side-branch commits
            c = args[-1].split("..")[0]
            shas = [x[0] for x in self.commits]
            return 0, "".join(x + "\n" for x in shas[:shas.index(c)] if x not in self.side)
        return None


class TrGit(object):
    """harness_trail git: HEAD known, every PASS head an ancestor unless in `gone`; `fail` = git never answers."""

    def __init__(self):
        self.gone, self.fail = set(), False

    def __call__(self, repo, args):
        if self.fail and args[0] != "rev-parse":
            return None
        if args[0] == "rev-parse":
            return 0, ("f" * 40 if args[-1] == "HEAD" else "1" * 40) + "\n"
        if args[0] == "merge-base":
            return (1, "") if args[2] in self.gone else (0, "")
        return 0, ""


class Outcome(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pl-oc-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(self.proj)
        self.evf = os.path.join(self.tmp, "evidence.jsonl")
        self.now = P + 20 * D
        self.git, self.tr = Git([]), TrGit()
        self.fix = [FIX]
        saved = [(OC, "OC_EVAL_DIR", os.path.join(self.tmp, "eval")), (OC, "_git", self.git), (OC, "_now", lambda: self.now),
                 (EV, "EV_FILE", self.evf), (TR, "_git", self.tr)]
        for mod, k, v in saved:
            old = getattr(mod, k)
            setattr(mod, k, v)
            self.addCleanup(setattr, mod, k, old)
        OC._OC_MEMO.clear()
        self.ledger([BASE])

    def ledger(self, rows, junk=False):
        d = os.path.join(self.tmp, "eval", OC.repo_key(self.proj))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "runs.jsonl"), "w", encoding="utf-8") as f:
            if junk:
                f.write("{half\n" + json.dumps({"name": "../x", "end": 1}) + "\n")
            f.write("".join(json.dumps(r) + "\n" for r in rows))

    def evidence(self, *rows):
        with open(self.evf, "w", encoding="utf-8") as f:
            for ts, rc, head, dirty in rows:
                if not isinstance(ts, (int, float)):
                    f.write(ts + "\n")
                    continue
                f.write(json.dumps({"v": 1, "kind": "check", "repo": os.path.realpath(self.proj), "ts": ts, "mode": "fast",
                                    "rc": rc, "head": head, "dirty": dirty, "steps": [{"name": "tests", "rc": rc}]}) + "\n")

    def result(self, commits):
        self.git.commits = commits
        OC._OC_MEMO.clear()
        return OC.outcome(self.proj, N, ["review"], fix=self.fix)["result"]

    def test_fix_window_and_files(self):
        """R1: a later commit counts only inside a fix run, within 14 days, sharing a file."""
        self.evidence((P, 0, "aaaaaaa", False))
        base = [("b" * 40, int(P + 15 * D), ["b.py"]),   # day 15: too late
                ("c" * 40, int(P + 3 * D), ["c.py"]),     # untouched file
                ("a" * 40, int(P - 30), ["a.py", "b.py"])] + FILL
        self.ledger([BASE, fixrun(P + 15 * D), fixrun(P + 3 * D), fixrun(P + 13 * D)])
        r = self.result(base)
        self.assertEqual((r["n"], r["broke"], r["fixed"]), (1, 0, 0))
        self.assertEqual(r["list"], [{"sha": "a" * 12, "files": ["a.py", "b.py"], "broke": False, "fixed": False}])
        r = self.result([("d" * 40, int(P + 13 * D), ["a.py"])] + base)   # day 13 touching a.py
        self.assertEqual((r["n"], r["fixed"]), (1, 1))

    def test_r1_non_fix_run_commit_not_a_fix(self):
        """R1: the same later commit made by a non-fix pipeline run (or no run at all) is not «fix followed»."""
        self.evidence((P, 0, "aaaaaaa", False))
        log = [("d" * 40, int(P + 3 * D), ["a.py"]), ("a" * 40, int(P - 30), ["a.py"])] + FILL
        self.ledger([BASE, fixrun(P + 3 * D, name="feature")])
        self.assertEqual(self.result(log)["fixed"], 0)
        self.ledger([BASE])
        self.assertEqual(self.result(log)["fixed"], 0)
        self.ledger([BASE, fixrun(P + 3 * D)])
        self.assertEqual(self.result(log)["fixed"], 1)

    def test_r1_grace_after_fix_run_end(self):
        """R1: a commit 899 s after a fix run ended belongs to it, 901 s does not (OC_FIX_GRACE_S = 900)."""
        self.evidence((P, 0, "aaaaaaa", False))
        end = P + 3 * D
        self.ledger([BASE, {"name": FIX, "t0": end - 600, "end": end}])
        for dt, want in ((899, 1), (901, 0)):
            r = self.result([("d" * 40, int(end + dt), ["a.py"]), ("a" * 40, int(P - 30), ["a.py"])] + FILL)
            self.assertEqual(r["fixed"], want, dt)

    def test_r1_nearest_run_end_owns_commit(self):
        """R1 (8512a747 case): a commit inside a long fix run, 9 s after a change run ended and 1830 s before the fix
        run ends, belongs to the change run, so it is not a fix."""
        self.evidence((P, 0, "aaaaaaa", False))
        ct = P + 3 * D
        self.ledger([BASE, {"name": FIX, "t0": ct - 6726, "end": ct + 1830}, {"name": "feature", "t0": ct - 1480, "end": ct - 9}])
        log = [("d" * 40, int(ct), ["a.py"]), ("a" * 40, int(P - 30), ["a.py"])] + FILL
        self.assertEqual(self.result(log)["fixed"], 0)
        self.ledger([BASE, {"name": FIX, "t0": ct - 6726, "end": ct + 1830}])   # no change run: the fix run owns it
        self.assertEqual(self.result(log)["fixed"], 1)

    def test_r1_fix_run_nested_in_own_run_not_a_fix(self):
        """R1: a fix run nested in the PASS's own run (change 0..3000, fix 2000..3000) does not own its commit at 2990."""
        self.evidence((P + 100, 0, "aaaaaaa", False))
        self.ledger([{"name": FIX, "t0": P + 2000, "end": P + 3000}, {"name": N, "t0": P, "end": P + 3000}])   # tie: fix row first
        r = self.result([("d" * 40, int(P + 2990), ["a.py"]), ("a" * 40, int(P - 30), ["a.py"])] + FILL)
        self.assertEqual((r["n"], r["fixed"]), (1, 0))

    def test_dirty_resolves_to_next_commit(self):
        self.evidence((P, 0, "aaaaaaa", True))
        self.ledger([BASE, fixrun(P + 300)])
        self.assertEqual(self.result([("e" * 40, int(P + 300), ["x.py"])])["n"], 0)   # landed after the run: unchecked
        r = self.result([("e" * 40, int(P + 300), ["x.py"]), ("a" * 40, int(P + 30), ["x.py"])] + FILL)
        self.assertEqual((r["n"], r["fixed"], r["list"][0]["sha"]), (1, 1, "a" * 12))

    def test_passes_on_one_commit_are_one_entry(self):
        self.ledger([BASE, {"name": N, "t0": P + 100, "end": P + 200}, fixrun(P + 3 * D)])
        self.evidence((P, 0, "aaaaaaa", False), (P + 5, 0, "aaaaaaa", False), (P + 150, 0, "aaaaaaa", False))
        r = self.result([("d" * 40, int(P + 3 * D), ["a.py"]), ("a" * 40, int(P - 30), ["a.py"])] + FILL)
        self.assertEqual((r["n"], r["fixed"], [x["sha"] for x in r["list"]]), (1, 1, ["a" * 12]))

    def test_same_run_commit_not_a_fix(self):
        """R1: a fix run's PASS and the commit that run makes late (inside its grace) is its own work, not a later fix."""
        self.fix = [N]
        self.evidence((P, 0, "aaaaaaa", False))
        r = self.result([("d" * 40, int(P + 800), ["a.py"]), ("a" * 40, int(P - 30), ["a.py"])] + FILL)   # run end P+10
        self.assertEqual((r["n"], r["fixed"]), (1, 0))
        self.ledger([BASE, fixrun(P + 3 * D, name=N)])   # a later run of the same fix pipeline does count
        r = self.result([("d" * 40, int(P + 3 * D), ["a.py"]), ("a" * 40, int(P - 30), ["a.py"])] + FILL)
        self.assertEqual((r["n"], r["fixed"]), (1, 1))

    def test_r2_overlap_on_code_files_only(self):
        """R2: sharing only docs/*.md, refactor/, tests/, screen baselines or CHANGELOG with a fix-run commit is not a fix."""
        self.evidence((P, 0, "aaaaaaa", False))
        self.ledger([BASE, fixrun(P + 3 * D)])
        meta = ["docs/GUIDE.md", "README.md", "refactor/STAGE3.md", "tests/test_a.py", "pkg/test/x_test.go",
                "scripts/screen_baseline/1920-en.json", "CHANGELOG.md", "CHANGELOG"]
        log = [("d" * 40, int(P + 3 * D), list(meta)), ("a" * 40, int(P - 30), ["a.py"] + meta)] + FILL
        self.assertEqual(self.result(log)["fixed"], 0)
        log[0] = ("d" * 40, int(P + 3 * D), meta + ["a.py"])
        self.assertEqual(self.result(log)["fixed"], 1)
        self.assertEqual([f for f in meta + ["scripts/check.sh", "web/js/a.js"] if OC._code(f)], ["scripts/check.sh", "web/js/a.js"])

    def test_r3_measured_false_cases(self):
        """R3: the measured «fix followed» PASSes recompute to 0, except two real fix-run follow-ups."""
        self.now, self.fix = R3_NOW, ["quick-fix", "sidereus-bugfix"]
        self.ledger([{"name": n, "t0": t0, "end": end} for n, t0, end in R3_RUNS])
        self.evidence(*[(ts, 0, h, dr) for _n, _s, ps in R3_CASES for ts, h, dr in ps])
        got = {}
        for name in sorted(set(n for n, _s, _p in R3_CASES)):
            self.git.commits = [(s, ct, list(fs)) for s, ct, fs in R3_LOG]
            OC._OC_MEMO.clear()
            for x in OC.outcome(self.proj, name, [], fix=self.fix)["result"]["list"]:
                got[(name, x["sha"])] = int(x["fixed"])
        # ⚠6580f96d -> b7512c44: a quick-fix run edited the same sidereus/hook_connect.py 10 min later, a real same-code
        # fix-run follow-up that file names cannot tell apart; 96f5d91c (release) is followed by those same two commits
        real = {("sidereus-bugfix", "6580f96de993"), ("release", "96f5d91cb96d")}
        want = dict(((n, s), int((n, s) in real)) for n, s, _p in R3_CASES)
        self.assertEqual(dict((k, got.get(k)) for k in want), want)

    def test_r3_synthetic_fix_run_same_code_file(self):
        """R3: a fix run committing the same code file after the PASS gives 1."""
        self.evidence((P, 0, "aaaaaaa", False))
        self.ledger([BASE, fixrun(P + D)])
        r = self.result([("d" * 40, int(P + D), ["sidereus/x.py", "CHANGELOG.md"]),
                         ("a" * 40, int(P - 30), ["sidereus/x.py", "CHANGELOG.md"])] + FILL)
        self.assertEqual((r["n"], r["fixed"]), (1, 1))

    def test_broke_from_later_fail(self):
        self.evidence((P, 0, "aaaaaaa", False), (P + 5, 1, "aaaaaaa", False))
        r = self.result([("a" * 40, int(P - 30), ["a.py"])])
        self.assertEqual((r["n"], r["broke"]), (1, 1))

    def test_side_branch_commit_not_a_fix(self):
        self.evidence((P, 0, "aaaaaaa", False))
        log = [("d" * 40, int(P + 3 * D), ["a.py"]), ("a" * 40, int(P - 30), ["a.py"])] + FILL
        self.ledger([BASE, fixrun(P + 3 * D)])
        self.git.side = {"d" * 40}
        self.assertEqual(self.result(log)["fixed"], 0)
        self.git.side = set()
        self.assertEqual(self.result(log)["fixed"], 1)

    def test_old_pass_broke_beyond_repo_wide_newest_30(self):
        self.ledger([{"name": N, "t0": P - 100, "end": P + 10}, {"name": "other", "t0": P + 1000, "end": P + 2000}])
        rows = [(P, 0, "c" * 7, False)] + [(P + 1000 + i * 10, 0, "d" * 7, False) for i in range(49)]
        self.evidence(*rows)
        self.tr.gone = {"c" * 7}
        r = self.result([("d" * 40, int(P + 900), ["z.py"]), ("c" * 40, int(P - 30), ["a.py"])])
        self.assertEqual((r["n"], r["broke"], r["unchecked"], r["partial"]), (1, 1, 0, False))

    def test_git_miss_is_unchecked_not_held(self):
        self.evidence((P, 0, "aaaaaaa", False))
        self.tr.fail = True
        r = self.result([("a" * 40, int(P - 30), ["a.py"])])
        self.assertEqual((r["n"], r["unchecked"], r["partial"]), (0, 1, True))
        self.tr.fail = False
        self.evidence((P, 0, "aaaaaaa", True))   # dirty, no commit landed in the run: unchecked, but not a git miss
        r = self.result([("a" * 40, int(P - 3000), ["a.py"])])
        self.assertEqual((r["n"], r["unchecked"], r["partial"]), (0, 1, False))

    def test_pass_outside_run_window_ignored(self):
        self.evidence((P + 500, 0, "aaaaaaa", False))
        self.assertEqual(self.result([("a" * 40, int(P - 30), ["a.py"])])["n"], 0)

    def test_git_argv_read_only(self):
        self.evidence((P, 0, "aaaaaaa", False))
        self.result([("a" * 40, int(P - 30), ["a.py"])])
        self.assertTrue(self.git.calls)
        for a in self.git.calls:
            self.assertFalse({"-p", "--patch", "--stat", "cat-file", "show", "diff"} & set(a), a)
            if a[0] in ("log", "diff-tree"):
                self.assertIn("--name-only", a)
            if a[0] == "rev-list":
                self.assertIn("--ancestry-path", a)

    def test_loopback_split_and_procedure(self):
        lb = [{"f": "review", "g": "impl", "n": 1}]
        self.ledger([{"name": N, "t0": self.now - 40 * D, "end": self.now - 40 * D, "lb": lb, "dc": {}},
                     {"name": N, "t0": self.now - 35 * D, "end": self.now - 35 * D, "lb": [], "dc": {}},
                     {"name": N, "t0": self.now - 2 * D, "end": self.now - 2 * D, "lb": lb, "dc": {"jump": 2, "zz": 5}},
                     {"name": N, "t0": self.now - D, "end": self.now - D, "lb": [{"f": "verify", "g": "impl", "n": 1}], "dc": {}},
                     {"name": "other", "t0": self.now - D, "end": self.now - D, "lb": lb, "dc": {"jump": 9}},
                     {"name": N, "t0": self.now - 70 * D, "end": self.now - 70 * D, "lb": lb, "dc": {}}], junk=True)
        o = OC.outcome(self.proj, N, ["review"])
        self.assertEqual(o["proc"], {"runs": 2, "jump": 2})
        self.assertEqual(o["lb"], {"cur": {"n": 2, "k": 1}, "prev": {"n": 2, "k": 1}})

    def test_ledger_rows_allow_listed(self):
        self.ledger([{"name": N, "t0": 1, "end": 2, "lb": [{"f": "a", "g": "b", "n": 1, "x": "body"}], "deny": 1,
                      "dc": {"jump": 1}, "h0": "abcd123", "h1": "not hex", "msg": "secret"}])
        rows = OC.ledger(OC.repo_key(self.proj), 0)
        self.assertEqual(rows, [{"name": N, "t0": 1.0, "end": 2.0, "lb": [{"f": "a", "g": "b", "n": 1}], "deny": 1,
                                 "dc": {"jump": 1}, "h0": "abcd123", "h1": ""}])

    def test_counts_and_sentences(self):
        o = {"proc": {"runs": 8, "jump": 1}, "lb": {"cur": {"n": 8, "k": 1}, "prev": {"n": 4, "k": 1}},
             "result": {"n": 5, "broke": 1, "fixed": 2, "list": [{"sha": "a", "files": ["x"]}]}}
        c = OC.counts(o)
        self.assertNotIn("list", c["result"])
        self.assertNotIn("files", json.dumps(c))
        self.assertEqual(OC.sentences({"n": 2, "m": 3}, o), [
            "Gate: 2 of 3 gates confirmed able to fail", "Procedure: 8 runs, 1 order violations blocked",
            "Result: 1 of 5 passes broke later, fix followed 2",
            "Review loop-backs: 13% of runs (last 30 days) vs 25% (30 days before)"])   # 12.5 rounds half up
        o["lb"]["prev"] = {"n": 0, "k": 0}
        self.assertEqual(OC.sentences(None, o)[-1], "Review loop-backs: 13% of runs (last 30 days), no earlier data")
        o["lb"]["cur"] = {"n": 0, "k": 0}
        self.assertEqual(len(OC.sentences(None, o)), 3)

    def test_latest_report(self):
        self.assertIsNone(OC.latest_report(self.proj))
        d = os.path.join(self.tmp, "eval", OC.repo_key(self.proj), "reports")
        os.makedirs(d)
        for n in ("2026-10-01.md", "2026-10-09.md", "notes.md"):
            open(os.path.join(d, n), "w", encoding="utf-8").close()
        self.assertEqual(OC.latest_report(self.proj), {"date": "2026-10-09", "path": os.path.join(d, "2026-10-09.md")})

    def test_states_since(self):
        rows = [{"kind": "check", "ts": t, "mode": "fast", "rc": rc, "head": "", "dirty": False,
                 "steps": [{"name": "tests", "rc": rc}]} for t, rc in ((10, 0), (20, 0), (30, 1))]
        st = TR.states(rows, "", 15, git=False)
        self.assertEqual([(s["ts"], s["state"]) for s in st], [(20.0, "broke")])
        st = TR.states(rows, "", 0, git=False, only={10.0})   # filtered to the given PASS set before the cap
        self.assertEqual([(s["ts"], s["state"]) for s in st], [(10.0, "broke")])


if __name__ == "__main__":
    unittest.main()
