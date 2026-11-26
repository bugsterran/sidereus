"""sidereus/state_v1 — public sidereus-state v1 projection, its stdlib validator and GET /api/v1/state.
No live files, clock or network: every source is monkeypatched on sidereus.state_v1."""
import copy
import json
import os
import shutil
import tempfile
import unittest

from tests._load import ROOT, sidereus, load

sv = sidereus("state_v1")
rg = sidereus("routes_get")

CANARY = "CANARY-BODY-7f3e please never leak"
ROW = {"id": "demo0001", "sid": "demo0001-session", "project": "shop", "cwd": "/Users/demo/shop", "branch": "main",
       "tool": "Agent", "targ": CANARY, "blocked": CANARY, "messages": [CANARY], "kind": "", "ageSec": 7,
       "ctx": 1000, "model": "opus", "win": 200000, "state": "tool", "plat": "cc", "cost": 3.2,
       "plm": {"name": "release", "title": "build", "age": 12},
       "sub": [{"lab": "Explore: map it", "min": 2, "tid": "toolu_x", "idle": 4, "aid": "a1", "now": "Read"}],
       "bgs": [{"lab": CANARY, "min": 1}]}
QUOTA = {"at": 1, "age": 0, "err": None, "src": "api",
         "five_hour": {"pct": 42, "resets_at": "2026-10-05T12:00:00Z", "leftSec": 3600},
         "seven_day": {"pct": 17.5, "resets_at": "2026-10-09T00:00:00Z", "leftSec": 400000},
         "plan": {"tier": "t1", "seat": "s1", "org": "org-secret"}, "extra": {"seat": "x"}}
ROOMS = {"release": {"created": 5, "owner": "lead", "members": ["lead"], "topic": "Release", "invited": [],
                     "cursors": {"lead": 1}}}
FORBIDDEN = ("targ", "blocked", "messages", "acks", "cursors", "cards", "usage")


