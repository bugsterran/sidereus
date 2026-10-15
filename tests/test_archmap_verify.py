"""arch_verify: map.json schema, evidence check at the stored commit, rate/gate, verify.json + map.md (temp git repo + temp store)."""
import importlib.util
import io
import shutil as _sh
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests._load import ROOT, sidereus, js_fn
from tests._node import node_e

AV = sidereus("arch_verify")
FIX = os.path.join(ROOT, "tests", "fixtures", "archmap_repo")
# ⚠Setup git must not read the user's global/system config (hooks, signing, templates).
GENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid", GIT_AUTHOR_DATE="2000-01-01T00:00:00Z",
            GIT_COMMITTER_DATE="2000-01-01T00:00:00Z")


def make_repo(tmp):
    repo = os.path.join(tmp, "repo")
    shutil.copytree(FIX, repo)
    for a in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "fixture"]):
        subprocess.run(["git", "-C", repo] + a, check=True, env=GENV, capture_output=True)
    head = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], check=True, env=GENV, capture_output=True,
                          text=True).stdout.strip()
    return os.path.realpath(repo), head


def _read(fp):
    with open(fp, encoding="utf-8") as f:
        return f.read()


def ev(file, line, symbol):
    return {"file": file, "line": line, "symbol": symbol}


def edge(evs, kind="call", f=None, t=None, **kw):
    # Default `from` = the module owning the first cited file (app/ or lib/), so evidence passes the owner check;
    # default `to` = external pg, so the `nodef` check (module->module only) stays out of unrelated tests.
    top = evs[0]["file"].split("/")[0] if evs else ""
    f = f or (top if top in ("app", "lib") else "app")
    t = t or "pg"
    return dict({"from": f, "to": t, "kind": kind, "label": "uses", "evidence": evs}, **kw)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sidereus-arch-")
        cls.repo, cls.commit = make_repo(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="sidereus-arch-store-")
        self.p = mock.patch.object(AV, "ARCH_DIR", self.store)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        shutil.rmtree(self.store, ignore_errors=True)

    def map(self, edges, **kw):
        m = {"v": 1, "repo": self.repo, "commit": self.commit,
             "modules": [{"id": "app", "name": "App", "path": "app", "kind": "module"},
                         {"id": "lib", "name": "Lib", "path": "lib", "kind": "module"},
                         {"id": "pg", "name": "Postgres \"main\" |db|", "path": "", "kind": "external", "ext": "db"},
                         {"id": "cfg", "name": "Config", "path": "config", "kind": "module"}],
             "edges": edges}
        m.update(kw)
        return m

    def put(self, m):
        d = AV.store_dir(self.repo, self.commit)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "map.json"), "w") as f:
            json.dump(m, f)
        return d

    def verdict(self, edges):
        return AV.verify_map(self.repo, self.commit, self.map(edges))


