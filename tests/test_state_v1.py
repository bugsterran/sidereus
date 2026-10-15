"""sidereus/state_v1 — public sidereus-state v1 projection, its stdlib validator and GET /api/v1/state.
No live files, clock or network: every source is monkeypatched on sidereus.state_v1."""
import copy
import json
import os
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


if __name__ == "__main__":
    unittest.main()
