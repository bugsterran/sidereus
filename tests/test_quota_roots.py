"""Per-account quota for extra signed-in roots (sidereus/quota_roots.py).

Everything is patched on `quota_roots`: subprocess, urlopen, clock, roots, home and lookup switch. Temp dirs only.
"""
import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
import urllib.error
import urllib.request

from tests._load import sidereus

qr = sidereus("quota_roots")
q = sidereus("quota")
st = sidereus("state")

NOW = 1_790_000_000.0
BODY = {"five_hour": {"utilization": 40, "resets_at": "2026-10-11T10:00:40Z"},
        "seven_day": {"utilization": 12, "resets_at": "2026-10-15T00:00:00Z"}}


class _Run(object):
    def __init__(self, ok_svc=None, secret='{"claudeAiOauth": {"accessToken": "TOK-A"}}'):
        self.calls, self.ok_svc, self.secret = [], ok_svc, secret

    def __call__(self, argv, **kw):
        self.calls.append(list(argv))
        svc = argv[argv.index("-s") + 1]

        class R(object):
            returncode = 0 if svc == self.ok_svc else 44
            stdout = self.secret if "-w" in argv else ""
        return R()


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.home = os.path.join(self.tmp, "home")
        self.prim = os.path.join(self.home, ".claude")
        os.makedirs(os.path.join(self.prim, "plugins"))
        self.roots = []
        self.urls = []
        self.http = {}          # token -> body | HTTPError
        self.run = _Run()
        self.saved = {}

        class T(object):
            @staticmethod
            def time():
                return NOW
        self._patch(qr, USER_HOME=self.home, time=T, IS_MAC=True, _quota_lookup_on=lambda: True,
                    _cc_account=lambda: "uuid-prim", _quota_interval=lambda: 60,
                    claude_home=lambda: self.prim, _acc={}, _uuid_cache={},
                    PTS_FILE=os.path.join(self.tmp, "pts.json"), _pts={}, _pts_loaded=False)
        self._patch(qr.subprocess, run=self.run)
        self._patch(urllib.request, urlopen=self._urlopen)
        self._patch(qr.claude_roots, roots=lambda: [dict(r) for r in self.roots],
                    accounts=lambda: [dict(r) for r in self.roots])

    def tearDown(self):
        for (m, k), v in self.saved.items():
            setattr(m, k, v)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _patch(self, mod, **kw):
        for k, v in kw.items():
            self.saved.setdefault((mod, k), getattr(mod, k))
            setattr(mod, k, v)

    def _urlopen(self, req, timeout=None):
        tok = req.get_header("Authorization")[len("Bearer "):]
        self.urls.append(tok)
        r = self.http.get(tok, BODY)
        if isinstance(r, Exception):
            raise r
        return _Resp(json.dumps(r).encode("utf-8"))

    def _root(self, name, uuid="uuid-" + "x", creds=None):
        d = os.path.join(self.home, name)
        os.makedirs(d, exist_ok=True)
        if uuid is not None:
            with open(os.path.join(d, ".claude.json"), "w", encoding="utf-8") as f:
                json.dump({"oauthAccount": {"accountUuid": uuid, "emailAddress": "a@b.c"}}, f)
        if creds:
            with open(os.path.join(d, ".credentials.json"), "w", encoding="utf-8") as f:
                json.dump({"claudeAiOauth": {"accessToken": creds}}, f)
        self.roots.append({"dir": d, "label": name.lstrip(".").replace("claude-", ""), "primary": False})
        return d


def _svc(s):
    return "Claude Code-credentials-" + hashlib.sha256(s.encode("utf-8")).hexdigest()[:8]


class ServiceNames(Base):
    def test_hash_and_default_root(self):
        d = os.path.join(self.home, ".claude-work")
        names = qr._svc_names(d)
        self.assertEqual(names, [_svc(d), _svc(d + "/"), _svc("~/.claude-work")])
        self.assertEqual(qr._svc_names(self.prim), ["Claude Code-credentials"])

    def test_exists_check_has_no_w_and_w_only_after_match(self):
        d = self._root(".claude-work", "uuid-w")
        self.run.ok_svc = _svc("~/.claude-work")
        self.assertEqual(qr._kc_token(d), "TOK-A")
        with_w = [c for c in self.run.calls if "-w" in c]
        self.assertEqual(len(with_w), 1)
        self.assertEqual(with_w[0][with_w[0].index("-s") + 1], self.run.ok_svc)
        self.assertEqual(self.run.calls.index(with_w[0]), len(self.run.calls) - 1)
        self.assertTrue(all("-w" not in c for c in self.run.calls[:-1]))


