"""Deterministic tests for sidereus/saver.py switch validation and the HTTP host / repo allow-list guards.

Safety: the real ~/.claude/hooks/.saver-force.json and .saver-goal.json are never written —
SAVER_FORCE / SAVER_GOAL are redirected to a temp dir before any call, and a module-level
recorder asserts at the end that no saver write, lock or replace ever targeted a real file.
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import load, sidereus

cs = load()   # only for Handler, which lives in chat_server.py itself
cfg = sidereus("config")
sv = sidereus("saver")
gitm = sidereus("git_view")   # _repo_ok/_branch_ok and the sessions_rows they read live here

_REAL = [os.path.expanduser("~/.claude/hooks/.saver-force.json"),
         os.path.expanduser("~/.claude/hooks/.saver-goal.json"),
         os.path.expanduser("~/.claude/hooks/.saver-limit.json")]


# Guard: record every path the saver module writes, locks or replaces during this module.
# ⚠Do not compare the real files' bytes/mtime instead — the live hook rewrites them mid-run and that flaked.
_WROTE = []
_GUARD = []


def _recording(name):
    real = getattr(sv, name)

    def wrap(path, *a, **kw):
        _WROTE.append(os.path.realpath(path))
        return real(path, *a, **kw)
    return wrap


def setUpModule():
    for name in ("_saver_write", "_saver_lock", "_atomic_write"):
        p = mock.patch.object(sv, name, _recording(name))
        p.start()
        _GUARD.append(p)


def tearDownModule():
    for p in _GUARD:
        p.stop()
    real = {os.path.realpath(p) for p in _REAL}
    hit = sorted(set(_WROTE) & real)
    assert _WROTE and not hit, "tests wrote to real saver files: %s" % hit


class _TempSaver(unittest.TestCase):
    """Redirect both switch files to a temp dir and stub quota() (no network, no real cache)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="saver-test-")
        self.force = os.path.join(self.tmp, ".saver-force.json")
        self.goal = os.path.join(self.tmp, ".saver-goal.json")
        for p in (mock.patch.object(sv, "SAVER_FORCE", self.force),
                  mock.patch.object(sv, "SAVER_GOAL", self.goal),
                  mock.patch.object(sv, "SAVER_LIMIT", os.path.join(self.tmp, ".saver-limit.json")),
                  mock.patch.object(sv, "SAVER_TRASH", os.path.join(self.tmp, "trash")),
                  mock.patch.object(sv, "quota", lambda: {}),
                  mock.patch.object(sv, "SAVER_VIEW", os.path.join(self.tmp, ".saver-view.json"))):
            p.start()
            self.addCleanup(p.stop)
        self.assertNotIn(self.force, _REAL)
        sv._saver_force_cache["at"] = 0.0
        sv._saver_sw_cache["at"] = 0.0
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def raw(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()


class SaverIntTest(unittest.TestCase):
    def test_accepts_ascii_digits_and_ints(self):
        self.assertEqual(sv._saver_int("3", 1, 4), 3)
        self.assertEqual(sv._saver_int(4, 1, 4), 4)
        self.assertEqual(sv._saver_int("0", 0, 100), 0)

    def test_rejects_non_ascii_and_malformed(self):
        for v in ("１２", "²", "-1", "", " 3", "3 ", "3.0", "+3", None, 3.0, [3]):
            self.assertIsNone(sv._saver_int(v, 0, 100), repr(v))

    def test_rejects_bools_and_out_of_range(self):
        self.assertIsNone(sv._saver_int(True, 0, 100))
        self.assertIsNone(sv._saver_int(False, 0, 100))
        self.assertIsNone(sv._saver_int(5, 1, 4))
        self.assertIsNone(sv._saver_int("101", 0, 100))


class HhmmTest(unittest.TestCase):
    def test_accepts_valid_times(self):
        for s in ("00:00", "0:00", "9:05", "09:05", "19:00", "23:59"):
            self.assertTrue(sv._SAVER_HHMM.fullmatch(s), s)

    def test_rejects_invalid_times(self):
        for s in ("24:00", "9:5", "09:60", "19:00\n", "19:00x", " 19:00", "1900", "", "１９:00"):
            self.assertIsNone(sv._SAVER_HHMM.fullmatch(s), repr(s))

    def test_matches_saver_mode_sh_case_pattern(self):
        # saver-mode.sh `pace`: [0-9]:[0-5][0-9] | [01][0-9]:[0-5][0-9] | 2[0-3]:[0-5][0-9]
        import fnmatch
        pats = ("[0-9]:[0-5][0-9]", "[01][0-9]:[0-5][0-9]", "2[0-3]:[0-5][0-9]")
        for h in range(0, 30):
            for m in (0, 5, 59, 60):
                for s in ("%d:%02d" % (h, m), "%02d:%02d" % (h, m)):
                    sh = any(fnmatch.fnmatchcase(s, p) for p in pats)
                    self.assertEqual(bool(sv._SAVER_HHMM.fullmatch(s)), sh, s)


class SaverSetValidationTest(_TempSaver):
    def assertRejected(self, req):
        out = sv.saver_set(req)
        self.assertFalse(out["ok"], req)
        self.assertFalse(os.path.exists(self.force), req)
        self.assertFalse(os.path.exists(self.goal), req)

    def test_rejects_non_dict_and_empty(self):
        for req in (None, [], "on", {}, {"stage": 2}):
            self.assertRejected(req)

    def test_rejects_bad_mode(self):
        for m in ("ON", "pause", "", 1):
            self.assertRejected({"mode": m})

    def test_rejects_bad_stage(self):
        for st in (0, 5, "２", True, 2.0, "2.0", None):
            self.assertRejected({"mode": "on", "stage": st})

    def test_rejects_bad_until(self):
        for u in ("24:00", "9:5", "19:00\n", None, 1900):
            self.assertRejected({"mode": "pace", "until": u})

    def test_rejects_bad_goal(self):
        for g in (-1, 101, "abc", 50.5, True, "５０"):
            self.assertRejected({"goal": g})

    def test_bad_goal_blocks_valid_mode_write(self):
        # All-or-nothing: a valid mode must not be written when goal is invalid.
        self.assertRejected({"mode": "on", "stage": 2, "goal": 200})


class SaverSetShapeTest(_TempSaver):
    def test_on_stage_bytes_match_skill(self):
        self.assertTrue(sv.saver_set({"mode": "on", "stage": 2})["ok"])
        self.assertEqual(self.raw(self.force), '{"mode":"on","stage":2}\n')

    def test_on_default_stage_is_3(self):
        sv.saver_set({"mode": "on"})
        self.assertEqual(self.raw(self.force), '{"mode":"on","stage":3}\n')

    def test_on_string_stage(self):
        sv.saver_set({"mode": "on", "stage": "4"})
        self.assertEqual(json.loads(self.raw(self.force)), {"mode": "on", "stage": 4})

    def test_pace_bytes_match_skill(self):
        sv.saver_set({"mode": "pace", "until": "19:00"})
        self.assertEqual(self.raw(self.force), '{"mode":"pace","until":"19:00"}\n')

    def test_off_bytes_match_skill(self):
        sv.saver_set({"mode": "off"})
        self.assertEqual(self.raw(self.force), '{"mode":"off"}\n')

    def test_auto_removes_force_and_tolerates_missing(self):
        sv.saver_set({"mode": "off"})
        self.assertTrue(sv.saver_set({"mode": "auto"})["ok"])
        self.assertFalse(os.path.exists(self.force))
        self.assertTrue(sv.saver_set({"mode": "auto"})["ok"])

    def test_goal_bytes_match_skill(self):
        sv.saver_set({"goal": 80})
        self.assertEqual(self.raw(self.goal), '{"goal":80}\n')
        sv.saver_set({"goal": "off"})
        self.assertEqual(self.raw(self.goal), '{"goal":null}\n')
        sv.saver_set({"goal": None})
        self.assertEqual(self.raw(self.goal), '{"goal":null}\n')

    def test_goal_only_leaves_force_untouched(self):
        sv.saver_set({"goal": "0"})
        self.assertFalse(os.path.exists(self.force))
        self.assertEqual(json.loads(self.raw(self.goal)), {"goal": 0})

    def test_mode_switch_drops_stale_keys_but_keeps_unknown(self):
        with open(self.force, "w", encoding="utf-8") as f:
            f.write('{"mode":"pace","until":"19:00","note":"x"}\n')
        sv.saver_set({"mode": "on", "stage": 1})
        self.assertEqual(json.loads(self.raw(self.force)), {"mode": "on", "stage": 1, "note": "x"})

    def test_sed_parse_of_status_branch(self):
        # saver-mode.sh status reads mode/stage/until with sed; emulate its regexes on our bytes.
        import re
        sv.saver_set({"mode": "on", "stage": 2})
        s = self.raw(self.force)
        self.assertEqual(re.search(r'"mode":"([a-z]*)"', s).group(1), "on")
        self.assertEqual(re.search(r'"stage":([0-9]*)', s).group(1), "2")


class SaverSetLockTest(_TempSaver):
    """Two threads calling saver_set at once must serialize read-merge-write (no lost update)."""

    def _race(self, reqs):
        import threading
        real_read, state = sv._saver_read, {"in": 0, "max": 0}
        mu, both = threading.Lock(), threading.Event()

        def slow_read(path):
            # Hold the read->write window open until a second reader arrives. Unlocked, the other thread
            # enters at once and releases the wait; locked, it cannot, and the wait simply expires (peak stays 1).
            with mu:
                state["in"] += 1
                state["max"] = max(state["max"], state["in"])
                if state["in"] >= 2:
                    both.set()
            both.wait(0.3)
            v = real_read(path)
            with mu:
                state["in"] -= 1
            return v

        # Stub _saver_switch so the only reads counted are the locked merge reads.
        with mock.patch.object(sv, "_saver_read", slow_read), mock.patch.object(sv, "_saver_switch", dict):
            ts = [threading.Thread(target=sv.saver_set, args=(r,)) for r in reqs]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
        return state["max"]

    def test_same_file_both_merges_survive(self):
        with open(self.force, "w", encoding="utf-8") as f:
            f.write('{"mode":"off","note":"x"}\n')
        # Each thread writes the merged file; with the lock both reads see a whole file and "note" survives.
        peak = self._race([{"mode": "on", "stage": 2}, {"mode": "pace", "until": "19:00"}])
        self.assertEqual(peak, 1)
        self.assertIn(self.raw(self.force), ('{"mode":"on","stage":2,"note":"x"}\n',
                                             '{"mode":"pace","until":"19:00","note":"x"}\n'))
        self.assertEqual([n for n in os.listdir(self.tmp) if ".tmp." in n], [])

    def test_mode_and_goal_both_survive(self):
        self._race([{"mode": "on", "stage": 1}, {"goal": 55}])
        self.assertEqual(self.raw(self.force), '{"mode":"on","stage":1}\n')
        self.assertEqual(self.raw(self.goal), '{"goal":55}\n')


class SaverSwitchReadTest(_TempSaver):
    def test_default_is_auto_goal_100(self):
        self.assertEqual(sv._saver_switch(),
                         {"mode": "auto", "stage": 0, "until": None, "goal": 100, "goalSet": False, "limit": "advise"})

    def test_roundtrip_on_and_goal(self):
        out = sv.saver_set({"mode": "on", "stage": 2, "goal": 70})
        self.assertEqual(out["switch"],
                         {"mode": "on", "stage": 2, "until": None, "goal": 70, "goalSet": True, "limit": "advise"})
        self.assertEqual(out["saver"]["why"], "manual")
        self.assertEqual(out["saver"]["cap"], 1)

    def test_roundtrip_pace_and_goal_off(self):
        out = sv.saver_set({"mode": "pace", "until": "7:30", "goal": "off"})
        self.assertEqual(out["switch"],
                         {"mode": "pace", "stage": 0, "until": "7:30", "goal": None, "goalSet": True, "limit": "advise"})

    def test_garbage_files_fall_back(self):
        with open(self.force, "w", encoding="utf-8") as f:
            f.write('{"mode":"on","stage":9}')
        with open(self.goal, "w", encoding="utf-8") as f:
            f.write("not json")
        v = sv._saver_switch()
        self.assertEqual((v["mode"], v["stage"], v["goal"], v["goalSet"]), ("on", 3, 100, False))

    def test_state_off_and_quota_stage(self):
        sv.saver_set({"mode": "off"})
        self.assertEqual(sv._saver_state(99, 600)["why"], "off")
        sv.saver_set({"mode": "auto"})
        st = sv._saver_state(80, 600)
        self.assertEqual((st["why"], st["stage"], st["cap"]), ("quota", 2, 1))
        # A past window's % (leftSec <= 0) must not turn saver on.
        self.assertFalse(sv._saver_state(99, 0)["on"])

    def _view(self, **kw):
        with open(sv.SAVER_VIEW, "w", encoding="utf-8") as f:
            json.dump(dict({"at": 1000, "mode": "auto", "stage": 1}, **kw), f)

    def test_auto_follows_fresh_hook_stage(self):
        # Settings line (saver.stage) and status bar (saverView.stage) must show the same stage.
        sv.saver_set({"mode": "auto"})
        clock = mock.patch.object(sv, "time", mock.Mock(wraps=sv.time, time=lambda: 1060.0))
        clock.start()
        self.addCleanup(clock.stop)
        self._view(stage=1)
        st = sv._saver_state(83, 600)
        self.assertEqual((st["on"], st["stage"], st["cap"]), (True, 1, sv.SAVER_CAP[1]))
        self._view(stage=0)
        self.assertFalse(sv._saver_state(83, 600)["on"])
        self._view(stage=1)
        self.assertFalse(sv._saver_state(83, 0)["on"])          # past window still never turns on
        self._view(stage=1, at=1060 - sv.SAVER_VIEW_STALE - 1)    # stale -> % table fallback
        self.assertEqual(sv._saver_state(83, 600)["stage"], 2)
        self._view(stage=1, mode="pace")                          # other mode's verdict is ignored
        self.assertEqual(sv._saver_state(83, 600)["stage"], 2)


class _FakeHandler:
    """Minimal stand-in for Handler: headers + response sinks, so _host_ok runs unbound."""

    def __init__(self, host):
        self.headers = {} if host is None else {"Host": host}
        self.codes = []
        self.wfile = self

    def send_response(self, c):
        self.codes.append(c)

    def send_header(self, *a):
        pass

    def end_headers(self):
        pass

    def write(self, b):
        pass

    _refuse = cs.Handler._refuse
    _send = cs.Handler._send


class HostOkTest(unittest.TestCase):
    def ok(self, host):
        h = _FakeHandler(host)
        r = cs.Handler._host_ok(h)
        self.assertEqual(h.codes, [] if r else [403], host)
        return r

    def test_accepts_loopback_with_port(self):
        p = cfg.PORT
        for h in ("127.0.0.1:%d" % p, "localhost:%d" % p, "LOCALHOST:%d" % p, " 127.0.0.1:%d " % p):
            self.assertTrue(self.ok(h), h)

    def test_rejects_others(self):
        p = cfg.PORT
        for h in (None, "", "evil.com", "evil.com:%d" % p, "127.0.0.1.evil.com:%d" % p,
                  "127.0.0.1", "localhost", "127.0.0.1:%d" % (p + 1), "0.0.0.0:%d" % p,
                  "[::1]:%d" % p, "127.0.0.1:%d.evil.com" % p, "127.0.0.2:%d" % p):
            self.assertFalse(self.ok(h), repr(h))


class RepoAllowListTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="repo-ok-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.a = os.path.join(self.tmp, "a")
        self.b = os.path.join(self.tmp, "b")
        self.out = os.path.join(self.tmp, "outside")
        for d in (self.a, self.b, self.out):
            os.makedirs(d)

    def test_repo_ok(self):
        allowed = {self.a}
        self.assertTrue(gitm._repo_ok(self.a, allowed))
        self.assertFalse(gitm._repo_ok(self.out, allowed))
        self.assertFalse(gitm._repo_ok("", allowed))
        self.assertFalse(gitm._repo_ok(None, allowed))
        self.assertFalse(gitm._repo_ok(self.a + "/../outside", allowed))

    def test_repo_ok_worktree_of_allowed_main(self):
        wt = os.path.join(self.tmp, "wt")
        os.makedirs(wt)
        with open(os.path.join(wt, ".git"), "w", encoding="utf-8") as f:
            f.write("gitdir: %s/.git/worktrees/wt\n" % self.a)
        main = gitm._wt_main(wt)
        self.assertEqual(gitm._repo_ok(wt, {self.a}), main == self.a)

    def test_branch_ok_uses_synthetic_sessions(self):
        rows = [{"cwd": self.a, "repos": [self.b]}]
        with mock.patch.object(gitm, "sessions_rows", lambda **k: rows):
            self.assertTrue(gitm._branch_ok(self.a))
            self.assertTrue(gitm._branch_ok(self.b))          # touched repo
            self.assertTrue(gitm._branch_ok(gitm.CODE_DIR))   # Sidereus itself
            self.assertFalse(gitm._branch_ok(self.out))
            # realpath("") resolves to the process cwd (= CODE_DIR); the guard must reject before that.
            for bad in ("", None, 0, b"/tmp", [self.a]):
                self.assertFalse(gitm._branch_ok(bad), repr(bad))
            self.assertFalse(gitm._branch_ok("/"))

    def test_branch_ok_symlink_into_allowed(self):
        link = os.path.join(self.tmp, "link")
        os.symlink(self.a, link)
        rows = [{"cwd": self.a, "repos": []}]
        with mock.patch.object(gitm, "sessions_rows", lambda **k: rows):
            self.assertTrue(gitm._branch_ok(link))            # realpath resolves into allowed
        bad = os.path.join(self.tmp, "badlink")
        os.symlink(self.out, bad)
        with mock.patch.object(gitm, "sessions_rows", lambda **k: rows):
            self.assertFalse(gitm._branch_ok(bad))

    def test_branch_ok_survives_sessions_rows_failure(self):
        def boom(**k):
            raise RuntimeError("ps slow")
        with mock.patch.object(gitm, "sessions_rows", boom):
            self.assertFalse(gitm._branch_ok(self.a))
            self.assertTrue(gitm._branch_ok(gitm.CODE_DIR))


if __name__ == "__main__":
    unittest.main()


class SaverLimitTest(_TempSaver):
    """Goal-reached action (advise|warn|block) — own file, backup before write, viewer Origin on the route."""

    def test_default_advise_and_write(self):
        self.assertEqual(sv._saver_switch()["limit"], "advise")
        out = sv.saver_set({"limit": "block"})
        self.assertTrue(out["ok"])
        self.assertEqual(out["switch"]["limit"], "block")
        self.assertEqual(self.raw(sv.SAVER_LIMIT), '{"action":"block"}\n')
        self.assertNotIn("backup", out)                       # nothing to back up the first time
        out = sv.saver_set({"limit": "warn"})
        self.assertTrue(os.path.isfile(out["backup"]) and out["backup"].startswith(sv.SAVER_TRASH))
        self.assertEqual(self.raw(out["backup"]), '{"action":"block"}\n')
        self.assertFalse(os.path.exists(self.force) or os.path.exists(self.goal))

    def test_rejects_unknown(self):
        for v in ("stop", "", True, 1):
            self.assertFalse(sv.saver_set({"limit": v})["ok"], v)
        self.assertFalse(os.path.exists(sv.SAVER_LIMIT))

    def test_route_requires_viewer_origin(self):
        from tests.test_routes_post import post, EVIL
        from tests.test_prefs import ORIGIN
        for origin in (None, EVIL):
            code, _o, _ = post("/api/saver/set", {"limit": "block"}, origin=origin)
            self.assertEqual(code, 403)
        self.assertFalse(os.path.exists(sv.SAVER_LIMIT))
        code, out, _ = post("/api/saver/set", {"limit": "warn"}, origin=ORIGIN)
        self.assertEqual((code, out["switch"]["limit"]), (200, "warn"))
