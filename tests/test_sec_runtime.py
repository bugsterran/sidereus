"""sidereus/sec_runtime.py (Harness runtime patch card): R2 stale, R3 none + cmd on any bad file, R4 fix keys, atomic
0644 write; scripts/arch_checks.py `_rt_write`. Temp dirs only — no live files, clock or network."""
import copy
import importlib.util
import json
import os
import shutil
import stat
import tempfile
import unittest
from unittest import mock

from tests._load import ROOT, load, sidereus

load()
SRT = sidereus("sec_runtime")
AV = sidereus("arch_verify")
NOW = 1_800_000_000.0
D = 86400


def _item(**kw):
    it = {"rt": "nodejs", "path": "/opt/homebrew/opt/node@22/bin/node", "cls": "homebrew", "viewer": False, "cur": "22.1.0",
          "cycle": "22", "level": "ok",
          "patch": {"level": "ok", "target": "22.1.0", "security": False, "eol": "2027-04-30", "eol_past": False},
          "newest": {"level": "ok", "target": "22.1.0", "behind_n": 0}}
    it.update(kw)
    return it


def _doc(items=None, age_d=1, **kw):
    d = {"at": NOW - age_d * D, "report": "security-report-20261027-0900.md", "dev": True, "offline": False,
         "items": [_item()] if items is None else items}
    d.update(kw)
    return d


class Shape(unittest.TestCase):
    def test_ok_fresh(self):
        b = SRT.shape(_doc(), NOW)
        self.assertEqual((b["state"], b["age_d"], b["stale"], b["items"][0]["fix"]), ("ok", 1, False, "brew-node"))
        self.assertIn("--repo", b["cmd"])
        self.assertIn("--dev", b["cmd"])

    def test_r2_stale_8d_never_fresh_ok(self):
        b = SRT.shape(_doc(age_d=8), NOW)
        self.assertEqual((b["age_d"], b["stale"]), (8, True))
        self.assertEqual(SRT.shape(_doc(age_d=7), NOW)["stale"], False)

    def test_states(self):
        warn = _item(patch=dict(_item()["patch"], level="warn", target="22.1.1"))
        unk = _item(patch=dict(_item()["patch"], level="unknown", target=""), newest={"level": "unknown", "target": "", "behind_n": 0})
        info = _item(newest={"level": "info", "target": "26.0.0", "behind_n": 2})
        self.assertEqual(SRT.shape(_doc([warn, unk]), NOW)["state"], "behind")
        self.assertEqual(SRT.shape(_doc([unk, info]), NOW)["state"], "unknown")
        self.assertEqual(SRT.shape(_doc([info]), NOW)["state"], "ok")   # info is not behind
        self.assertEqual(SRT.shape(_doc([]), NOW)["state"], "unknown")   # nothing listed is never ok
        self.assertEqual(SRT.shape(_doc([info]), NOW)["items"][0]["level"], "info")   # level recomputed
        self.assertEqual(SRT.shape(_doc([dict(warn, level="ok")]), NOW)["items"][0]["level"], "warn")

    def test_r3_bad_docs_none_with_cmd(self):
        bad = [None, [], _doc(at=0), _doc(at=True), _doc(dev="x"), _doc(report="../x"), _doc(items=[_item()] * 21),
               _doc([_item(rt="ruby")]), _doc([_item(cls="weird")]), _doc([_item(cur="v22")]),
               _doc([_item(cur="22.1.0; rm")]), _doc([_item(path="a\nb")]),
               _doc([_item(patch=dict(_item()["patch"], level="great"))]),
               _doc([_item(patch=dict(_item()["patch"], target="latest"))]),
               _doc([_item(patch=dict(_item()["patch"], eol="soon"))]),
               _doc([_item(newest={"level": "info", "target": "26.0.0", "behind_n": -1})])]
        for d in bad:
            b = SRT.shape(d, NOW)
            self.assertEqual((b["state"], b["at"], b["age_d"], b["items"]), ("none", 0, None, []), d)
            self.assertTrue(b["cmd"].startswith("python3 "))

    def test_non_finite_at_none(self):
        for at in (float("inf"), float("nan")):
            self.assertEqual(SRT.shape(_doc(at=at), NOW)["state"], "none")
        self.assertEqual(SRT.shape(json.loads('{"at": Infinity, "report": "", "dev": true, "offline": false, "items": []}'),
                                   NOW)["state"], "none")

    def test_r4_fix_whitelist_recomputed(self):
        rows = [_item(), _item(rt="python", cls="homebrew"), _item(rt="python", cls="system", path="/usr/bin/python3"),
                _item(rt="nodejs", cls="other"), dict(_item(), fix="rm -rf /")]
        self.assertEqual([x["fix"] for x in SRT.shape(_doc(rows), NOW)["items"]],
                         ["brew-node", "brew-python", "system-python", "other", "brew-node"])

    def test_metadata_only_keys(self):
        it = SRT.shape(_doc([dict(_item(), out="PLANTED-OUTPUT")]), NOW)["items"][0]
        self.assertEqual(set(it), {"rt", "path", "cls", "viewer", "cur", "cycle", "level", "patch", "newest", "fix"})


