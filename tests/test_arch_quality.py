"""arch_quality: fail/warn checks on fixture maps; scripts/arch_verify.py exits 1 on a quality fail (git faked)."""
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests._load import ROOT, sidereus

AV = sidereus("arch_verify")
AQ = sidereus("arch_quality")
C = "c" * 40


def mod(i, name=None, kind="module"):
    return {"id": i, "name": name or i.upper(), "path": i, "kind": kind}


def edge(f, t, label="uses", kind="call", sym="run"):
    return {"from": f, "to": t, "kind": kind, "label": label, "evidence": [{"file": f + "/x.py", "line": 1, "symbol": sym}]}


def flow(fid, pairs, kind="http", label=None):
    return {"id": fid, "name": fid, "entry": {"kind": kind, "label": label or "/" + fid},
            "steps": [{"from": a, "to": b, "label": "x", "evidence": {"file": "a/x.py", "line": 1, "symbol": "s"}}
                      for a, b in pairs]}


def amap(mods, edges, v=1):
    return {"v": v, "repo": "/r", "commit": C, "modules": mods, "edges": edges}


MODS = [mod(x) for x in "abcdefghijklmn"]
BASE = amap(MODS, [edge(x, y) for x, y in zip("abcdefghijklm", "bcdefghijklmn")])


def checks(q, key):
    return [x["check"] for x in q[key]]


def chain(ids):
    return list(zip(ids, ids[1:]))


class OverlapTest(unittest.TestCase):
    def test_boundary(self):
        # 79 shared of 100 in the union -> 0.79 passes; 80 of 100 fails.
        common = [("c%d" % i, "d%d" % i) for i in range(79)]
        a = common + [("a%d" % i, "x") for i in range(10)]
        b = common + [("b%d" % i, "x") for i in range(11)]
        self.assertEqual(AQ.check(BASE, [flow("f1", a), flow("f2", b)])["warn"], [])
        common = [("c%d" % i, "d%d" % i) for i in range(80)]
        a = common + [("a%d" % i, "x") for i in range(10)]
        b = common + [("b%d" % i, "x") for i in range(10)]
        q = AQ.check(BASE, [flow("f1", a), flow("f2", b)])
        self.assertEqual(q["fail"], [])                           # warn-only until more maps are measured
        f = [x for x in q["warn"] if x["check"] == "flow-overlap"][0]
        self.assertEqual((f["n"], f["max"], f["items"]), (1, 0.8, ["f1~f2"]))

    def test_short_flows_exempt(self):
        p = chain("abc")
        self.assertEqual(AQ.check(BASE, [flow("f1", p), flow("f2", p)])["warn"], [])
        p = chain("abcd")
        self.assertEqual(checks(AQ.check(BASE, [flow("f1", p), flow("f2", p)]), "warn"), ["flow-overlap"])


class LabelTargetTest(unittest.TestCase):
    def test_import_name_passes(self):
        m = amap([mod("arch"), mod("gitinfo", "Git info")], [edge("arch", "gitinfo", "imports gitinfo", "import")] * 4)
        self.assertEqual(AQ.check(m, [])["fail"], [])

    def test_name_only_labels_fail(self):
        m = amap([mod("a"), mod("db", "Main DB")], [edge("a", "db", "main db")] * 3)
        q = AQ.check(m, [])
        self.assertEqual([(x["check"], x["n"], x["of"]) for x in q["fail"]], [("label-target", 3, 3)])

    def test_hangul_subset_fails(self):
        name = "사용자 관리"
        m = amap([mod("a"), mod("user", name)], [edge("a", "user", "사용자")] * 3)
        self.assertEqual(checks(AQ.check(m, []), "fail"), ["label-target"])

    def test_camel_id_echo_fails(self):
        m = amap([mod("a"), mod("sessionStore", "Store")], [edge("a", "sessionStore", "session store")] * 3)
        self.assertEqual(checks(AQ.check(m, []), "fail"), ["label-target"])

    def test_source_has_no_hangul(self):
        with open(os.path.join(ROOT, "sidereus", "arch_quality.py"), encoding="utf-8") as f:
            self.assertFalse(any("\uac00" <= c <= "\ud7a3" for c in f.read()))

    def test_under_floor_passes(self):
        m = amap([mod("a"), mod("db", "Main DB")], [edge("a", "db", "db"), edge("a", "db", "db"), edge("a", "db", "reads rows")])
        self.assertEqual(AQ.check(m, [])["fail"], [])

    def test_under_ratio_passes(self):
        es = [edge("a", "db", "db")] * 3 + [edge("a", "db", "reads rows")] * 10
        self.assertEqual(AQ.check(amap([mod("a"), mod("db")], es), [])["fail"], [])