class StateV1(unittest.TestCase):
    def setUp(self):
        self.patch("sessions_cached", lambda **kw: ([copy.deepcopy(ROW)], True))
        self.patch("quota", lambda: copy.deepcopy(QUOTA))
        self.patch("_saver_state", lambda pct, left=None: {"on": True, "why": "quota", "pct": pct, "stage": 1})
        self.patch("_load", lambda name, default: copy.deepcopy(ROOMS) if name == "rooms.json" else default)
        self.patch("state_off", lambda: set())
        self.patch("_now", lambda: 1790000000.0)
        self.schema = sv.load_schema()

    def patch(self, name, val):
        old = getattr(sv, name)
        setattr(sv, name, val)
        self.addCleanup(setattr, sv, name, old)

    def test_build_validates(self):
        obj = sv.build(max_age=0)
        self.assertEqual(sv.validate(obj, self.schema), [])
        self.assertEqual((obj["schema"], obj["version"], obj["at"]), ("sidereus-state", 1, 1790000000))
        self.assertEqual(obj["sessions"][0]["sub"][0]["lab"], "Explore: map it")
        self.assertEqual(obj["quota"]["plan"], {"tier": "t1", "seat": "s1"})
        self.assertEqual(obj["saver"], {"on": True, "pct": 42, "stage": 1})

    def test_forbidden_keys_absent(self):
        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    self.assertNotIn(k, FORBIDDEN)
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        obj = sv.build(max_age=0)
        walk(obj)
        self.assertNotIn("bgs", obj["sessions"][0])

    def test_canary_never_leaks(self):
        self.assertNotIn("CANARY", json.dumps(sv.build(max_age=0), ensure_ascii=False))

    def test_feature_off_drops_block(self):
        self.patch("state_off", lambda: {"rooms", "sessions"})
        obj = sv.build(max_age=0)
        self.assertNotIn("rooms", obj)
        self.assertNotIn("sessions", obj)
        self.assertIn("quota", obj)
        self.assertEqual(sv.validate(obj, self.schema), [])

    def test_no_quota_is_null(self):
        self.patch("quota", lambda: {"err": "boom"})
        obj = sv.build(max_age=0)
        self.assertIsNone(obj["quota"])
        self.assertEqual(sv.validate(obj, self.schema), [])

    def test_cache(self):
        a = sv.build(max_age=0)
        self.assertIs(sv.build(), a)

    def test_examples_validate(self):
        for n in ("state.v1.min.json", "state.v1.full.json"):
            with open(os.path.join(ROOT, "docs", "schema", "examples", n), encoding="utf-8") as f:
                self.assertEqual(sv.validate(json.load(f), self.schema), [], n)

    def test_validate_catches(self):
        good = sv.build(max_age=0)
        bad = copy.deepcopy(good)
        bad["at"] = "now"
        self.assertTrue(any("$.at" in e for e in sv.validate(bad, self.schema)))
        bad = copy.deepcopy(good)
        del bad["version"]
        self.assertTrue(any("version" in e for e in sv.validate(bad, self.schema)))
        bad = copy.deepcopy(good)
        bad["messages"] = []
        self.assertTrue(any("messages" in e for e in sv.validate(bad, self.schema)))
        bad = copy.deepcopy(good)
        bad["sessions"][0]["sub"][0]["lab"] = "x" * 201
        self.assertTrue(sv.validate(bad, self.schema))
        bad = copy.deepcopy(good)
        bad["version"] = True
        self.assertTrue(sv.validate(bad, self.schema))

    def test_route(self):
        cs = load()
        self.assertIs(cs.Handler._GET_ROUTES["/api/v1/state"], rg._GetRoutes._g_state_v1)
        self.assertIs(cs.Handler._GET_ROUTES["/api/state"], rg._GetRoutes._g_state)
        sv.build(max_age=0)   # warm the cache with the patched sources (the route uses the default TTL)
        sent = {}
        fake = _FakeHandler()
        fake._raw_json = lambda code, out, cache=True: sent.update(code=code, out=out)
        rg._GetRoutes._g_state_v1(fake, None)
        self.assertEqual(sent["code"], 200)
        self.assertEqual(sent["out"]["version"], 1)


class _FakeHandler(object):
    pass


RUN_KEYS = {"name", "rid", "t0", "end", "cur", "verdict", "stages"}


def _st(o, t1):
    return {"o": o, "n": 1, "t0": t1 - 10, "t1": t1, "from": {CANARY: 1},
            "ag": [{"aid": "a1", "tid": "t1", "lab": "Explore: " + CANARY, "run": False, "t0": 1, "t1": 2}]}


def _plrun(proj=""):
    """Head run (open) + past: one archived before `stop` was kept (null), one stopped, one duplicate of the head."""
    return [{"name": "change", "proj": proj, "sid": CANARY, "rid": 3000.0, "lab": CANARY, "cur": "build",
             "end": 0.0, "t0": 3000.0, "t1": 3100.0, "stop": 0.0, "cm": [CANARY], "via": CANARY, "why": CANARY,
             "stages": {"plan": _st("done", 3050), "build": _st("run", 3100)},
             "past": [{"rid": 1000.0, "t0": 1000.0, "t1": 1200.0, "end": 1150.0, "cur": "verify", "stop": None, "lab": CANARY,
                       "stages": {"plan": _st("done", 1050), "build": _st("done", 1100), "verify": _st("done", 1150)}},
                      {"rid": 2000.0, "t0": 2000.0, "t1": 2200.0, "end": 2150.0, "cur": "verify", "stop": 2150.0, "lab": CANARY,
                       "stages": {"plan": _st("done", 2050), "verify": _st("done", 2150)}},
                      {"rid": 3000.0, "t0": 3000.0, "t1": 3100.0, "end": 0.0, "cur": "build", "stop": 0.0, "stages": {}}]}]