class EvidenceTest(Base):
    def test_symbol_within_k_lines(self):
        # `conn` is on lines 6-7 (`connect` does not count: whole word); cited 4 still passes (±2), 3 does not.
        v = self.verdict([edge([ev("app/main.py", 6, "conn")]), edge([ev("app/main.py", 4, "conn")]),
                          edge([ev("app/main.py", 7, "conn")]), edge([ev("app/main.py", 3, "conn")])])
        self.assertEqual([e["ok"] for e in v["edges"]], [True, True, True, False])
        self.assertEqual(v["edges"][3]["why"], "nosym")

    def test_whole_word_case_sensitive(self):
        v = self.verdict([edge([ev("app/main.py", 6, "conn")]), edge([ev("app/main.py", 6, "Connect")]),
                          edge([ev("app/main.py", 6, "onnect")])])
        self.assertEqual([e["ok"] for e in v["edges"]], [True, False, False])   # `conn` is a word on line 6

    def test_failures(self):
        v = self.verdict([edge([ev("app/nope.py", 1, "x")]), edge([ev("app/main.py", 99, "run")]),
                          edge([ev("../app/main.py", 1, "lib")]), edge([ev("/etc/hosts", 1, "localhost")]),
                          edge([ev("app/../app/main.py", 1, "lib")]), edge([ev("app/main.py", 0, "lib")])])
        self.assertEqual([e["why"] for e in v["edges"]], ["nofile", "range", "bad", "bad", "bad", "range"])

    def test_reads_commit_not_working_tree(self):
        with open(os.path.join(self.repo, "lib", "extra.py"), "w") as f:
            f.write("ghost = 1\n")
        try:
            v = self.verdict([edge([ev("lib/extra.py", 1, "ghost")])])
        finally:
            os.remove(os.path.join(self.repo, "lib", "extra.py"))
        self.assertEqual(v["edges"][0]["why"], "nofile")

    def test_import_last_segment(self):
        # `lib.util.helper` is not on line 7 as a dotted import name, but `helper` is; only kind=import gets this.
        self.assertTrue(self.verdict([edge([ev("app/main.py", 7, "x.y.helper")], kind="import")])["edges"][0]["ok"])
        self.assertFalse(self.verdict([edge([ev("app/main.py", 7, "x.y.helper")], kind="call")])["edges"][0]["ok"])

    def test_any_evidence_passes(self):
        v = self.verdict([edge([ev("nope.py", 1, "x"), ev("lib/db.py", 1, "connect")], f="lib")])
        self.assertEqual((v["passed"], v["total"], v["rate"]), (1, 1, 1.0))

    def test_rate_math(self):
        ok, bad = edge([ev("lib/db.py", 1, "connect")]), edge([ev("lib/db.py", 1, "zzz")])
        v = self.verdict([ok, ok, bad])
        self.assertEqual((v["passed"], v["total"], v["rate"]), (2, 3, 0.6667))
        self.assertEqual(self.verdict([])["rate"], 1.0)


class SymBoundaryTest(unittest.TestCase):
    def _chk(self, line, sym):
        return AV.check_evidence({"file": "a.py", "line": 1, "symbol": sym}, "config", {"a.py"}, lambda rel: [line])

    def test_url_after_word_char(self):
        self.assertEqual(self._chk('URL = "http://127.0.0.1:%d/api/hook" % port', "/api/hook"), "")

    def test_word_symbol_keeps_boundaries(self):
        self.assertEqual(self._chk("def loadTlx(): pass", "loadTl"), "nosym")
        self.assertEqual(self._chk("x = loadTl()", "loadTl"), "")


class OwnerTest(Base):
    def test_evidence_must_be_in_from_module(self):
        v = self.verdict([edge([ev("lib/db.py", 1, "connect")], f="app"),                  # lib's line backing app->lib
                          edge([ev("lib/db.py", 1, "connect"), ev("app/main.py", 6, "conn")], f="app"),
                          edge([ev("app/main.py", 2, "connect")], f="pg", t="app"),       # external from: `to` owns it
                          edge([ev("lib/db.py", 1, "connect")], f="pg", t="app")])
        self.assertEqual([(e["ok"], e["why"]) for e in v["edges"]],
                         [(False, "owner"), (True, None), (True, None), (False, "owner")])

    def test_plan_globs_win_over_path(self):
        m = self.map([edge([ev("lib/db.py", 1, "connect")], f="app")])
        self.assertEqual(AV.verify_map(self.repo, self.commit, m, {"app": ["lib/d*.py"], "lib": ["lib/u*.py"]})["passed"], 1)
        self.assertEqual(AV.verify_map(self.repo, self.commit, m, {"app": ["app/*"]})["passed"], 0)
        plan = {"modules": [{"id": "app", "globs": ["app/*", 3]}, {"id": "x", "globs": "y"}, "z"]}
        self.assertEqual(AV.plan_globs(plan), {"app": ["app/*"]})
        d = self.put(m)
        with open(os.path.join(d, "plan.json"), "w") as f:
            json.dump({"modules": [{"id": "app", "globs": ["lib/d*"]}, {"id": "lib", "globs": ["lib/u*.py"]}]}, f)
        self.assertEqual(AV.run(self.repo, self.commit), (0, "arch_verify: rate 1.00 (1/1)"))

    def test_negative_control_swapped_from(self):
        # Every edge is true as drawn; swapping `from` on k of them must drop exactly those k.
        good = [edge([ev("app/main.py", 6, "conn")]), edge([ev("app/main.py", 2, "connect")], kind="import"),
                edge([ev("lib/db.py", 1, "connect")]), edge([ev("lib/util.py", 1, "helper")]),
                edge([ev("config/app.ini", 2, "db_url")], kind="config", f="cfg", t="lib")]
        self.assertEqual(self.verdict(good)["rate"], 1.0)
        swap = {"app": "lib", "lib": "app", "cfg": "app"}
        for k in (1, 3, 5):
            bad = [dict(e, **{"from": swap[e["from"]], "to": "pg"}) if i < k else e for i, e in enumerate(good)]
            v = self.verdict(bad)
            self.assertEqual(v["passed"], 5 - k)
            self.assertEqual({x["why"] for x in v["edges"][:k]}, {"owner"})