class EntryDupTest(unittest.TestCase):
    def test_same_label_same_kind_fails(self):
        q = AQ.check(BASE, [flow("f1", [("a", "b")], label="/Login "), flow("f2", [("c", "d")], label="/login")])
        f = q["fail"][0]
        self.assertEqual((f["check"], f["items"]), ("entry-dup", ["http /login"]))

    def test_different_kind_passes(self):
        q = AQ.check(BASE, [flow("f1", [("a", "b")], label="sync"), flow("f2", [("c", "d")], "cli", "sync")])
        self.assertEqual(q["fail"], [])


class WarnTest(unittest.TestCase):
    def test_accessor(self):
        m = amap([mod("a"), mod("b"), mod("c")],
                 [edge("a", "b", sym="user.getId"), edge("a", "c", sym="Svc.getCodeMasListBy()"),
                  edge("b", "c", sym="setMainView"), edge("c", "a", sym="loadAll")])
        q = AQ.check(m, [])
        self.assertEqual(q["fail"], [])                           # accessor names only ever warn
        w = q["warn"][0]                                          # getCodeMasListBy has 4 words: not an accessor
        self.assertEqual((w["check"], w["n"], w["of"], w["max"], w["items"]), ("accessor-call", 2, 4, 0.5, ["a>b", "b>c"]))

    def test_isolated(self):
        m = amap([mod("a"), mod("b"), mod("c")], [edge("a", "b")])
        self.assertEqual([(x["check"], x["items"]) for x in AQ.check(m, [])["warn"]], [("isolated", ["c"])])
        self.assertEqual(AQ.check(amap([mod("a"), mod("b")], []), [])["warn"], [])

    def test_store_rw_v2_only(self):
        mods = [mod("a"), mod("s1", kind="store"), mod("s2", kind="store")]
        es = [edge("a", "s1", kind="read"), edge("a", "s2", kind="call")]
        self.assertEqual([(x["check"], x["items"]) for x in AQ.check(amap(mods, es, 2), [])["warn"]], [("store-rw", ["s2"])])
        self.assertEqual(AQ.check(amap(mods, es, 1), [])["warn"], [])


class MainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-archq-"))
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        files = {"a/x.py": ["def go():", "    return main_db()"], "db/y.py": ["def main_db():", "    pass"]}
        self.p = [mock.patch.object(AV, "ARCH_DIR", os.path.join(self.tmp, "store")),
                  mock.patch.object(AV, "_tree", lambda r, c: set(files)),
                  mock.patch.object(AV, "_show", lambda r, c, rel: list(files.get(rel, []))),
                  mock.patch.object(AV, "_grep", lambda r, c, s: [f for f, ls in files.items() if any(s in x for x in ls)])]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cli(self, label, flows=None):
        m = {"v": 1, "repo": self.repo, "commit": C,
             "modules": [{"id": "a", "name": "A", "path": "a", "kind": "module"},
                         {"id": "db", "name": "Main DB", "path": "db", "kind": "module"}],
             "edges": [{"from": "a", "to": "db", "kind": "call", "label": label,
                        "evidence": [{"file": "a/x.py", "line": 2, "symbol": "main_db"}]}] * 3}
        d = AV.store_dir(self.repo, C)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "map.json"), "w", encoding="utf-8") as f:
            json.dump(m, f)
        if flows is not None:
            with open(os.path.join(d, "flows.json"), "w", encoding="utf-8") as f:
                json.dump(flows, f)
        spec = importlib.util.spec_from_file_location("arch_verify_cli_q", os.path.join(ROOT, "scripts", "arch_verify.py"))
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(["--repo", self.repo, "--commit", C])
        qp = os.path.join(d, "quality.json")
        if not os.path.exists(qp):
            return rc, buf.getvalue().strip(), None
        with open(qp, encoding="utf-8") as f:
            q = json.load(f)
        return rc, buf.getvalue().strip(), q

    def test_quality_fail_sets_rc(self):
        rc, line, q = self.cli("main db")
        self.assertEqual(rc, 1)
        self.assertTrue(line.startswith("arch_verify: rate 1.00 (3/3)"), line)
        self.assertIn(" · quality FAIL (label-target)", line)
        self.assertEqual((q["v"], q["commit"], checks(q, "fail")), (1, C, ["label-target"]))

    def test_invalid_flows_skipped(self):
        rc, line, q = self.cli("reads rows", {"v": 2})
        self.assertEqual((rc, q["flows"]), (0, "skipped"))
        self.assertIn(" · quality flows skipped", line)

    def test_quality_error_prints_line(self):
        with mock.patch.object(AQ, "check", side_effect=OSError):
            rc, line, q = self.cli("reads rows")
        self.assertEqual((rc, q), (1, None))                      # no traceback; fails closed
        self.assertTrue(line.startswith("arch_verify: rate 1.00 (3/3) · quality error (OSError)"), line)

    def test_clean_map_passes(self):
        rc, line, q = self.cli("reads rows")
        self.assertEqual((rc, q["fail"]), (0, []))
        self.assertNotIn("quality", line)


if __name__ == "__main__":
    unittest.main()