class Targets(Base):
    def test_no_roots_empty_and_state_quota_unchanged(self):
        qr.tick()
        self.assertEqual(qr.quota_accounts(), [])
        self.assertEqual(self.urls, [])
        q0 = {"five_hour": {"pct": 5}}
        self.assertIs(st._with_accounts(q0), q0)
        self.assertIsNone(st._with_accounts(None))

    def test_shared_history_profile_targeted_by_uuid(self):
        # accounts() lists a profile whose projects/ is shared with the primary; uuid decides, not the scan root
        self._patch(qr.claude_roots, roots=lambda: [])
        self._root(".claude-alt", "uuid-alt")
        self._root(".claude-same", "uuid-prim")
        self.assertEqual([r["label"] for r, _u in qr._targets()], ["alt"])

    def test_state_merge_adds_accounts(self):
        self.run.ok_svc = _svc("~/.claude-work")
        self._root(".claude-work", "uuid-w")
        qr.tick()
        got = st._with_accounts({"five_hour": {"pct": 5}})
        self.assertEqual(got["five_hour"], {"pct": 5})
        self.assertEqual([a["label"] for a in got["accounts"]], ["work"])

    def test_same_uuid_or_signed_out_skipped(self):
        self._root(".claude-same", "uuid-prim", creds="TOK-S")
        self._root(".claude-out", None, creds="TOK-O")
        qr.tick()
        self.assertEqual(self.urls, [])
        self.assertEqual(qr.quota_accounts(), [])

    def test_row_is_metadata_only(self):
        self.run.ok_svc = _svc("~/.claude-work")
        self._root(".claude-work", "uuid-w")
        qr.tick()
        rows = qr.quota_accounts()
        self.assertEqual([r["label"] for r in rows], ["work"])
        self.assertEqual(rows[0]["five_hour"]["pct"], 40)
        self.assertEqual(rows[0]["five_hour"]["resets_at"], "2026-10-11T10:01:00+00:00")
        self.assertEqual(rows[0]["seven_day"]["pct"], 12)
        flat = json.dumps(rows)
        for bad in ("uuid-w", "a@b.c", "TOK-A", self.home):
            self.assertNotIn(bad, flat)


class OmcCache(Base):
    def _omc_dir(self, d):
        p = os.path.join(d, "plugins", "oh-my-claudecode")
        os.makedirs(p, exist_ok=True)
        return os.path.join(p, ".usage-cache-anthropic.json")

    def test_real_plugins_written_with_marker(self):
        d = self._root(".claude-work", "uuid-w", creds="TOK-W")
        self._patch(qr, IS_MAC=False)
        p = self._omc_dir(d)
        qr.tick()
        with open(p, encoding="utf-8") as f:
            c = json.load(f)
        self.assertTrue(c["sidereus"])
        self.assertEqual(c["data"]["fiveHourPercent"], 40)
        self.assertIsNone(qr._omc_read(d))      # our own marked file is never adopted

    def test_symlinked_plugins_no_read_no_write(self):
        d = self._root(".claude-work", "uuid-w", creds="TOK-W")
        self._patch(qr, IS_MAC=False)
        p = self._omc_dir(self.prim)
        os.symlink(os.path.join(self.prim, "plugins"), os.path.join(d, "plugins"))
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"timestamp": NOW * 1000, "data": {"fiveHourPercent": 99}}, f)
        self.http["TOK-W"] = urllib.error.HTTPError("u", 429, "x", {}, None)
        qr.tick()
        with open(p, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["data"]["fiveHourPercent"], 99)   # untouched
        self.assertIsNone(qr._omc_path(d))
        self.assertNotIn("five_hour", qr.quota_accounts()[0])               # primary's HUD value not adopted

    def test_symlinked_omc_subdir_refused(self):
        d = self._root(".claude-work", "uuid-w", creds="TOK-W")
        self._patch(qr, IS_MAC=False)
        p = self._omc_dir(self.prim)
        os.makedirs(os.path.join(d, "plugins"))
        os.symlink(os.path.dirname(p), os.path.join(d, "plugins", "oh-my-claudecode"))
        qr.tick()
        self.assertIsNone(qr._omc_path(d))
        self.assertFalse(os.path.exists(p))                                 # nothing written into the primary's dir


class Isolation(Base):
    def test_429_on_a_leaves_primary_and_b(self):
        self._patch(qr, IS_MAC=False)
        self._root(".claude-a", "uuid-a", creds="TOK-1")
        self._root(".claude-b", "uuid-b", creds="TOK-2")
        qr.tick()
        b_next = qr._acc["b"]["next"]
        prim = (dict(q._quota), list(q._quota_retry_after))
        hdr = {"Retry-After": "900"}
        self.http["TOK-1"] = urllib.error.HTTPError("u", 429, "x", hdr, None)
        qr._acc["a"]["next"] = 0
        qr.tick()
        self.assertEqual((dict(q._quota), list(q._quota_retry_after)), prim)
        self.assertEqual(qr._acc["b"]["next"], b_next)
        self.assertEqual(qr._acc["a"]["err"], "HTTPError 429")
        self.assertEqual(qr._acc["a"]["next"], NOW + 900)
        self.assertEqual(qr._acc["a"]["data"]["five_hour"]["pct"], 40)     # last good value kept

    def test_linux_reads_credentials_file(self):
        self._patch(qr, IS_MAC=False)
        self._root(".claude-work", "uuid-w", creds="TOK-L")
        qr.tick()
        self.assertEqual(self.urls, ["TOK-L"])
        self.assertEqual(self.run.calls, [])

    def test_lookup_off_no_subprocess_no_network(self):
        self._patch(qr, _quota_lookup_on=lambda: False)
        self._root(".claude-work", "uuid-w", creds="TOK-L")
        qr.tick()
        self.assertEqual((self.urls, self.run.calls), ([], []))
        self.assertEqual(qr.quota_accounts(), [])