def _write_def(d, name, body):
    pd = os.path.join(d, ".claude", "pipelines")
    os.makedirs(pd, exist_ok=True)
    fp = os.path.join(pd, name + ".json")
    with open(fp, "w", encoding="utf-8") as f:
        f.write(body if isinstance(body, str) else json.dumps(body))
    return fp


DEF = {"v": 1, "name": "change", "title": "change", "defaults": {"model": "inherit", "retry": 0},
       "stages": [{"title": "plan", "agent": "Plan", "task": "Plan it."}, {"title": "build", "agent": "general-purpose", "task": "Build it."},
                  {"title": "verify", "agent": "general-purpose", "task": "Verify it."}]}


def _bad_defs():
    """Definitions pipeline_schema.validate rejects on the subset state_v1._def_ok mirrors."""
    st = DEF["stages"]
    out = []
    for k, v in (("v", None), ("v", 2), ("name", "other"), ("title", ""), ("title", "a\nb"), ("defaults", None),
                 ("defaults", {"model": "gpt", "retry": 0}), ("defaults", {"model": "opus", "retry": 4}),
                 ("defaults", {"model": "opus", "retry": 0, "effort": "huge"}), ("stages", []), ("stages", st * 7),
                 ("stages", st[:1] + st[:1]), ("stages", [dict(st[0], title="")]), ("stages", [dict(st[0], title="x" * 41)]),
                 ("stages", [dict(st[0], title="\ufeff")]), ("stages", [dict(st[0], agent="")]), ("stages", ["plan"])):
        d = copy.deepcopy(DEF)
        if v is None:
            d.pop(k)
        else:
            d[k] = v
        out.append(d)
    return out


