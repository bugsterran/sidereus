"""Harness «Red→Green»/«Pass stability» trail (sidereus/harness_trail.py). `_git` and `_now` are patched; no real git runs."""
import unittest

from tests._load import load, sidereus

load()
TR = sidereus("harness_trail")
HEAD = "f" * 40


def _row(ts, mode, rc, head="aaaa111", dirty=False, steps=None):
    steps = steps if steps is not None else [("tests", rc)]
    return {"kind": "check", "ts": ts, "mode": mode, "head": head, "dirty": dirty, "rc": rc,
            "steps": [{"name": n, "rc": r, "n": 1, "failed": int(r != 0), "secs": 1.0} for n, r in steps]}


def _newest_first(*rows):
    return sorted(rows, key=lambda r: -r["ts"])


class FakeGit(object):
    """Answers by command; `fail` makes every call a git failure."""

    def __init__(self, gone=(), reverted=(), count=3, fail=False):
        self.calls, self.gone, self.reverted, self.count, self.fail = [], set(gone), set(reverted), count, fail

    def __call__(self, repo, args):
        self.calls.append(list(args))
        if self.fail:
            return None
        cmd = args[0]
        if cmd == "rev-parse" and args[-1] == "HEAD":
            return 0, HEAD + "\n"
        if cmd == "merge-base":
            return (1, "") if args[2] in self.gone else (0, "")
        if cmd == "rev-parse":
            return 0, "1" * 40 + "\n"   # tree of <head>^
        if cmd == "log":
            h = args[-1].split("..")[0]
            tree = "1" * 40 if h in self.reverted else "2" * 40
            return 0, "%s\t%s\n" % ("9" * 40, tree)
        if cmd == "rev-list":
            return 0, "%d\n" % self.count
        return 128, ""


