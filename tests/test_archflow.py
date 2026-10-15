"""arch_flow: flows.json schema, per-step verdicts, gate suffix; flows never change the exit code (tree/show/grep faked, no git)."""
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
AF = sidereus("arch_flow")
C = "c" * 40
FILES = {"app/api.py": ["from lib.db import connect", "def login():", "    return connect()"],
         "lib/db.py": ["def connect():", "    return 1"],
         "shared.py": ["connect = None"]}


def ev(file, line, symbol):
    return {"file": file, "line": line, "symbol": symbol}


def step(evd, f="app", t="lib", **kw):
    return dict({"from": f, "to": t, "label": "calls", "evidence": evd}, **kw)


def flow(steps, fid="login", kind="http"):
    return {"id": fid, "name": "Login", "entry": {"kind": kind, "label": "POST /login"}, "steps": steps}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-archflow-"))
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        self.store = os.path.join(self.tmp, "store")
        self.p = [mock.patch.object(AV, "ARCH_DIR", self.store),
                  mock.patch.object(AV, "_tree", lambda r, c: set(FILES)),
                  mock.patch.object(AV, "_show", lambda r, c, rel: list(FILES.get(rel, []))),
                  mock.patch.object(AV, "_grep", lambda r, c, s: [f for f, ls in FILES.items() if any(s in x for x in ls)])]
        for p in self.p:
            p.start()
        self.m = {"v": 1, "repo": self.repo, "commit": C,
                  "modules": [{"id": "app", "name": "App", "path": "app", "kind": "module"},
                              {"id": "lib", "name": "Lib", "path": "lib", "kind": "module"},
                              {"id": "pg", "name": "PG", "path": "", "kind": "external", "ext": "db"}],
                  "edges": [{"from": "app", "to": "pg", "kind": "call", "label": "", "evidence": [ev("app/api.py", 3, "connect")]}]}

    def tearDown(self):
        for p in self.p:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fl(self, flows, **kw):
        return dict({"v": 1, "repo": self.repo, "commit": C, "flows": flows}, **kw)

    def put(self, flows=None, edge_ok=True):
        d = AV.store_dir(self.repo, C)
        os.makedirs(d, exist_ok=True)
        m = json.loads(json.dumps(self.m))
        if not edge_ok:
            m["edges"][0]["evidence"][0]["symbol"] = "nothere"
        with open(os.path.join(d, "map.json"), "w") as f:
            json.dump(m, f)
        fp = os.path.join(d, "flows.json")
        if flows is None:
            if os.path.exists(fp):
                os.remove(fp)
        else:
            with open(fp, "w") as f:
                json.dump(flows, f)
        return d


