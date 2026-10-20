"""arch_map.load: /api/arch body from a temp store (allow list, HEAD reader and store dir patched; no git)."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

AM = sidereus("arch_map")
AV = sidereus("arch_verify")
AP = sidereus("arch_prov")
PLR = sidereus("pl_runs")
BEHIND_OF = AM.behind_of   # real reader; setUp patches the module attribute
C1, C2 = "a" * 40, "b" * 40


class LoadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-archload-"))
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        self.store = os.path.join(self.tmp, "store")
        self.head = C1
        self.allowed = {self.repo}
        roots = lambda p: (os.path.realpath(p) if p and os.path.realpath(p) in self.allowed else "")
        self.p = [mock.patch.object(AM, "ARCH_DIR", self.store), mock.patch.object(AM, "_struct_src_root", roots),
                  mock.patch.object(AM, "head_of", lambda r: self.head),
                  mock.patch.object(AM, "behind_of", lambda r, c: 4),
                  mock.patch.object(AP, "PROV_DIR", os.path.join(self.tmp, "prov")), mock.patch.object(AP, "_MISS", {}),
                  mock.patch.object(PLR, "PLR_DIR", os.path.join(self.tmp, "plmark"))]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, commit, mtime, edges_ok=(True, False), md="```mermaid\nflowchart LR\n```\n", vx=None, **kw):
        d = os.path.join(self.store, AV.repo_key(self.repo), commit)
        os.makedirs(d, exist_ok=True)
        m = {"v": 1, "repo": self.repo, "commit": commit,
             "modules": [{"id": "a", "name": "A", "path": "a", "kind": "module"},
                         {"id": "db", "name": "DB", "path": "", "kind": "external", "ext": "db"}],
             "edges": [{"from": "a", "to": "db", "kind": "di", "label": "pool", "evidence": [{"file": "a/x.py", "line": 3, "symbol": "Pool"}]},
                       {"from": "db", "to": "a", "kind": "call", "label": "", "evidence": [{"file": "b.py", "line": 1, "symbol": "f"}]}]}
        m.update(kw)
        v = {"commit": commit, "total": 2, "passed": 1, "rate": 0.5, "body": "never shown",
             "edges": [{"i": i, "ok": ok, "why": None if ok else "nosym"} for i, ok in enumerate(edges_ok)]}
        v.update(vx or {})
        for name, data in (("map.json", json.dumps(m)), ("verify.json", json.dumps(v)), ("map.md", md)):
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write(data)
        os.utime(os.path.join(d, "verify.json"), (mtime, mtime))

    def test_disallowed_root(self):
        self.allowed = set()
        out = AM.load(self.repo)
        self.assertFalse(out["ok"])
        self.assertNotIn("modules", out)
        self.assertTrue(out["msg"] and out["sidereus"])

    def test_empty_state(self):
        out = AM.load(self.repo)
        self.assertEqual((out["ok"], out["empty"], out["modules"], out["edges"], out["rate"]), (True, True, [], [], None))
        self.assertEqual(out["head"], C1)
        self.assertEqual(out["sidereus"], os.path.realpath(sidereus("config").CODE_DIR))
        self.assertNotIn("msg", out)                    # empty is not an error: the view shows the request button

    def test_loads_newest_and_stale(self):
        self.put(C1, 1000)
        self.put(C2, 2000)
        os.makedirs(os.path.join(self.store, AV.repo_key(self.repo), "not-a-commit"))
        out = AM.load(self.repo)
        self.assertEqual((out["commit"], out["head"], out["stale"], out["rate"]), (C2, C1, True, 0.5))
        self.assertEqual([e["ok"] for e in out["edges"]], [True, False])
        self.assertEqual([e["est"] for e in out["edges"]], [1, 0])
        self.assertEqual(out["modules"][1], {"id": "db", "name": "DB", "path": "", "kind": "external", "ext": "db"})
        self.assertEqual(set(out["edges"][0]), {"from", "to", "kind", "label", "est", "ok", "evidence"})
        self.assertNotIn("never shown", json.dumps(out))
        self.assertFalse(out["empty"])
        self.assertTrue(out["sidereus"])
        self.assertEqual(out["behind"], 4)
        self.head = C2
        self.assertEqual((AM.load(self.repo)["stale"], AM.load(self.repo)["behind"]), (False, None))
        self.head = ""
        self.assertFalse(AM.load(self.repo)["stale"])   # unreadable HEAD is not «stale»

    def test_checks(self):
        self.assertIsNone(AM.load(self.repo)["checks"])                  # empty store
        self.put(C1, 1000)
        self.assertIsNone(AM.load(self.repo)["checks"])                  # old store: no checks-security.json
        d = os.path.join(self.store, AV.repo_key(self.repo), C1)
        with open(os.path.join(d, "checks-security.json"), "w", encoding="utf-8") as f:
            n = {"critical": 1, "high": 0, "medium": 0, "low": 0}
            json.dump({"v": 2, "repo": self.repo, "commit": C1, "dirty": False, "src_changed": False, "at": 5.0,
                       "tools": [{"id": "bandit", "rules": "default", "status": "ok", "ms": 1, "files": 1, "n": n}],
                       "files": {"a/x.py": n}, "items": []}, f)
        c = AM.load(self.repo)["checks"]
        self.assertEqual((c["security"]["mods"], c["security"]["stale"], c["tools"]), ({"a": n}, False, []))
        self.assertIsNone(c["security"]["report"])                      # no report file

    def test_checks_report(self):
        self.put(C1, 1000)
        kdir = os.path.join(self.store, AV.repo_key(self.repo))
        name = "security-report-20261017-0930.md"
        with open(os.path.join(kdir, name), "w", encoding="utf-8") as f:
            f.write("# body never in /api/arch\n")
        os.utime(os.path.join(kdir, name), (1234, 1234))
        c = AM.load(self.repo)["checks"]                                 # a report alone still opens the security shell
        self.assertEqual(c["security"]["report"], {"name": name, "at": 1234})
        self.assertNotIn("body never", json.dumps(c))

    def test_generated_at(self):
        self.put(C1, 1000)
        d = os.path.join(self.store, AV.repo_key(self.repo), C1)
        os.utime(os.path.join(d, "map.json"), (1500, 1500))
        self.assertEqual(AM.load(self.repo)["at"], 1500)          # no field: map.json mtime
        with open(os.path.join(d, "verify.json"), encoding="utf-8") as f:
            v = json.load(f)
        for bad in (True, "1700000000", -5):
            v["at"] = bad
            with open(os.path.join(d, "verify.json"), "w", encoding="utf-8") as f:
                json.dump(v, f)
            self.assertEqual(AM.load(self.repo)["at"], 1500)      # junk field ignored
        v["at"] = 1791469200
        with open(os.path.join(d, "verify.json"), "w", encoding="utf-8") as f:
            json.dump(v, f)
        self.assertEqual(AM.load(self.repo)["at"], 1791469200)    # the field wins over the mtime
        shutil.rmtree(self.store)
        self.assertIsNone(AM.load(self.repo)["at"])                # empty store: no time

    def test_behind_of_git_count(self):
        calls = []

        class R:
            def __init__(self, rc, out):
                self.returncode, self.stdout = rc, out

        def fake(repo, args, timeout):
            calls.append((repo, args))
            return R(*fake.ret)
        with mock.patch.object(AM, "_git_run", fake):
            fake.ret = (0, "7\n")
            self.assertEqual(BEHIND_OF("/r", C1), 7)
            self.assertEqual(calls[0], ("/r", ["rev-list", "--count", C1 + "..HEAD"]))
            fake.ret = (128, "")
            self.assertIsNone(BEHIND_OF("/r", C1))
            self.assertIsNone(BEHIND_OF("/r", "--all"))          # not a commit id: no git call
            self.assertEqual(len(calls), 2)

        def boom(*a):
            raise AM.subprocess.TimeoutExpired("git", 1)
        with mock.patch.object(AM, "_git_run", boom):
            self.assertIsNone(BEHIND_OF("/r", C1))

    def test_style_and_dev(self):
        self.put(C1, 1000)
        out = AM.load(self.repo)
        self.assertEqual((out["style"], out["dev"]), (None, []))          # old store
        self.assertEqual(AM.load(os.path.join(self.tmp, "nope")).get("style"), None)
        st = {"style": "layered", "framework": "F" * 199, "units": "u" * 300, "ok": True, "x": "never shown",
              "evidence": [{"file": "a/%d.py" % k, "ok": True} for k in range(9)] + [{"file": 3}]}
        dev = [{"i": 0, "a": "web", "b": "data"}, {"i": 1, "a": "web", "b": "data"},      # edge 1 failed verification
               {"i": 9, "a": "web", "b": "data"}, {"i": True, "a": "web", "b": "data"}, {"i": 0, "a": "boss", "b": "data"}, 3]
        self.put(C1, 1000, vx={"style": st, "dev": dev})
        out = AM.load(self.repo)
        self.assertEqual(len(out["style"]["evidence"]), 5)
        self.assertEqual((len(out["style"]["framework"]), len(out["style"]["units"])), (80, 120))
        self.assertEqual(set(out["style"]), {"style", "framework", "units", "evidence", "ok"})
        self.assertEqual(out["dev"], [{"i": 0, "a": "web", "b": "data"}])
        self.put(C1, 1000, vx={"style": dict(st, style="bogus"), "dev": "x"})
        out = AM.load(self.repo)
        self.assertEqual((out["style"], out["dev"]), (None, []))
        self.put(C1, 1000, modules=[{"id": "a", "name": "A", "path": "a", "kind": "module", "role": "web"},
                                    {"id": "db", "name": "DB", "path": "", "kind": "external", "ext": "db"}])
        self.assertEqual(AM.load(self.repo)["modules"][0]["role"], "web")

    def put_flows(self, commit, f, v=None):
        d = os.path.join(self.store, AV.repo_key(self.repo), commit)
        for name, data in (("flows.json", f), ("flows.verify.json", v)):
            if data is not None:
                with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(data))

    def test_flows(self):
        self.put(C1, 1000)
        self.assertEqual(AM.load(self.repo)["flows"], [])                 # old store: no flows.json
        self.assertEqual(AM.load(os.path.join(self.tmp, "nope")).get("flows"), None)
        step = {"from": "a", "to": "db", "label": "query", "evidence": {"file": "a/x.py", "line": 3, "symbol": "Pool"}}
        fl = {"id": "login", "name": "Login", "entry": {"kind": "http", "label": "POST /login"}, "steps": [step, dict(step, est=1)]}
        f = {"v": 1, "repo": self.repo, "commit": C1, "flows": [fl, dict(fl, id="bad", entry={"kind": "rpc", "label": "x"})]}
        v = {"v": 1, "commit": C1, "flows": [{"id": "login", "ok": True, "steps": [{"ok": True, "why": None}]}], "body": "never shown"}
        self.put_flows(C1, f, v)
        out = AM.load(self.repo)
        self.assertEqual([x["id"] for x in out["flows"]], ["login"])      # broken flow dropped alone
        x = out["flows"][0]
        self.assertEqual(set(x), {"id", "name", "entry", "ok", "steps"})
        self.assertEqual(x["steps"][0], dict(step, est=0, ok=True, why=None))
        self.assertEqual((x["steps"][1]["ok"], x["steps"][1]["why"], x["steps"][1]["est"]), (False, "unchecked", 1))  # no verdict
        self.assertFalse(x["ok"])
        self.assertNotIn("never shown", json.dumps(out))
        self.put_flows(C1, f, dict(v, commit=C2))                         # verdict of another commit: unchecked
        self.assertEqual(AM.load(self.repo)["flows"][0]["steps"][0]["why"], "unchecked")
        self.put_flows(C1, dict(f, flows=[fl] * 41))                      # over FLOW_MAX: the whole file is refused
        self.assertEqual(AM.load(self.repo)["flows"], [])
        self.put_flows(C1, dict(f, extra=1))
        self.assertEqual(AM.load(self.repo)["flows"], [])

    def test_md_rebuilt_and_bad_store(self):
        self.put(C1, 1000, md="flowchart LR\n  hand --> edited\n")
        md = AM.load(self.repo)["md"]                   # stored map.md ignored: rebuilt from the verified edges
        self.assertNotIn("hand", md)
        self.assertIn('n0 -.->|"pool"| n1', md)
        self.assertNotIn("n1 -", md)                    # edge 1 failed verification
        self.put(C1, 1000, modules=[{"id": "a", "name": "x" * 61, "path": "", "kind": "module"}], edges=[])
        out = AM.load(self.repo)
        self.assertEqual((out["ok"], out.get("bad"), out["modules"]), (True, True, []))
        self.put(C1, 1000, repo="/elsewhere")            # map from another repo's store is refused
        self.assertTrue(AM.load(self.repo).get("bad"))

    def prov(self, commit, vt, **kw):
        p = dict({"v": 1, "plat": "cc", "sid": "aaaabbbb-1111", "model": "opus-4-1",
                  "stages": [{"t": "Draw", "model": "sonnet-4-5"}], "at": vt, "vt": vt}, **kw)
        fp = os.path.join(AP.PROV_DIR, AV.repo_key(self.repo), commit + ".json")
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(p, f)

    def test_r3_old_store_prov_none_rest_unchanged(self):
        # R3: a map saved before provenance existed loads with prov null and every other key as before.
        self.put(C1, 1000)
        with open(os.path.join(self.store, AV.repo_key(self.repo), C1, "prov.json"), "w", encoding="utf-8") as f:
            json.dump({"v": 1, "plat": "cc", "sid": "aaaabbbb-1111", "model": "forged", "stages": [], "vt": 1000}, f)
        out = AM.load(self.repo)
        self.assertIsNone(out["prov"])                  # R1: a prov file inside the agent-writable store is never read
        self.prov(C1, 1000)
        out2 = AM.load(self.repo)
        self.assertEqual(out2["prov"], {"v": 1, "plat": "cc", "sid": "aaaabbbb-1111", "model": "opus-4-1",
                                        "stages": [{"t": "Draw", "model": "sonnet-4-5"}], "at": 1000.0, "vt": 1000.0})
        out.pop("prov"), out2.pop("prov")
        self.assertEqual(out, out2)
        self.assertIsNone(AM.load(os.path.join(self.tmp, "nope")).get("prov"))   # disallowed body has no prov key

    def test_r3_vt_mismatch_none(self):
        self.put(C1, 1000)
        self.prov(C1, 1003)                             # written for an older gate run of the same commit
        self.assertIsNone(AM.load(self.repo)["prov"])
        self.prov(C1, 1001.5)
        self.assertEqual(AM.load(self.repo)["prov"]["model"], "opus-4-1")

    def test_r3_invalid_model_none(self):
        self.put(C1, 1000)
        for bad in ({"model": "<img onerror=x>"}, {"model": "x" * 41}, {"plat": "zz"}, {"sid": "../x"},
                    {"stages": [{"t": "a", "model": "bad\"q"}]}, {"stages": "x"}):
            self.prov(C1, 1000, **bad)
            self.assertIsNone(AM.load(self.repo)["prov"], bad)
        self.assertEqual(AM.load(self.repo)["empty"], False)


if __name__ == "__main__":
    unittest.main()