class RunTest(Base):
    def test_outputs_and_est(self):
        d = self.put(self.map([edge([ev("lib/db.py", 1, "connect")], kind="di", t="app"),
                               edge([ev("config/app.ini", 2, "db_url")], kind="config", f="cfg", t="pg", label='a"|b'),
                               edge([ev("app/main.py", 2, "connect")], kind="import", t="lib"),
                               edge([ev("lib/util.py", 1, "nothere")], f="lib", t="pg")]))
        rc, line = AV.run(self.repo, self.commit)
        self.assertEqual((rc, line), (0, "arch_verify: rate 0.75 (3/4)"))
        v = json.loads(_read(os.path.join(d, "verify.json")))
        self.assertEqual(set(v), {"commit", "total", "passed", "rate", "edges", "overlap", "style", "dev"})
        self.assertEqual((v["style"], v["dev"]), (None, []))     # no plan.arch: old behaviour
        self.assertEqual(v["overlap"], {"n": 0, "files": [], "pairs": [], "broad": []})
        md = _read(os.path.join(d, "map.md"))
        self.assertIn('n1 -.->|"uses"| n0', md)         # di: always estimated -> dashed
        self.assertIn('n3 -.->|"a\'\u00a6b"| n2', md)    # config dashed; quote/pipe swapped for look-alikes
        self.assertIn('n0 -->|"uses"| n1', md)
        self.assertNotIn('n1 -->|"uses"| n2', md)       # failed edge dropped
        self.assertIn('n2(["Postgres \'main\' \u00a6db\u00a6"])', md)
        self.assertEqual(AV.est_of({"kind": "call", "est": 1}), 1)
        self.assertEqual(AV.est_of({"kind": "call"}), 0)

    def test_gate_low_rate_and_cli(self):
        self.put(self.map([edge([ev("lib/db.py", 1, "zzz")])]))
        self.assertEqual(AV.run(self.repo, self.commit), (1, "arch_verify: rate 0.00 (0/1)"))
        spec = importlib.util.spec_from_file_location("arch_verify_cli", os.path.join(ROOT, "scripts", "arch_verify.py"))
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        self.assertIs(cli.AV, AV)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli.main(["--last"]), 1)                 # no _last.json
            with open(os.path.join(self.store, "_last.json"), "w") as f:
                json.dump({"repo": self.repo, "commit": self.commit}, f)
            self.assertEqual(cli.main(["--last"]), 1)                 # low rate
            self.put(self.map([edge([ev("lib/db.py", 1, "connect")])]))
            self.assertEqual(cli.main(["--repo", self.repo, "--commit", self.commit]), 0)
            self.assertEqual(cli.main([]), 2)
        self.assertIn("rate 1.00 (1/1)", out.getvalue())

    def test_empty_map(self):
        self.put(self.map([]))
        self.assertEqual(AV.run(self.repo, self.commit), (1, "arch_verify: EMPTY: 4 modules, 0 edges — nothing was checked"))
        self.put(self.map([], modules=self.map([])["modules"][:1]))
        self.assertEqual(AV.run(self.repo, self.commit), (0, "arch_verify: rate 1.00 (0/0)"))   # one-module repo

    def test_schema_error_exit(self):
        self.put(self.map([], extra=1))
        rc, line = AV.run(self.repo, self.commit)
        self.assertEqual(rc, 1)
        self.assertTrue(line.startswith("arch_verify: schema:"))
        self.assertEqual(AV.run(self.repo, "abc")[0], 1)               # not a full id: no store path built
        self.assertFalse(os.path.exists(os.path.join(self.store, AV.repo_key(self.repo), "abc")))