class SchemaTest(Base):
    def test_refusals(self):
        ok = flow([step(ev("app/api.py", 3, "connect"))])
        errs, kept, dropped = AF.flow_errors(self.fl([ok]), self.repo, C)
        self.assertEqual((errs, len(kept), dropped), ([], 1, 0))
        self.assertTrue(AF.flow_errors(self.fl([ok] * 41), self.repo, C)[0])           # > FLOW_MAX: whole file
        many = [flow(ok["steps"], "f%d" % i) for i in range(40)]                         # FLOW_MAX distinct ids: all kept
        errs, kept, dropped = AF.flow_errors(self.fl(many), self.repo, C)
        self.assertEqual((errs, len(kept), dropped), ([], 40, 0))
        errs, kept, dropped = AF.flow_errors(self.fl([flow(ok["steps"] * 40, "w")]), self.repo, C)  # STEP_MAX steps: kept
        self.assertEqual((errs, len(kept), dropped), ([], 1, 0))
        self.assertTrue(AF.flow_errors(self.fl([ok], extra="x"), self.repo, C)[0])      # unknown key
        self.assertTrue(AF.flow_errors(self.fl([ok], commit="d" * 40), self.repo, C)[0])
        self.assertTrue(AF.flow_errors(self.fl([ok]), "/elsewhere", C)[0])
        bad = [flow(ok["steps"], "k", kind="rpc"),                                         # bad entry kind
               flow(ok["steps"] * 41, "n"),                                                # > STEP_MAX
               flow([], "e"),                                                              # no step
               dict(ok, id="x", body="src"),                                               # extra flow key
               flow([dict(ok["steps"][0], code="x")], "s"),                                # extra step key
               flow([step(dict(ev("a", 1, "f"), text="x"))], "v"),                         # extra evidence key
               ok]                                                                         # duplicate id
        errs, kept, dropped = AF.flow_errors(self.fl([ok] + bad), self.repo, C)
        self.assertEqual((errs, [x["id"] for x in kept], dropped), ([], ["login"], 7))

    def test_R4_hook_mcp_kinds_pass(self):
        st = [step(ev("app/api.py", 3, "connect"))]
        fl = [flow(st, "h", kind="hook"), flow(st, "m", kind="mcp")]
        errs, kept, dropped = AF.flow_errors(self.fl(fl), self.repo, C)
        self.assertEqual((errs, [x["id"] for x in kept], dropped), ([], ["h", "m"], 0))

    def test_R4_unknown_kind_dropped(self):
        st = [step(ev("app/api.py", 3, "connect"))]
        errs, kept, dropped = AF.flow_errors(self.fl([flow(st, "r", kind="rpc")]), self.repo, C)
        self.assertEqual((errs, kept, dropped), ([], [], 1))


class VerifyTest(Base):
    def test_one_step_per_why(self):
        globs = {"app": ["app/*", "shared.py"], "lib": ["lib/*", "shared.py"]}
        steps = [step(ev("app/api.py", 3, "connect")),            # passes: connect defined in lib
                 step(ev("app/api.py", 3, "connect"), f="zzz"),   # nomod
                 step(ev("lib/db.py", 1, "connect")),             # owner
                 step(ev("shared.py", 1, "connect")),             # overlap
                 step(ev("app/gone.py", 1, "connect")),           # nofile
                 step(ev("app/api.py", 99, "connect")),           # range
                 step(ev("app/api.py", 3, "nothere")),            # nosym
                 step(ev("../x.py", 1, "connect")),               # bad
                 step(ev("app/api.py", 2, "login")),              # nodef: login is not defined in lib
                 step(ev("app/api.py", 2, "login"), t="app"),     # self step skips nodef
                 step(ev("app/api.py", 2, "login"), est=1),       # estimated wiring skips nodef
                 step(ev("app/api.py", 3, "connect"), t="pg")]    # external end skips nodef
        res = AF.verify_flows(self.repo, C, self.m, [flow(steps)], globs)
        self.assertEqual([s["why"] for s in res[0]["steps"]],
                         [None, "nomod", "owner", "overlap", "nofile", "range", "nosym", "bad", "nodef", None, None, None])
        self.assertEqual(len(res[0]["steps"]), len(steps))                                # marked, never removed
        self.assertFalse(res[0]["ok"])
        self.assertTrue(AF.verify_flows(self.repo, C, self.m, [flow(steps[:1])], globs)[0]["ok"])

    def test_java_record_accessor_step(self):
        src = {"lib/Dto.java": ["public record UserDto(", "    String name) {}"],
               "app/Use.java": ["UserDto d = svc.get();", "d.name();"],
               "app/Other.java": ["x.name();"]}
        with mock.patch.dict(FILES, src):
            res = AF.verify_flows(self.repo, C, self.m, [flow([step(ev("app/Use.java", 2, "name")),
                                                               step(ev("app/Other.java", 1, "name"))])], {})
        self.assertEqual([s["why"] for s in res[0]["steps"]], [None, "nodef"])   # record named only in Use.java