class ViewWrite(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="sidereus-rt-")
        self.addCleanup(shutil.rmtree, self.d, True)
        self.fp = os.path.join(self.d, SRT.DEPS_FILE)

    def test_missing_none(self):
        self.assertEqual(SRT.view(self.d, NOW)["state"], "none")

    def test_write_atomic_0644_roundtrip(self):
        SRT.write(self.d, _doc())
        self.assertEqual(stat.S_IMODE(os.stat(self.fp).st_mode), 0o644)
        self.assertEqual([n for n in os.listdir(self.d) if n.startswith(".arch-")], [])
        self.assertEqual(SRT.view(self.d, NOW)["state"], "ok")

    def test_symlink_oversize_bad_json(self):
        real = os.path.join(self.d, "real.json")
        with open(real, "w", encoding="utf-8") as f:
            json.dump(_doc(), f)
        os.symlink(real, self.fp)
        self.assertEqual(SRT.view(self.d, NOW)["state"], "none")
        os.remove(self.fp)
        with open(self.fp, "w", encoding="utf-8") as f:
            f.write(" " * (SRT.MAX_BYTES + 1))
        self.assertEqual(SRT.view(self.d, NOW)["state"], "none")
        with open(self.fp, "w", encoding="utf-8") as f:
            f.write("{nope")
        self.assertEqual(SRT.view(self.d, NOW)["state"], "none")
        os.remove(self.fp)
        os.mkdir(self.fp)
        self.assertEqual(SRT.view(self.d, NOW)["state"], "none")


class RunnerWrite(unittest.TestCase):
    """scripts/arch_checks.py stores the deps_audit runtime dict; nothing without one."""
    def setUp(self):
        spec = importlib.util.spec_from_file_location("arch_checks_cli_rt", os.path.join(ROOT, "scripts", "arch_checks.py"))
        self.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cli)
        self.d = tempfile.mkdtemp(prefix="sidereus-rt-")
        self.addCleanup(shutil.rmtree, self.d, True)
        p = mock.patch.object(AV, "ARCH_DIR", self.d)
        p.start()
        self.addCleanup(p.stop)

    def test_rt_write(self):
        self.assertFalse(self.cli._rt_write(NOW, "r.md", True, []))
        self.assertFalse(os.path.exists(os.path.join(self.d, SRT.DEPS_FILE)))
        self.assertFalse(self.cli._rt_write(NOW, "r.md", False, [{"offline": True, "items": [_item()]}]))   # no --dev
        self.assertFalse(os.path.exists(os.path.join(self.d, SRT.DEPS_FILE)))
        self.assertTrue(self.cli._rt_write(NOW, "r.md", True, [{"offline": True, "items": [_item()]}]))
        b = SRT.view(self.d, NOW)
        self.assertEqual((b["state"], b["offline"], b["report"], b["dev"]), ("ok", True, "r.md", True))

    def test_deps_passes_rich(self):
        seen = []

        class Deps:
            @staticmethod
            def collect(argv, rich=None):
                seen.append(argv)
                rich.append({"offline": False, "items": []})
                return []
        rich = []
        with mock.patch.object(self.cli, "SIDEREUS_ROOT", os.path.realpath(self.d)), \
                mock.patch.object(self.cli, "_load_deps", lambda: Deps):
            self.assertEqual(self.cli._deps(self.d, True, True, rich), [])
        self.assertEqual((seen, rich), ([["--dev", "--offline"]], [{"offline": False, "items": []}]))


class Demo(unittest.TestCase):
    def test_demo_runtime_card(self):
        DT = sidereus("demo_tools")
        a = NOW
        b = SRT.shape(DT._demo_runtime(a), a, root="/Users/demo/src/sidereus")
        self.assertEqual((b["state"], b["age_d"], b["stale"]), ("behind", 9, True))
        lv = {x["path"]: (x["level"], x["patch"]["level"], x["newest"]["behind_n"], x["fix"]) for x in b["items"]}
        self.assertEqual(lv, {"/opt/homebrew/opt/node@22/bin/node": ("warn", "warn", 2, "brew-node"),
                              "/usr/bin/python3": ("fail", "fail", 5, "system-python"),
                              "/opt/homebrew/opt/node@24/bin/node": ("info", "ok", 1, "brew-node"),
                              "/opt/homebrew/opt/python@3.10/bin/python3.10": ("fail", "fail", 4, "brew-python")})
        self.assertNotIn(ROOT, b["cmd"])
        self.assertEqual(copy.deepcopy(b), json.loads(json.dumps(b)))


if __name__ == "__main__":
    unittest.main()