class OverlapDefTest(Base):
    def test_overlap_refuses_shared_file(self):
        m = self.map([edge([ev("lib/db.py", 1, "connect")]), edge([ev("lib/util.py", 1, "helper")])])
        v = AV.verify_map(self.repo, self.commit, m, {"app": ["app/*", "lib/db.py"], "lib": ["lib/*"]})
        self.assertEqual((v["overlap"]["n"], v["overlap"]["files"], v["overlap"]["pairs"]), (1, ["lib/db.py"], [["app", "lib"]]))
        self.assertEqual([(e["ok"], e["why"]) for e in v["edges"]], [(False, "overlap"), (True, None)])
        d = self.put(m)
        with open(os.path.join(d, "plan.json"), "w") as f:
            json.dump({"modules": [{"id": "app", "globs": ["app/*", "lib/db.py"]}, {"id": "lib", "globs": ["lib/*"]}]}, f)
        self.assertEqual(AV.run(self.repo, self.commit), (1, "arch_verify: rate 0.50 (1/2) · overlap 1"))

    def test_broad_glob(self):
        tree = {"app/main.py", "lib/db.py", "config/app.ini"}
        cont, info = AV.contested(tree, self.map([])["modules"], {"app": ["**"]})
        self.assertIn("app", info["broad"])
        self.assertEqual(cont, {"lib/db.py", "config/app.ini"})     # app's own files stay uncontested

    def test_symbol_must_be_defined_in_to(self):
        imp = edge([ev("app/main.py", 2, "connect")], kind="import", t="lib")
        v = self.verdict([imp, dict(imp, to="cfg"), edge([ev("app/main.py", 5, "run")], t="lib"),
                          edge([ev("lib/util.py", 1, "helper")], t="app"),
                          edge([ev("lib/util.py", 1, "helper")], kind="config", t="app"),
                          edge([ev("app/main.py", 1, "lib.util")], kind="import", t="lib")])   # `util` = a lib file stem
        self.assertEqual([(e["ok"], e["why"]) for e in v["edges"]],
                         [(True, None), (False, "nodef"), (False, "nodef"), (False, "nodef"), (True, None), (True, None)])

    def test_route_symbol_is_estimated_not_nodef(self):
        # An HTTP call cites a URL string; no file of `to` defines it, so it must not be dropped as `nodef`.
        call = edge([ev("app/main.py", 5, "/codebook")], t="lib")
        with mock.patch.object(AV, "check_evidence", return_value=""):
            v = self.verdict([call, edge([ev("app/main.py", 5, "run")], t="lib")])
        self.assertEqual([(e["ok"], e["why"]) for e in v["edges"]], [(True, None), (False, "nodef")])
        self.assertEqual([AV.is_route(s) for s in ("/codebook", "http://x/y", "run", "", None)], [True, True, False, False, False])
        self.assertEqual((AV.est_of(call), AV.est_of(edge([ev("a", 1, "/x"), ev("a", 2, "run")]))), (1, 0))

    def test_git_error_is_not_defined(self):
        with mock.patch.object(AV, "_git_run_capped", side_effect=OSError):
            self.assertFalse(AV.defined_in("connect", {}, {"lib/db.py"}, lambda f: ["def connect():"],
                                           lambda s: AV._grep(self.repo, self.commit, s)))
        self.assertTrue(AV.defined_in("a.connect", {}, {"lib/db.py"}, lambda f: ["def connect():"], lambda s: ["lib/db.py"]))

    def test_class_attr_alias_and_file_name(self):
        src = {"lib/r.py": ["class R:", "    \"\"\"", "    FOO = 1", "    \"\"\"", "    D = {", "    BAR: 1,", "    }",
                            "    ROUTES = {", "    }", "    N: int", "    def go(self):", "        LOCAL = 1"],
               "lib/bad.py": ["class R:", "    ROUTES = (", ""],
               "lib/t.js": ["class R {", "  ROUTES = 1", "}"],
               "app/x.py": ["from lib.p import (a, save as p_save,", ")", "from .q import put as q_put",
                            "import other.m as o_m", "with open('f') as w_sym:", "    pass", "# from lib.p import z as c_sym",
                            "s = 'from lib.p import z as s_sym'"]}
        rd = lambda f: src.get(f, [])
        di = lambda s, files: AV.defined_in(s, {}, files, rd, lambda q: sorted(files))
        self.assertEqual([di(s, {"lib/r.py"}) for s in ("ROUTES", "N", "go", "LOCAL", "FOO", "BAR", "MISSING")],
                         [True, True, True, False, False, False, False])   # function local, docstring, dict key
        self.assertFalse(di("ROUTES", {"lib/bad.py"}))        # does not parse
        self.assertFalse(di("ROUTES", {"lib/t.js"}))          # Python only
        self.assertTrue(di("index.html", {"web/index.html"}))
        self.assertTrue(di("web/index.html", {"web/index.html"}))
        self.assertFalse(di("main.html", {"web/index.html"}))  # a file name not in `to`
        defs, lib = {"save", "put"}, {"lib/p.py", "app/q.py"}
        doa = lambda s, files=lib: AV.defined_or_alias(s, "app/x.py", rd, lambda y: y in defs, lambda: files)
        self.assertEqual([doa(s) for s in ("p_save", "q_put", "w_sym", "c_sym", "s_sym", "o_m", "other")],
                         [True, True, False, False, False, False, False])
        self.assertFalse(doa("p_save", {"lib/z.py"}))          # alias whose module is not in `to`
        defs.clear()
        self.assertFalse(doa("p_save"))                        # alias to a missing name

    def test_java_record_and_lombok(self):
        src = {"api/Dto.java": ["package a;", "public record UserDto(", "    @NotNull String name,",
                                "    Map<String, List<Long>> ids, int size) implements X {}"],
               "api/Ent.java": ["@Getter", "@Builder", "public class Ent {", "    private String title;",
                                "    private boolean active = false;", "}"],
               "api/Bare.java": ["public class Bare {", "    private String note;", "}"],
               "api/Fld.java": ["public class Fld {", "    @Setter", "    private String memo;", "}"],
               "api/Off.java": ["@Data", "public class Off {", "    @Getter(AccessLevel.NONE)", "    private String key;",
                                "    private Long id;", "}"],
               "app/Use.java": ["UserDto d = svc.get();", "d.name(); d.ids(); list.size();", "Ent e; Bare b; Fld f; Off o;"],
               "app/Other.java": ["list.size(); x.name();"]}
        rd = lambda f: src.get(f, [])
        gr = lambda q: [f for f, ls in sorted(src.items()) if AV._word_re(q).search("\n".join(ls))]
        di = lambda s, files, ev="app/Use.java": AV.defined_in(s, {}, set(files), rd, gr, rd(ev) if ev else None)
        dto = ["api/Dto.java"]
        self.assertEqual([di(s, dto) for s in ("name", "ids", "size", "String")], [True, True, True, False])
        self.assertEqual([di("name", dto, "app/Other.java"), di("name", dto, None)], [False, False])  # type not named
        ent = ["api/Ent.java", "api/Bare.java", "api/Fld.java"]
        self.assertEqual([di(s, ent) for s in ("getTitle", "isActive", "builder", "setTitle", "getNote",
                                                "setMemo", "getMemo", "size", "toString")],
                         [True, True, True, False, False, True, False, False, False])
        self.assertFalse(di("builder", ["api/Bare.java"]))
        self.assertEqual([di(s, ent, "app/Other.java") for s in ("getTitle", "builder")], [False, False])  # class not named
        self.assertEqual([di(s, ["api/Off.java"]) for s in ("getKey", "setKey", "getId")], [False, True, True])
        self.assertFalse(di("getId", ["api/Off.java"], "app/Other.java"))   # @Data class not named by the caller

    def test_def_regex(self):
        hit = ["def connect(x):", "export async function connect() {", "public static int connect(String a) throws E {",
               "connect = 1", "connect: int", "const connect = () => 1"]
        miss = ["    return connect(x)", "if (connect(x)) {", "x = connect()", "connect == 1", "conn = connect"]
        rx = AV._def_re("connect")
        self.assertEqual([bool(rx.search(x)) for x in hit], [True] * len(hit))
        self.assertEqual([bool(rx.search(x)) for x in miss], [False] * len(miss))

    def test_def_regex_object_method(self):
        hit = ["  post: <T>(url: string, body?: object) =>", "  post(url) {", "  post: async (x) =>",
               "  post: function (x) {", "post: (x) => x"]
        miss = ["  post: string", "  post: vi.fn()", "  post: client.post", "  x: post(a)"]
        rx = AV._def_re("post")
        self.assertEqual([bool(rx.search(x)) for x in hit], [True] * len(hit))
        self.assertEqual([bool(rx.search(x)) for x in miss], [False] * len(miss))

    def test_def_regex_abstract_decl(self):
        hit = ['    List<String> getX(@Param("empNo") String empNo);', "  public abstract int getX();",
               "  Map<String, Object> getX(int a) throws IOException;", "Task<int> getX(int a);"]
        miss = ["    return getX(a);", "    List<String> x = getX(a);", "  getX(a);", "  new getX(a);",
                "  throw getX(a);", "  await getX(a);", "  yield getX(a);", "  else getX(a);", "  case getX(a);",
                "  x.y = getX(a);"]
        rx = AV._def_re("getX")
        self.assertEqual([bool(rx.search(x)) for x in hit], [True] * len(hit))
        self.assertEqual([bool(rx.search(x)) for x in miss], [False] * len(miss))