class HttpStepTest(Base):
    SRC = {"web/api.js": ["export function get(id) {", "  return http.get('/api/objectchange/' + id)", "}",
                          "fetch('/api/items/' + id)", "fetch('/api/users')"],
           "svc/Ctl.java": ["@RestController", "@RequestMapping(\"/objectchange\")", "public class Ctl {", "",
                            "", "", "    @GetMapping(\"/{id}\")", "    public X get(@PathVariable long id) {",
                            "", "", "    @GetMapping(\"/other\")"],
           "svc/items.py": ["router = APIRouter(prefix=\"/items\")", "", "", "", "@router.get(\"/{id}\")", "def item(id):"],
           "svc/users.js": ["router.get('/users', (req, res) => {", "})"],
           "web/fake.java": ["@GetMapping(\"/{id}\")"]}

    def setUp(self):
        super().setUp()
        self.m["modules"] = [{"id": "web", "name": "Web", "path": "web", "kind": "module"},
                             {"id": "svc", "name": "Svc", "path": "svc", "kind": "module"},
                             {"id": "pg", "name": "PG", "path": "", "kind": "external", "ext": "db"}]
        self.globs = {"web": ["web/*"], "svc": ["svc/*"]}
        self.d = mock.patch.dict(FILES, self.SRC)
        self.d.start()

    def tearDown(self):
        self.d.stop()
        super().tearDown()

    def whys(self, steps):
        res = AF.verify_flows(self.repo, C, self.m, [flow(steps)], self.globs)
        return [s["why"] for s in res[0]["steps"]]

    def hop(self, line, sym, tev=None, t="svc", **kw):
        st = step(ev("web/api.js", line, sym), f="web", t=t, **kw)
        if tev:
            st["to_evidence"] = tev
        return st

    def test_proven_spring_express_fastapi(self):
        steps = [self.hop(2, "/api/objectchange/", ev("svc/Ctl.java", 7, "GetMapping")),
                 self.hop(2, "/api/objectchange/", ev("svc/Ctl.java", 7, "/{id}"), est=1),
                 self.hop(5, "/api/users", ev("svc/users.js", 1, "/users")),
                 self.hop(4, "/api/items/", ev("svc/items.py", 5, "/{id}"))]
        self.assertEqual(self.whys(steps), [None] * 4)

    def test_noroute(self):
        steps = [self.hop(2, "/api/objectchange/"),                                          # no to_evidence
                 self.hop(2, "/api/objectchange/", ev("svc/Ctl.java", 11, "/other")),         # mapping /other
                 self.hop(2, "/api/objectchange/", ev("web/fake.java", 1, "/{id}")),         # to_evidence owned by web
                 self.hop(2, "/api/objectchange/", ev("svc/Ctl.java", 99, "/{id}")),         # line outside the file
                 self.hop(2, "/api/objectchange/", ev("svc/Ctl.java", 2, "GetMapping")),     # symbol not in window
                 self.hop(2, "/api/nothere/", ev("svc/Ctl.java", 7, "/{id}"))]               # FE nosym comes first
        self.assertEqual(self.whys(steps), ["noroute"] * 5 + ["nosym"])

    def test_same_module_and_external_still_pass(self):
        steps = [self.hop(2, "/api/objectchange/", t="web"), self.hop(2, "/api/objectchange/", t="pg")]
        self.assertEqual(self.whys(steps), [None, None])

    def test_be_routes_prefix_and_nonliteral(self):
        express = ["router.get('/users', h)", "", "", "", "class Svc {}"]
        self.assertEqual(AF._be_routes(express, 1), ["/users"])                              # not a class prefix
        spring = ["@RequestMapping(\"/objectchange\")", "public class Ctl {", "", "", "",
                  "  @GetMapping(value = PATH)", "", "", "", "  @GetMapping", "", "", "", "  @GetMapping()"]
        self.assertEqual(AF._be_routes(spring, 6), [])                                       # non-literal: no route
        self.assertEqual(AF._be_routes(spring, 10), ["/objectchange/"])                      # bare annotation
        self.assertEqual(AF._be_routes(spring, 14), ["/objectchange/"])

    def test_route_match(self):
        self.assertTrue(AF.route_match("http://h:8/api/objectchange/", "/objectchange/{id}"))
        self.assertTrue(AF.route_match("/api/users?x=1", "/users"))
        self.assertFalse(AF.route_match("/api/objectchange/", "/{id}"))                      # no literal kept
        self.assertFalse(AF.route_match("/api/objectchange", "/objectchange/{id}"))          # closed tail
        self.assertFalse(AF.route_match("/api/a", "/b"))

    def test_schema_and_load_flows(self):
        good = self.hop(2, "/api/objectchange/", ev("svc/Ctl.java", 7, "/{id}"))
        bad = dict(good, to_evidence={"file": "svc/Ctl.java", "line": 7})
        errs, kept, dropped = AF.flow_errors(self.fl([flow([good]), flow([bad], "b")]), self.repo, C)
        self.assertEqual((errs, [x["id"] for x in kept], dropped), ([], ["login"], 1))
        self.assertEqual(kept[0]["steps"][0]["to_evidence"], good["to_evidence"])
        d = self.put(self.fl([flow([self.hop(2, "/api/objectchange/")])]))
        with open(os.path.join(d, "flows.verify.json"), "w") as f:
            json.dump({"commit": C, "flows": [{"id": "login", "steps": [{"ok": False, "why": "noroute"}]}]}, f)
        out = AF.load_flows(d, self.m, self.repo, C)
        self.assertEqual(out[0]["steps"][0]["why"], "noroute")
        self.assertNotIn("to_evidence", out[0]["steps"][0])


