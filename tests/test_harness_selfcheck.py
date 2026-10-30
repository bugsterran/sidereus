"""Harness «Guard self-check»: the runner (scripts/harness_selfcheck.py) writes 11 passing cases to --out, the loader
(sidereus/harness_selfcheck.py) whitelists the file field by field, and harness_plat._results carries it.
Temp files only; HEAD lookups (`_head` on both modules) are patched, so no live repo, clock or network is read."""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import ROOT, load, sidereus

load()
HSC, HP = sidereus("harness_selfcheck"), sidereus("harness_plat")
SHA = "a" * 40


def _mod(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


RUN = _mod("harness_selfcheck_cli_t", "scripts/harness_selfcheck.py")


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="hsc-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.fp = os.path.join(self.tmp, "harness-selfcheck.json")
        for o, k, v in ((HSC, "HSC_FILE", self.fp), (HSC, "_head", lambda root: SHA)):
            p = mock.patch.object(o, k, v)
            p.start()
            self.addCleanup(p.stop)

    def write(self, doc):
        with open(self.fp, "w", encoding="utf-8") as f:
            f.write(doc if isinstance(doc, str) else json.dumps(doc))


class Runner(_Tmp):
    def test_main_writes_all_cases(self):
        with mock.patch.object(RUN, "_head", lambda: SHA), mock.patch("sys.stdout"):
            rc = RUN.main(["--out", self.fp])
        self.assertEqual(rc, 0)
        with open(self.fp, encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual((d["v"], d["head"]), (1, SHA))
        cs = dict((c["name"], c) for c in d["cases"])
        self.assertEqual(len(cs), 11)
        self.assertEqual([n for n, c in cs.items() if c["pass"] is not True], [])
        for n, c in cs.items():
            self.assertNotEqual(cs[c["pair"]]["expect"], c["expect"], n)
            self.assertEqual(cs[c["pair"]]["guard"], c["guard"], n)
        self.assertEqual(cs["guard-jump"]["codes"], ["jump"])
        # the loader reads exactly what the runner wrote
        v = HSC.load(ROOT, 0)
        self.assertEqual((v["state"], v["stale"], len(v["cases"])), ("ok", False, 11))
        self.assertEqual(v["cases"][0], d["cases"][0])

    def test_missing_fixtures(self):
        with mock.patch.object(RUN, "FX", os.path.join(self.tmp, "none")), mock.patch("sys.stdout"):
            self.assertEqual(RUN.main(["--out", self.fp]), 2)
        self.assertFalse(os.path.exists(self.fp))

    def test_empty_fixtures(self):
        os.makedirs(os.path.join(self.tmp, "empty"))
        with mock.patch.object(RUN, "FX", os.path.join(self.tmp, "empty")), mock.patch("sys.stdout"):
            self.assertEqual(RUN.main(["--out", self.fp]), 2)
        self.assertFalse(os.path.exists(self.fp))


class Loader(_Tmp):
    def test_missing_file(self):
        v = HSC.load(ROOT, 0)
        self.assertEqual((v["state"], v["cases"], v["cmd"]), ("none", [], "python3 scripts/harness_selfcheck.py"))

    def test_bad_json_and_version(self):
        self.write("{not json")
        self.assertEqual(HSC.load(ROOT, 0)["state"], "none")
        self.write({"v": 2, "cases": []})
        self.assertEqual(HSC.load(ROOT, 0)["state"], "none")
        self.write("[" * 100000 + "]" * 100000)   # under HSC_READ_MAX, deep enough to raise RecursionError
        self.assertEqual(HSC.load(ROOT, 0)["state"], "none")

    def test_fields_dropped_one_by_one(self):
        good = {"name": "guard-jump", "guard": "guard", "situation": "s", "expect": "blocked", "actual": "blocked",
                "pass": True, "pair": "guard-jump-declared", "codes": ["jump"]}
        bad = dict(good, guard="other", situation="x" * 201, pair=5, codes=["jump", "BAD CODE", 3], extra="drop")
        bad["pass"] = "yes"   # non-bool pass is rejected, not coerced
        self.write({"v": 1, "ts": 5, "head": SHA, "cases": [good, bad, "junk"] + [good] * 40})
        v = HSC.load(ROOT, 0)
        self.assertEqual((v["state"], v["ts"], v["head"], v["stale"]), ("ok", 5, SHA, False))
        self.assertEqual(len(v["cases"]), 31)   # 32 read, the string dropped
        self.assertEqual(v["cases"][0], good)
        b = v["cases"][1]
        self.assertEqual((b["guard"], b["situation"], b["pass"], b["pair"], b["codes"]), (None, None, None, None, ["jump"]))
        self.assertEqual((b["name"], b["expect"]), ("guard-jump", "blocked"))
        self.assertNotIn("extra", b)

    def test_head_mismatch_is_stale(self):
        self.write({"v": 1, "ts": 1, "head": "b" * 40, "cases": []})
        self.assertTrue(HSC.load(ROOT, 0)["stale"])
        self.write({"v": 1, "ts": 1, "head": "not-hex; rm", "cases": []})
        v = HSC.load(ROOT, 0)
        self.assertEqual((v["head"], v["stale"]), ("", True))

    def test_head_memo(self):
        calls = []
        g = mock.Mock(returncode=0, stdout=SHA + "\n")
        with mock.patch.dict(HSC._HSC_MEMO, clear=True), mock.patch.object(HSC, "_now", lambda: 100.0), \
                mock.patch.object(HSC.gitinfo, "_git_run", lambda *a, **k: calls.append(a) or g):
            self.assertEqual((_REAL_HEAD("/r"), _REAL_HEAD("/r")), (SHA, SHA))
        self.assertEqual(len(calls), 1)


_REAL_HEAD = HSC._head


class Plat(_Tmp):
    def test_results_carries_selfcheck(self):
        self.write({"v": 1, "ts": 1, "head": SHA, "cases": []})
        proj = os.path.join(self.tmp, "proj")
        os.makedirs(proj)
        sc = HP._results(proj)["selfcheck"]
        self.assertEqual((sc["state"], sc["head"]), ("ok", SHA))


if __name__ == "__main__":
    unittest.main()