class StateV1Runs(unittest.TestCase):
    """Session `runs` (R1 R3 R4): definitions live in tempdirs; _def_dirs and V1_DEFS are patched."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(self.proj)
        bi = [os.path.join(self.tmp, "code"), os.path.join(self.tmp, "data")]
        for d in bi:
            os.makedirs(d)
        self.patch("_def_dirs", lambda: tuple(bi))
        self.patch("V1_DEFS", sv.BoundedMemo(64))
        self.patch("quota", lambda: copy.deepcopy(QUOTA))
        self.patch("_saver_state", lambda pct, left=None: {"on": False, "pct": pct, "stage": 0})
        self.patch("_load", lambda name, default: default)
        self.patch("state_off", lambda: set())
        self.patch("_now", lambda: 1790000000.0)
        self.schema = sv.load_schema()

    def patch(self, name, val):
        old = getattr(sv, name)
        setattr(sv, name, val)
        self.addCleanup(setattr, sv, name, old)

    def rows(self, *rows):
        self.patch("sessions_cached", lambda **kw: ([copy.deepcopy(r) for r in rows], True))

    def session(self, **kw):
        r = copy.deepcopy(ROW)
        r.update(cwd=self.proj, **kw)
        return r

    def build(self):
        return sv.build(max_age=0)

    def test_runs_projection(self):
        _write_def(self.proj, "change", DEF)
        self.rows(self.session(plrun=_plrun()))
        obj = self.build()
        self.assertEqual(sv.validate(obj, self.schema), [])
        runs = obj["sessions"][0]["runs"]
        self.assertEqual([r["rid"] for r in runs], [3000.0, 2000.0, 1000.0])   # newest first, head duplicate dropped
        for r in runs:
            self.assertEqual(set(r), RUN_KEYS)
        self.assertEqual([r["verdict"] for r in runs], ["unknown", "unknown", "unknown"])
        self.assertIsNone(runs[0]["end"])
        self.assertEqual(runs[1]["end"], 2150.0)
        self.assertEqual(runs[1]["stages"], {"plan": "done", "verify": "done"})
        self.assertNotIn("CANARY", json.dumps(obj, ensure_ascii=False))
        self.assertEqual(obj["version"], 1)

    def test_pass_and_fail(self):
        _write_def(self.proj, "change", DEF)
        pl = _plrun()
        pl[0]["past"][0]["stop"] = 0.0   # stop known, not stopped, last stage done -> pass
        pl[0]["stages"]["build"] = _st("fail", 3100)
        self.rows(self.session(plrun=pl))
        runs = self.build()["sessions"][0]["runs"]
        self.assertEqual({r["rid"]: r["verdict"] for r in runs}, {3000.0: "fail", 2000.0: "unknown", 1000.0: "pass"})

    def test_no_runs_no_key(self):
        for pl in (None, [], [{"name": ""}], ["x"]):
            r = self.session()
            if pl is not None:
                r["plrun"] = pl
            self.rows(r)
            obj = self.build()
            self.assertNotIn("runs", obj["sessions"][0], pl)
            self.assertEqual(obj["version"], 1)
            self.assertEqual(sv.validate(obj, self.schema), [])

    def test_definition_from_repos(self):
        other = os.path.join(self.tmp, "other")
        os.makedirs(other)
        _write_def(other, "change", DEF)
        pl = _plrun()
        pl[0]["past"][0]["stop"] = 0.0
        self.rows(self.session(plrun=pl, repos=[other]))
        runs = self.build()["sessions"][0]["runs"]
        self.assertEqual(runs[-1]["verdict"], "pass")

    def test_builtin_dir_only_when_builtin(self):
        pl = _plrun()
        pl[0]["past"][0]["stop"] = 0.0
        code = sv._def_dirs()[0]
        _write_def(code, "change", DEF)   # not builtin -> ignored
        self.rows(self.session(plrun=pl))
        self.assertEqual(self.build()["sessions"][0]["runs"][-1]["verdict"], "unknown")
        _write_def(code, "change", dict(DEF, builtin=True))
        self.assertEqual(self.build()["sessions"][0]["runs"][-1]["verdict"], "pass")

    def test_invalid_builtin_owner_is_unknown(self):
        other = os.path.join(self.tmp, "other")
        os.makedirs(other)
        _write_def(other, "change", DEF)
        _write_def(sv._def_dirs()[0], "change", dict(DEF, builtin=True, v=2))   # the builtin owner decides, like pipeline.borrowed
        pl = _plrun()
        pl[0]["past"][0]["stop"] = 0.0
        self.rows(self.session(plrun=pl, repos=[other]))
        self.assertEqual(self.build()["sessions"][0]["runs"][-1]["verdict"], "unknown")

    def test_code_dir_builtin_run_is_unknown(self):
        code = sv._def_dirs()[0]
        _write_def(code, "change", dict(DEF, builtin=True))   # hidden from CODE_DIR's own list (pipeline._listed), never borrowed
        pl = _plrun(proj=code)
        pl[0]["past"][0]["stop"] = 0.0
        self.rows(self.session(plrun=pl))
        self.assertEqual(self.build()["sessions"][0]["runs"][-1]["verdict"], "unknown")
        _write_def(self.proj, "change", dict(DEF, builtin=True))   # builtin outside CODE_DIR is listed there
        pl = _plrun(proj=self.proj)
        pl[0]["past"][0]["stop"] = 0.0
        self.rows(self.session(plrun=pl))
        self.assertEqual(self.build()["sessions"][0]["runs"][-1]["verdict"], "pass")

    def test_def_ok_never_more_lenient_than_schema(self):
        ps = sidereus("pipeline_schema")
        self.assertEqual((sv.V1_MODELS, sv.V1_EFFORTS, sv.V1_RENAMED, sv._V1_WS, sv._V1_AGENT.pattern),
                         (ps.MODELS, ps.EFFORTS, ps.RENAMED, ps._JS_WS, ps._AGENT.pattern))
        self.assertEqual(ps.validate(DEF, "change"), [])
        self.assertTrue(sv._def_ok(DEF, "change"))
        for d in _bad_defs():
            self.assertTrue(ps.validate(d, "change"), d)
            self.assertFalse(sv._def_ok(d, "change"), d)

    def test_invalid_definition_is_unknown(self):
        other = os.path.join(self.tmp, "other")
        os.makedirs(other)
        _write_def(other, "change", DEF)
        pl = _plrun()
        pl[0]["past"][0]["stop"] = 0.0
        bodies = ["{not json", {"stages": []}, {"stages": [{"title": ""}]}, " " * (sv.V1_DEF_MAX + 1),
                  dict(DEF, v=None), dict(DEF, name="other")] + _bad_defs()
        for body in bodies:
            _write_def(self.proj, "change", body)   # proj file exists -> it decides, never falls back to repos
            self.rows(self.session(plrun=pl, repos=[other]))
            self.assertEqual(self.build()["sessions"][0]["runs"][-1]["verdict"], "unknown", str(body)[:20])

    def test_symlinked_pipelines_dir_leaving_project(self):
        out = os.path.join(self.tmp, "outside")
        _write_def(out, "change", DEF)
        os.makedirs(os.path.join(self.proj, ".claude"))
        os.symlink(os.path.join(out, ".claude", "pipelines"), os.path.join(self.proj, ".claude", "pipelines"))
        pl = _plrun()
        pl[0]["past"][0]["stop"] = 0.0
        self.rows(self.session(plrun=pl))
        self.assertEqual(self.build()["sessions"][0]["runs"][-1]["verdict"], "unknown")

    def test_symlinked_repo_root_resolves(self):
        _write_def(self.proj, "change", DEF)
        link = os.path.join(self.tmp, "link")
        os.symlink(self.proj, link)
        pl = _plrun()
        pl[0]["past"][0]["stop"] = 0.0
        self.rows(dict(self.session(plrun=pl), cwd=link))
        self.assertEqual(self.build()["sessions"][0]["runs"][-1]["verdict"], "pass")

    def test_definition_cache(self):
        fp = _write_def(self.proj, "change", DEF)
        os.utime(fp, ns=(1000000000, 1000000000))
        reads = []
        real = sv._read_def_bytes
        self.patch("_read_def_bytes", lambda p: reads.append(p) or real(p))
        pl = _plrun()
        pl[0]["past"][0]["stop"] = 0.0
        self.rows(self.session(plrun=pl))
        self.build()
        self.build()
        self.assertEqual(len(reads), 1)   # unchanged mtime/size: no reread
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(dict(DEF, stages=DEF["stages"] + [{"title": "ship", "agent": "general-purpose", "task": "Ship it."}]), f)
        os.utime(fp, ns=(2000000000, 2000000000))
        self.assertEqual(self.build()["sessions"][0]["runs"][-1]["verdict"], "unknown")   # last stage is now «ship»
        self.assertEqual(len(reads), 2)

    def test_canary_in_full_row(self):
        _write_def(self.proj, "change", DEF)
        self.rows(self.session(plrun=_plrun(proj=self.proj)))
        obj = self.build()
        self.assertNotIn("CANARY", json.dumps(obj, ensure_ascii=False))
        self.assertNotIn(self.proj, json.dumps(obj["sessions"][0]["runs"]))   # run proj / sid stay out

    def test_full_example_has_runs(self):
        with open(os.path.join(ROOT, "docs", "schema", "examples", "state.v1.full.json"), encoding="utf-8") as f:
            ex = json.load(f)
        self.assertTrue(ex["sessions"][0]["runs"])
        self.assertEqual(sv.validate(ex, self.schema), [])
        bad = copy.deepcopy(ex)
        bad["sessions"][0]["runs"][0]["lab"] = "x"
        self.assertTrue(any("lab" in e for e in sv.validate(bad, self.schema)))
        bad = copy.deepcopy(ex)
        bad["sessions"][0]["runs"][0]["verdict"] = "ok"
        self.assertTrue(sv.validate(bad, self.schema))


if __name__ == "__main__":
    unittest.main()