class RunTest(Base):
    def cli(self):
        spec = importlib.util.spec_from_file_location("arch_verify_cli_f", os.path.join(ROOT, "scripts", "arch_verify.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = mod.main(["--repo", self.repo, "--commit", C])
        return rc, buf.getvalue().strip()

    def test_suffix_and_verdict_file(self):
        good, bad = step(ev("app/api.py", 3, "connect")), step(ev("app/api.py", 3, "nothere"))
        d = self.put(self.fl([flow([good, good]), flow([good, bad], "f2"), flow([], "f3")]))
        self.assertEqual(AF.run(self.repo, C), " · flows 1/2 (steps 3/4) · 1 flow(s) dropped")
        with open(os.path.join(d, "flows.verify.json")) as f:
            v = json.load(f)
        self.assertEqual((v["v"], v["commit"], v["total"], v["passed"], v["rate"], v["dropped"]), (1, C, 4, 3, 0.75, 1))
        self.assertEqual(v["flows"][1], {"id": "f2", "ok": False, "steps": [{"ok": True, "why": None}, {"ok": False, "why": "nosym"}]})
        self.put(self.fl([flow([good])], extra=1))
        self.assertEqual(AF.run(self.repo, C), " · flows ignored (invalid)")

    def test_nothing_without_flows(self):
        d = self.put(None)
        self.assertEqual(AF.run(self.repo, C), "")
        self.assertFalse(os.path.exists(os.path.join(d, "flows.verify.json")))
        self.assertEqual(self.cli(), (0, "arch_verify: rate 1.00 (1/1)"))

    def test_exit_code_unchanged(self):
        failing = self.fl([flow([step(ev("app/api.py", 3, "nothere"))] * 3, "f%d" % k) for k in range(8)])
        for edge_ok in (True, False):
            self.put(None, edge_ok)
            rc0, line0 = self.cli()
            self.put(failing, edge_ok)
            rc1, line1 = self.cli()
            self.assertEqual(rc1, rc0)
            self.assertEqual(line1, line0 + " · flows 0/8 (steps 0/24)")
        self.assertEqual(rc0, 1)
        self.m["modules"][0]["kind"] = "bogus"                    # invalid map: no flow suffix at all
        self.put(failing)
        rc, line = self.cli()
        self.assertEqual(rc, 1)
        self.assertNotIn("flows", line)


if __name__ == "__main__":
    unittest.main()