class MermaidTest(Base):
    NAME = "O'Neil & [core] @x #quot; <b>`t`"

    def md(self):
        m = self.map([edge([ev("lib/db.py", 1, "connect")], label=self.NAME)])
        m["modules"][0]["name"] = self.NAME
        return AV.render_md(m, AV.verify_map(self.repo, self.commit, m))

    def test_no_entities(self):
        md = self.md()
        self.assertNotRegex(md, r"#\d+;")
        self.assertIn("O'Neil \uff06 [core] @x \uff03quot; \u2039b\u203a't'", md)

    @unittest.skipUnless(_sh.which("node"), "node not installed")
    def test_page_renderer_reads_labels(self):
        # The page's own flowchart parser (81e) must show the label text as written in map.md, nothing decoded or dropped.
        body = self.md().split("\n", 1)[1].rsplit("```", 1)[0]
        src = "\n".join(js_fn(n) for n in ("mmdLabel", "mmdSplit", "mmdChain", "mmdParse")) + \
            "\nconst g = mmdParse(%s); console.log(JSON.stringify([g.nodes.n0.label, g.edges[0].label]));" % json.dumps(body)
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        want = AV.mm_text(self.NAME)
        self.assertEqual(json.loads(r.stdout), [want, want])


class StyleTest(Base):
    ARCH = {"style": "layered", "framework": "Spring", "units": "layer packages", "evidence": ["app/main.py", "./lib/db.py"]}

    def test_plan_arch(self):
        self.assertEqual(AV.plan_arch({"arch": self.ARCH})["evidence"], ["app/main.py", "lib/db.py"])
        self.assertEqual(AV.plan_arch({"arch": {"style": "crates", "evidence": ["Cargo.toml"]}})["framework"], "")
        for bad in (dict(self.ARCH, style="spaghetti"), dict(self.ARCH, evidence=["../etc/passwd"]),
                    dict(self.ARCH, evidence=["/abs"]), dict(self.ARCH, evidence=["a"] * 6), dict(self.ARCH, evidence=[]),
                    dict(self.ARCH, note="x"), dict(self.ARCH, units="a\nb"), "layered"):
            self.assertIsNone(AV.plan_arch({"arch": bad}), bad)
        self.assertIsNone(AV.plan_arch({}))
        self.assertIsNone(AV.plan_arch(None))

    def test_plan_arch_long_text_is_cut_not_refused(self):
        a = AV.plan_arch({"arch": dict(self.ARCH, framework="x" * 41, units="u" * 124)})
        self.assertEqual((len(a["framework"]), a["framework"][-1]), (AV.FW_MAX, "\u2026"))
        self.assertEqual((len(a["units"]), a["style"]), (AV.UNITS_MAX, "layered"))

    def test_check_style(self):
        a = AV.plan_arch({"arch": self.ARCH})
        st = AV.check_style(a, {"app/main.py", "lib/db.py"})
        self.assertTrue(st["ok"])
        st = AV.check_style(a, {"app/main.py"})
        self.assertEqual((st["ok"], [x["ok"] for x in st["evidence"]]), (False, [True, False]))
        self.assertIsNone(AV.check_style(None, set()))

    def rmap(self, roles, edges):
        mods = [{"id": k, "name": k, "path": k, "kind": "module", "role": r} if r else
                {"id": k, "name": k, "path": k, "kind": "module"} for k, r in roles]
        return self.map(edges, modules=mods)

    def test_deviations(self):
        roles = [("w", "web"), ("s", "service"), ("d", "data"), ("u", "shared"), ("n", None)]
        es = [edge([ev("w/a", 1, "x")], f="w", t="d"),                   # web -> data: outside layered
              edge([ev("w/a", 1, "x")], f="w", t="s"),                   # allowed
              edge([ev("w/a", 1, "x")], f="w", t="u"),                   # -> shared always allowed
              edge([ev("w/a", 1, "x")], f="w", t="n"),                   # missing role: not judged
              edge([ev("w/a", 1, "x")], f="w", t="d", est=1),            # estimated: not judged
              edge([ev("w/a", 1, "x")], f="w", t="d", kind="di"),        # di: not judged
              edge([ev("w/a", 1, "x")], f="w", t="d"),                   # failed verification below
              edge([ev("d/a", 1, "x")], f="d", t="d")]                   # same role (self)
        m = self.rmap(roles, es)
        self.assertEqual(AV.schema_errors(m, self.repo, self.commit), [])
        v = {"edges": [{"i": i, "ok": i != 6} for i in range(len(es))]}
        self.assertEqual(AV.deviations(m, v, "layered"), [{"i": 0, "a": "web", "b": "data"}])
        self.assertEqual(AV.deviations(m, v, "modular"), [])            # no flow table
        self.assertEqual(AV.deviations(m, v, None), [])
        self.assertTrue(AV.schema_errors(self.rmap([("w", "boss")], []), self.repo, self.commit))

    def test_deviations_roles_outside_style(self):
        def dev(roles, f, t, style):
            m = self.rmap(roles, [edge([ev("x/a", 1, "x")], f=f, t=t)])
            return AV.deviations(m, {"edges": [{"i": 0, "ok": True}]}, style)
        lay = [("w", "web"), ("a", "adapter"), ("u", "shared")]
        self.assertEqual(dev(lay, "w", "a", "layered"), [])              # adapter is not a layered role: not judged
        self.assertEqual(dev(lay, "a", "w", "layered"), [])
        self.assertEqual(dev(lay, "u", "w", "layered"), [{"i": 0, "a": "shared", "b": "web"}])   # shared -> web flagged
        hx = [("a", "adapter"), ("p", "app")]
        self.assertEqual(dev(hx, "a", "p", "hexagonal"), [])              # driving adapter -> use case
        self.assertEqual(dev(hx, "p", "a", "hexagonal"), [{"i": 0, "a": "app", "b": "adapter"}])
        mv = [("v", "view"), ("m", "model")]
        self.assertEqual(dev(mv, "v", "m", "mvvm"), [])                   # view binds to model types
        self.assertEqual(dev(mv, "m", "v", "mvvm"), [{"i": 0, "a": "model", "b": "view"}])

    def test_run_writes_style_gate_unaffected(self):
        d = self.put(self.map([edge([ev("lib/db.py", 1, "connect")])]))
        with open(os.path.join(d, "plan.json"), "w") as f:
            json.dump({"arch": dict(self.ARCH, evidence=["app/main.py", "nope.txt"])}, f)
        self.assertEqual(AV.run(self.repo, self.commit), (0, "arch_verify: rate 1.00 (1/1)"))
        v = json.loads(_read(os.path.join(d, "verify.json")))
        self.assertEqual((v["style"]["ok"], v["style"]["evidence"][1], v["dev"]), (False, {"file": "nope.txt", "ok": False}, []))
        self.put(self.map([edge([ev("lib/db.py", 1, "zzz")])]))
        self.assertEqual(AV.run(self.repo, self.commit)[0], 1)          # style present: low rate still fails the same way
        with open(os.path.join(d, "plan.json"), "w") as f:
            json.dump({"arch": {"style": "bogus"}}, f)
        self.put(self.map([edge([ev("lib/db.py", 1, "connect")])]))
        self.assertEqual(AV.run(self.repo, self.commit)[0], 0)          # invalid arch never fails the gate
        self.assertIsNone(json.loads(_read(os.path.join(d, "verify.json")))["style"])