class TrailTest(unittest.TestCase):
    def setUp(self):
        self.saved = (TR._git, TR._now)
        TR._now = lambda: 1000.0
        TR._TR_CACHE.clear()
        self.git = FakeGit()
        TR._git = self.git

    def tearDown(self):
        TR._git, TR._now = self.saved
        TR._TR_CACHE.clear()

    def test_keys_pinned(self):
        t = TR.trail(_newest_first(_row(1, "fast", 1, head="aaaa111"), _row(2, "fast", 0, head="bbbb222")), "/r")
        self.assertEqual(sorted(t), ["fixes", "held"])
        self.assertEqual(sorted(t["fixes"][0]), ["commits", "fail", "flipped", "mode", "pass", "still"])
        self.assertEqual(sorted(t["fixes"][0]["fail"]), ["dirty", "head", "ts"])
        self.assertEqual(sorted(t["held"][0]), ["at", "dirty", "git", "head", "mode", "state", "steps", "ts"])
        self.assertEqual(t["fixes"][0]["commits"], 3)

    def test_pairs_per_mode_only(self):
        t = TR.trail(_newest_first(_row(1, "fast", 1), _row(2, "full", 0)), "/r", git=False)
        self.assertEqual(t["fixes"], [])
        t = TR.trail(_newest_first(_row(1, "fast", 1), _row(2, "full", 0), _row(3, "fast", 0)), "/r", git=False)
        self.assertEqual([(f["mode"], f["fail"]["ts"], f["pass"]["ts"]) for f in t["fixes"]], [("fast", 1, 3)])

    def test_hook_modes_pair_per_kind(self):
        rows = [_row(1, "hook-test", 1, steps=[("test", 1)]), _row(2, "hook-build", 0, steps=[("build", 0)])]
        self.assertEqual(TR.trail(_newest_first(*rows), "/r", git=False)["fixes"], [])
        rows.append(_row(3, "hook-test", 0, steps=[("test", 0)]))
        fx = TR.trail(_newest_first(*rows), "/r", git=False)["fixes"]
        self.assertEqual([(f["mode"], f["fail"]["ts"], f["pass"]["ts"], f["flipped"]) for f in fx], [("hook-test", 1, 3, ["test"])])

    def test_flipped_and_still(self):
        f = _row(1, "full", 1, steps=[("py", 0), ("tests", 1), ("leak", 1), ("old", 0)])
        p = _row(2, "full", 0, steps=[("py", 0), ("tests", 0), ("leak", 1), ("screen", 0)])
        fx = TR.trail(_newest_first(f, p), "/r", git=False)["fixes"][0]
        self.assertEqual(fx["flipped"], ["tests"])
        self.assertEqual(fx["still"], ["leak"])                  # old/screen ran in one run only: not «still»

    def test_broke_then_refixed(self):
        rows = [_row(1, "fast", 0, steps=[("tests", 0), ("lint", 0)]), _row(2, "full", 1),
                _row(3, "fast", 1, steps=[("lint", 1)])]
        h = TR.trail(_newest_first(*rows), "/r", git=False)["held"]
        self.assertEqual((h[0]["state"], h[0]["steps"], h[0]["at"]), ("broke", ["lint"], 3))
        h = TR.trail(_newest_first(*(rows + [_row(4, "fast", 0)])), "/r", git=False)["held"]
        self.assertEqual([x["state"] for x in h], ["held", "refixed"])

    def test_non_overlapping_fail_holds(self):
        rows = [_row(1, "fast", 0, steps=[("tests", 0)]), _row(2, "fast", 1, steps=[("lint", 1)])]
        self.assertEqual(TR.trail(_newest_first(*rows), "/r", git=False)["held"][0]["state"], "held")

    def test_dirty_unchecked_without_git(self):
        h = TR.trail([_row(1, "fast", 0, dirty=True)], "/r")["held"][0]
        self.assertEqual((h["state"], h["git"]), ("unchecked", False))
        self.assertEqual([c for c in self.git.calls if c[0] != "rev-parse" or c[-1] != "HEAD"], [])

    def test_git_gone_reverted_held(self):
        self.git.gone, self.git.reverted = {"aaaa111"}, {"bbbb222"}
        rows = [_row(1, "a", 0, head="aaaa111"), _row(2, "b", 0, head="bbbb222"), _row(3, "c", 0, head="cccc333"),
                _row(4, "d", 0, head=HEAD[:7])]
        h = TR.trail(_newest_first(*rows), "/r")["held"]
        self.assertEqual([(x["head"], x["state"], x["git"]) for x in h],
                         [(HEAD[:7], "held", True), ("cccc333", "held", True), ("bbbb222", "reverted", True),
                          ("aaaa111", "gone", True)])
        for c in self.git.calls:   # hash-only formats
            self.assertFalse(any("%s" in a or a == "--stat" for a in c), c)

    def test_git_error_evidence_only(self):
        TR._git = FakeGit(fail=True)
        t = TR.trail(_newest_first(_row(1, "fast", 1, head="aaaa111"), _row(2, "fast", 0, head="bbbb222")), "/r")
        self.assertEqual((t["held"][0]["state"], t["held"][0]["git"], t["fixes"][0]["commits"]), ("held", False, None))
        self.assertEqual(TR._TR_CACHE, {})

    def test_caps_and_spawn_budget(self):
        rows = []
        for i in range(8):
            rows += [_row(10 * i + 1, "m%d" % i, 1, head="%04x" % (i + 1)), _row(10 * i + 2, "m%d" % i, 0, head="%04x" % (i + 100))]
        t = TR.trail(_newest_first(*rows), "/r")
        self.assertEqual((len(t["fixes"]), len(t["held"])), (5, 5))
        self.assertEqual(t["held"][0]["ts"], 72)
        self.assertLessEqual(len(self.git.calls), TR.TR_SPAWN_MAX)

    def test_junk_ignored(self):
        rows = [None, "x", {"kind": "red", "ts": 5, "mode": "fast", "rc": 0}, {"kind": "check", "ts": 0, "mode": "fast", "rc": 0},
                {"kind": "check", "ts": 3, "mode": "BAD MODE", "rc": 0}, {"kind": "check", "ts": 4, "mode": "fast", "rc": True},
                _row(2, "fast", 0, head="<b>")]
        h = TR.trail(rows, "/r", git=False)["held"]
        self.assertEqual([(x["ts"], x["head"]) for x in h], [(2, "")])
        self.assertEqual(TR.trail("nope", "/r"), {"fixes": [], "held": []})

    def test_cache_second_call_no_git(self):
        rows = _newest_first(_row(1, "fast", 1, head="aaaa111"), _row(2, "fast", 0, head="bbbb222"))
        first = TR.trail(rows, "/r")
        n = len(self.git.calls)
        self.assertGreater(n, 0)
        self.assertEqual(TR.trail(rows, "/r"), first)
        self.assertEqual(len(self.git.calls), n)


if __name__ == "__main__":
    unittest.main()