class PtsRing(Base):
    def setUp(self):
        Base.setUp(self)
        self._patch(qr, IS_MAC=False)
        self.d = self._root(".claude-work", "uuid-w", creds="TOK-W")
        self.clock = [NOW]
        clock = self.clock

        class T(object):
            @staticmethod
            def time():
                return clock[0]
        self._patch(qr, time=T)
        self._patch(st, time=T)

    def _tick(self, pct, reset="2026-10-11T10:00:40Z", dt=60):
        self.http["TOK-W"] = {"five_hour": {"utilization": pct, "resets_at": reset}}
        qr._acc.get("work", {})["next"] = 0
        qr.tick()
        self.clock[0] += dt

    def _ring(self):
        return qr._pts["work"]["pts"]

    def test_append_only_on_change_and_file_metadata_only(self):
        self._tick(10)
        self._tick(10)
        self._tick(12)
        self.assertEqual(self._ring(), [[int(NOW), 10], [int(NOW) + 120, 12]])
        with open(qr.PTS_FILE, encoding="utf-8") as f:
            raw = f.read()
        for bad in ("uuid-w", "a@b.c", "TOK-W", self.home):
            self.assertNotIn(bad, raw)
        self.assertEqual(json.loads(raw)["work"]["acct"], hashlib.sha1(b"uuid-w", usedforsecurity=False).hexdigest()[:12])

    def test_new_reset_clears_but_jitter_does_not(self):
        self._tick(10)
        self._tick(12, reset="2026-10-11T10:00:59.600Z")
        self.assertEqual(len(self._ring()), 2)
        self._tick(1, reset="2026-10-11T15:00:40Z")
        self.assertEqual([p[1] for p in self._ring()], [1])

    def test_account_change_clears(self):
        self._tick(10)
        self._tick(12)
        with open(os.path.join(self.d, ".claude.json"), "w", encoding="utf-8") as f:
            json.dump({"oauthAccount": {"accountUuid": "uuid-other"}}, f)
        os.utime(os.path.join(self.d, ".claude.json"), (NOW + 999, NOW + 999))
        self._tick(30)
        self.assertEqual([p[1] for p in self._ring()], [30])

    def test_cap(self):
        for i in range(qr.PTS_CAP + 5):
            self._tick(i % 100 + (i // 100) * 0.5)
        self.assertEqual(len(self._ring()), qr.PTS_CAP)

    def test_reload_from_file(self):
        self._tick(10)
        self._tick(12)
        saved = qr._pts
        self._patch(qr, _pts={}, _pts_loaded=False)
        qr._acc["work"]["next"] = self.clock[0] + 999
        qr.tick()
        self.assertEqual(qr._pts, saved)

    def test_429_leaves_ring(self):
        self._tick(10)
        self._tick(12)
        before = [list(p) for p in self._ring()]
        self.http["TOK-W"] = urllib.error.HTTPError("u", 429, "x", {}, None)
        qr._acc["work"]["next"] = 0
        qr.tick()
        self.assertEqual(self._ring(), before)

    def test_dropped_root_drops_ring(self):
        self._tick(10)
        self.roots[:] = []
        qr.tick()
        self.assertNotIn("work", qr._pts)
        with open(qr.PTS_FILE, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {})

    def test_row_pts_only_with_matching_reset_and_two_points(self):
        self._tick(10)
        self.assertNotIn("pts", qr.quota_accounts()[0]["five_hour"])
        self._tick(12)
        self.assertEqual(len(qr.quota_accounts()[0]["five_hour"]["pts"]), 2)
        qr._pts["work"]["reset5"] += 3600
        self.assertNotIn("pts", qr.quota_accounts()[0]["five_hour"])

    def test_state_over_at_only_with_two_points(self):
        self._tick(10, dt=600)
        got = st._with_accounts({"five_hour": {"pct": 5}})
        self.assertNotIn("over_at", got["accounts"][0]["five_hour"])
        self._tick(40, dt=600)
        fh = st._with_accounts({"five_hour": {"pct": 5}})["accounts"][0]["five_hour"]
        self.assertIn("over_at", fh)
        self.assertGreater(fh["over_at"], self.clock[0])


if __name__ == "__main__":
    unittest.main()