class SchemaTest(Base):
    def errs(self, m):
        return AV.schema_errors(m, self.repo, self.commit)

    def test_valid(self):
        self.assertEqual(self.errs(self.map([edge([ev("a", 1, "b")], est=1)])), [])

    def test_rejects(self):
        e1 = edge([ev("a", 1, "b")])
        bad = [
            self.map([], secret="x"),                                           # unknown top key
            self.map([dict(e1, body="x")]),                                     # unknown edge key
            self.map([edge([dict(ev("a", 1, "b"), text="x")])]),                # unknown evidence key
            self.map([edge([])]),                                               # no evidence
            self.map([edge([ev("a", 1, "b")] * 6)]),                            # > 5 evidence
            self.map([edge([ev("a", 1, "b")], kind="uses")]),
            self.map([edge([ev("a", 1, "b")], t="ghost")]),
            self.map([edge([ev("a", True, "b")])]),
            self.map([edge([ev("a", 1, " b")])]),
            self.map([dict(e1, label="x" * 61)]),
            self.map([dict(e1, est=2)]),
            self.map([], modules=[]),
            self.map([], modules=[{"id": "a b", "name": "x", "path": "", "kind": "module"}]),
            self.map([], modules=[{"id": "a", "name": "x" * 61, "path": "", "kind": "module"}]),
            self.map([], modules=[{"id": "a", "name": "x", "path": "", "kind": "module", "ext": "smtp"}]),
            self.map([], modules=[{"id": "a", "name": "x", "path": "", "kind": "lib"}]),
            self.map([], modules=[{"id": "a", "name": "x", "path": "", "kind": "module"}] * 2),
            self.map([], v=2),
            self.map([], commit="0" * 40),
            self.map([], repo="/elsewhere"),
            [],
        ]
        for i, m in enumerate(bad):
            self.assertTrue(self.errs(m), "case %d accepted" % i)


if __name__ == "__main__":
    unittest.main()
