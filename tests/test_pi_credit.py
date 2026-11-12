"""pi «Credits» chip data: auth_kinds (R1, R4), credit_last, ext_presence row `credit`, state._who_pi `credit.tok`."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

pi = sidereus("plat_pi")
pres = sidereus("ext_presence")
stt = sidereus("state")
ext = sidereus("ext")
est = sidereus("ext_store")
att = sidereus("attention")

SID = "0199aaaa-bbbb-7ccc-8ddd-0000000000d1"
T0 = 1791162000.0      # 2026-10-05T01:00:00Z
DUMMY = "sk-test-DUMMY"


def _iso(t):
    import datetime
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def asst(eid, dt, prov="anthropic"):
    u = {"input": 1000, "output": 200, "cacheRead": 400, "cacheWrite": 100, "cost": {"total": 0.25}}
    m = {"role": "assistant", "content": [], "provider": prov, "model": "m1", "usage": u,
         "timestamp": int((T0 + dt) * 1000)}
    return {"type": "message", "id": eid, "timestamp": _iso(T0 + dt), "message": m}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-pi-credit-")
        self.root = os.path.join(self.tmp, "agent")
        os.makedirs(os.path.join(self.root, "sessions"))
        self.p = [mock.patch.object(pi, "root", lambda: self.root),
                  mock.patch.object(pres, "mbox_pi", lambda cwd: ("", "none"))]
        for p in self.p:
            p.start()
        pi._cache.clear()
        pi._AUTH.clear()

    def tearDown(self):
        for p in self.p:
            p.stop()
        pi._cache.clear()
        pi._AUTH.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def auth(self, d):
        with open(os.path.join(self.root, "auth.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def sess(self, entries):
        d = os.path.join(self.root, "sessions", "--w-proj--")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "2026-10-05T01-00-00-000Z_%s.jsonl" % SID)
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "session", "version": 3, "id": SID, "timestamp": _iso(T0), "cwd": "/w/proj"}) + "\n")
            for e in entries:
                f.write(json.dumps(e) + "\n")
        os.utime(p, (T0 + 100, T0 + 100))
        return p

    def row(self, now):
        c = pi.scan(0.0)[0]
        return pres._row("pi", c, now)


class TestAuthKinds(Base):
    def test_types_only(self):
        self.auth({"anthropic": {"type": "oauth", "access": DUMMY, "refresh": DUMMY},
                   "openai": {"type": "api_key", "key": DUMMY}, "BAD KEY": {"type": "oauth"},
                   "long": {"type": "x" * 21}, "nodict": DUMMY})
        k = pi.auth_kinds()
        self.assertEqual(k, {"anthropic": "oauth", "openai": "api_key"})
        self.assertNotIn(DUMMY, json.dumps(pi._AUTH))

    def test_missing_is_empty(self):
        self.assertEqual(pi.auth_kinds(), {})

    def test_bad_json_is_empty_and_type_name_only(self):
        with open(os.path.join(self.root, "auth.json"), "w", encoding="utf-8") as f:
            f.write('{"anthropic": "' + DUMMY)
        seen = []
        with mock.patch.object(pi, "warn_once", lambda *a, **kw: seen.append((a, kw))):
            self.assertEqual(pi.auth_kinds(), {})
        self.assertNotIn(DUMMY, json.dumps(seen))
        self.assertEqual(seen[0][1]["vars"]["err"], "JSONDecodeError")

    def test_over_cap_is_empty(self):
        with mock.patch.object(pi, "AUTH_MAX", 10):
            self.auth({"anthropic": {"type": "oauth"}})
            self.assertEqual(pi.auth_kinds(), {})

    def test_memo_no_reread(self):
        self.auth({"anthropic": {"type": "oauth", "access": DUMMY}})
        n = []
        real = open

        def counting(p, *a, **kw):
            if str(p).endswith("auth.json"):
                n.append(p)
            return real(p, *a, **kw)
        with mock.patch.object(pi, "open", counting, create=True):
            pi.auth_kinds()
            pi.auth_kinds()
            self.assertEqual(len(n), 1)
            self.auth({"anthropic": {"type": "api_key", "key": DUMMY + "-longer"}})
            self.assertEqual(pi.auth_kinds(), {"anthropic": "api_key"})
            self.assertEqual(len(n), 2)


class TestCreditRow(Base):
    def test_oauth_anthropic_sets_credit_and_tok(self):
        self.auth({"anthropic": {"type": "oauth", "access": DUMMY}})
        self.sess([asst("a0", -200), asst("a1", 10), asst("a2", 20), asst("o1", 30, prov="openai")])
        now = T0 + 60
        r = self.row(now)
        self.assertEqual(r["credit"], {"lastAt": int(T0 + 20)})
        who = {"start": T0 - 100, "rows": [], "total": 0}
        lst = [r]
        out = stt._who_pi(who, now, lst)
        self.assertEqual(lst[0]["credit"]["tok"], 3400)     # two anthropic entries in the window, 1700 each
        self.assertNotIn("roll", lst[0]["credit"])
        self.assertNotIn(DUMMY, json.dumps([lst, out]))

    def test_no_start_uses_rolling_window(self):
        self.auth({"anthropic": {"type": "oauth"}})
        self.sess([asst("a1", 10)])
        r = self.row(T0 + 60)
        lst = [r]
        self.assertIsNone(stt._who_pi(None, T0 + 60, lst))
        self.assertEqual((lst[0]["credit"]["tok"], lst[0]["credit"]["roll"]), (1700, 1))

    def test_api_key_no_credit(self):
        self.auth({"anthropic": {"type": "api_key", "key": DUMMY}})
        self.sess([asst("a1", 10)])
        r = self.row(T0 + 60)
        self.assertNotIn("credit", r)
        self.assertNotIn(DUMMY, json.dumps(r))

    def test_other_provider_only_no_credit(self):
        self.auth({"anthropic": {"type": "oauth"}})
        self.sess([asst("o1", 10, prov="openai")])
        self.assertNotIn("credit", self.row(T0 + 60))

    def test_no_auth_file_no_credit(self):
        self.sess([asst("a1", 10)])
        self.assertNotIn("credit", self.row(T0 + 60))

    def test_credit_last(self):
        self.assertEqual(pi.credit_last({}), 0)
        self.assertEqual(pi.credit_last(None), 0)
        self.assertEqual(pi.credit_last({"a": (1, 1, 1, 0, 5.0, "anthropic/m", None),
                                         "b": (1, 1, 1, 0, 9.0, "openai/m", None)}), 5.0)


class TestHookedRow(Base):
    """Hook rows (pi extension connected) come from ext.ext_rows, not ext_presence: same credit rule."""

    def setUp(self):
        super().setUp()
        self.saved = (dict(est._ext), est._ext_save_locked)
        est._ext_save_locked = lambda: None
        est._ext.clear()
        pi._path_memo.clear()
        self.p2 = [mock.patch.object(ext.time, "time", lambda: T0 + 60),
                   mock.patch.object(ext, "plm_of", lambda sid, now: None)]
        for p in self.p2:
            p.start()

    def tearDown(self):
        for p in self.p2:
            p.stop()
        est._ext.clear()
        est._ext.update(self.saved[0])
        est._ext_save_locked = self.saved[1]
        with est._tok_lock:
            est._tok.pop(("pi", SID), None)
        super().tearDown()

    def hooked(self, **kw):
        path = self.sess([asst("a1", 10), asst("a2", 20)])
        self.path = path
        # ⚠no transcript_path: the real pi extension payload carries only session_id
        v = {"cwd": "/w/proj", "state": "tool", "firstSeen": T0, "lastSeen": T0 + 55}
        v.update(kw)
        est._ext[("pi", SID)] = v
        return [r for r in ext.ext_rows() if r["sid"] == SID]

    def test_hooked_row_gets_credit_and_attention(self):
        self.auth({"anthropic": {"type": "oauth", "access": DUMMY}})
        rows = self.hooked()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["credit"], {"lastAt": int(T0 + 20)})
        self.assertEqual(rows[0]["tok"], 3400)
        sg = [s for s in att._row_sigs(rows[0], T0 + 60) if s["k"] == "credit"]
        self.assertEqual(len(sg), 1)
        self.assertNotIn(DUMMY, json.dumps(rows))

    def test_hooked_row_done_drops_from_attention(self):
        self.auth({"anthropic": {"type": "oauth"}})
        rows = self.hooked(state="done")   # the CLI ended its turn
        self.assertEqual(rows[0]["state"], "done")
        self.assertEqual([s for s in att._row_sigs(rows[0], T0 + 60) if s["k"] == "credit"], [])

    def test_hooked_row_nul_cwd_still_listed(self):
        self.auth({"anthropic": {"type": "oauth"}})
        rows = self.hooked(cwd="/w/\0proj")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["credit"], {"lastAt": int(T0 + 20)})

    def test_hooked_row_api_key_no_credit(self):
        self.auth({"anthropic": {"type": "api_key", "key": DUMMY}})
        self.assertNotIn("credit", self.hooked()[0])


class TestSidPath(Base):
    def test_found_by_sid_and_memoised(self):
        p = self.sess([asst("a1", 10)])
        pi._path_memo.clear()
        with mock.patch.object(pi, "time", mock.Mock(time=lambda: T0)):
            self.assertEqual(pi.sid_path(SID, "/w/proj"), p)
            with mock.patch.object(pi.glob, "glob", lambda pat: self.fail("glob after a hit")):
                self.assertEqual(pi.sid_path(SID, "/w/proj"), p)
            self.assertEqual(pi.sid_path("../x"), "")

    def test_nul_cwd_no_raise(self):
        p = self.sess([asst("a1", 10)])
        pi._path_memo.clear()
        with mock.patch.object(pi, "time", mock.Mock(time=lambda: T0)):
            self.assertEqual(pi.sid_path(SID, "/w/\0proj"), p)   # cwd pattern skipped, all-folder lookup still finds it
            pi._path_memo.clear()
            with mock.patch.object(pi.glob, "glob", mock.Mock(side_effect=ValueError("embedded null byte"))):
                self.assertEqual(pi.sid_path(SID, "/w/proj"), "")

    def test_miss_memoised(self):
        pi._path_memo.clear()
        clock = mock.Mock(time=lambda: T0)
        with mock.patch.object(pi, "time", clock):
            self.assertEqual(pi.sid_path("nosuch"), "")
            with mock.patch.object(pi.glob, "glob", lambda pat: self.fail("glob within PATH_MISS_S")):
                self.assertEqual(pi.sid_path("nosuch"), "")
            clock.time = lambda: T0 + pi.PATH_MISS_S
            self.assertEqual(pi.sid_path("nosuch"), "")   # looked up again (glob allowed)


class TestAuthNotRegular(Base):
    def test_directory_refused(self):
        os.makedirs(os.path.join(self.root, "auth.json"))
        self.assertEqual(pi.auth_kinds(), {})


class TestWhoPiCopies(Base):
    def test_rows_not_mutated(self):
        self.auth({"anthropic": {"type": "oauth"}})
        self.sess([asst("a1", 10)])
        r = self.row(T0 + 60)
        before = json.dumps(r, sort_keys=True)
        lst = [r]
        stt._who_pi({"start": T0 - 100, "rows": [], "total": 0}, T0 + 60, lst)
        self.assertEqual(json.dumps(r, sort_keys=True), before)
        self.assertEqual(lst[0]["credit"]["tok"], 1700)


if __name__ == "__main__":
    unittest.main()
