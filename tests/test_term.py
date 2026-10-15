"""«터미널로»: tty/app detection, termApp setting, POST /api/term/focus validation. No real ps/osascript/files."""
import io
import json
import unittest

from tests._load import sidereus, load

term = sidereus("term")
SID = "aa11aa11-1111-4111-8111-111111111111"
SID2 = "bb22bb22-2222-4222-8222-222222222222"


class _Run:
    def __init__(self, out):
        self.out, self.calls = out, []

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        o = self.out(argv) if callable(self.out) else self.out
        return type("R", (), {"stdout": o, "stderr": ""})()


class Base(unittest.TestCase):
    def patch(self, mod, name, val):
        old = getattr(mod, name)
        setattr(mod, name, val)
        self.addCleanup(setattr, mod, name, old)


class Detect(Base):
    def setUp(self):
        self.patch(term, "IS_MAC", True)
        self.patch(term, "_TTY_CACHE", {})
        self.patch(term, "_TTY_FAIL", [0.0])

    def test_app_of_env(self):
        self.assertEqual(term.app_of_env("claude --x TERM_PROGRAM=iTerm.app HOME=/h"), "iterm")
        self.assertEqual(term.app_of_env("claude TERM_PROGRAM=Apple_Terminal"), "apple")
        self.assertEqual(term.app_of_env("claude TERM_PROGRAM=tmux LC_TERMINAL=iTerm2"), "other")
        self.assertEqual(term.app_of_env("claude LC_TERMINAL=iTerm2"), "iterm")
        self.assertEqual(term.app_of_env("claude"), "other")

    def test_attach_maps_official_and_argv(self):
        av = {"101": {"sessionId": SID}}
        snap = [("101", "1", "claude"), ("202", "1", "/usr/bin/claude --resume " + SID2), ("303", "1", "vim " + SID2)]
        self.patch(term, "_av_cache", [0.0, av])
        self.patch(term, "_ps_snap_cache", [0.0, snap])
        run = _Run("101 ttys003 claude TERM_PROGRAM=iTerm.app\n202 ?? claude --resume x TERM_PROGRAM=Apple_Terminal\n")
        self.patch(term.subprocess, "run", run)
        rows = [{"sid": SID, "state": "wait"}, {"sid": SID2, "state": "tool"},
                {"sid": SID, "state": "done"}, {"sid": "g", "ext": True}]
        term.term_attach(rows)
        self.assertEqual(rows[0]["term"], {"app": "iterm", "tty": "ttys003"})
        self.assertIsNone(rows[1]["term"])          # "??" = no tty
        self.assertIsNone(rows[2]["term"])          # ended row
        self.assertNotIn("term", rows[3])           # external CLI rows untouched
        self.assertEqual(run.calls, [["ps", "-Ewwo", "pid=,tty=,command=", "-p", "101,202"]])
        term.term_attach(rows)                      # cached: no second fork
        self.assertEqual(len(run.calls), 1)

    def test_sid_pids_int_keys_not_doubled(self):
        out = term._sid_pids({101: {"sessionId": SID}}, [("101", "1", "claude --resume " + SID2)])
        self.assertEqual(out, {SID: ["101"]})       # int av key vs str ps pid: same process, argv not re-added

    def test_probe_failure_is_cached(self):
        self.patch(term, "_av_cache", [0.0, {"101": {"sessionId": SID}}])
        self.patch(term, "_ps_snap_cache", [0.0, []])
        n = []

        def boom(*a, **k):
            n.append(1)
            raise OSError("x")
        self.patch(term.subprocess, "run", boom)
        self.patch(term, "warn_once", lambda *a, **k: None)
        rows = [{"sid": SID, "state": "wait"}]
        term.term_attach(rows)
        term.term_attach(rows)
        self.assertEqual(len(n), 1)
        self.assertIsNone(rows[0]["term"])

    def test_stale_entry_kept_when_reprobe_times_out(self):
        self.patch(term, "_av_cache", [0.0, {"101": {"sessionId": SID}}])
        self.patch(term, "_ps_snap_cache", [0.0, []])
        self.patch(term, "_TTY_CACHE", {"101": (1.0, "ttys003", "iterm", None)})   # long past TTY_TTL

        def slow(*a, **k):
            raise term.subprocess.TimeoutExpired("ps", 3)
        self.patch(term.subprocess, "run", slow)
        self.patch(term, "warn_once", lambda *a, **k: None)
        rows = [{"sid": SID, "state": "wait"}]
        term.term_attach(rows)
        self.assertEqual(rows[0]["term"], {"app": "iterm", "tty": "ttys003"})   # a pid's tty never changes

    def test_gone_pid_dropped_on_answer(self):
        self.patch(term, "_av_cache", [0.0, {"101": {"sessionId": SID}}])
        self.patch(term, "_ps_snap_cache", [0.0, []])
        self.patch(term, "_TTY_CACHE", {"101": (1.0, "ttys003", "iterm", None)})
        self.patch(term.subprocess, "run", _Run(""))          # ps answered without the pid = gone
        rows = [{"sid": SID, "state": "wait"}]
        term.term_attach(rows)
        self.assertIsNone(rows[0]["term"])


class Focus(Base):
    _real_resolve = staticmethod(term._resolve)
    ROW = {"sid": SID, "state": "wait", "term": {"app": "iterm", "tty": "ttys003"}}

    def setUp(self):
        self.patch(term, "IS_MAC", True)
        self.run = _Run("ok\n")
        self.patch(term.subprocess, "run", self.run)
        self.patch(term, "term_cfg", lambda: "auto")
        self.patch(term, "_resolve", lambda sid: (True, None))
        self.patch(term, "_JUMP_FAILS", {})
        self.warns = []
        self.patch(term, "warn_once", lambda key, msg, **k: self.warns.append((key, k.get("vars"))))

    def test_focus_argv_fixed_script(self):
        code, out = term.term_focus(SID, [dict(self.ROW)])
        self.assertEqual((code, out["how"], out["cmd"]), (200, "focused", "claude --resume " + SID))
        [argv] = self.run.calls
        self.assertEqual(argv[:2], ["osascript", "-e"])
        self.assertEqual(argv[2], term._SCRIPT_ITERM)       # script text is the constant — tty not interpolated
        self.assertNotIn("ttys003", argv[2])
        self.assertEqual(argv[3], "/dev/ttys003")

    def test_override_and_off(self):
        code, out = term.term_focus(SID, [dict(self.ROW)], cfg="apple")
        self.assertEqual(self.run.calls[-1][2], term._SCRIPT_APPLE)
        code, out = term.term_focus(SID, [dict(self.ROW)], cfg="off")
        self.assertEqual((code, out["how"], out["cmd"]), (200, "off", "claude --resume " + SID))
        self.assertEqual(len(self.run.calls), 1)

    def test_unsupported_and_notfound(self):
        r = dict(self.ROW, term={"app": "other", "tty": "ttys003"})
        self.assertEqual(term.term_focus(SID, [r])[1]["how"], "unsupported")
        self.assertEqual(term.term_focus(SID, [dict(self.ROW, term=None)])[1]["how"], "unsupported")
        self.run.out = "notrunning\n"
        self.assertEqual(term.term_focus(SID, [dict(self.ROW)])[1]["how"], "notfound")
        self.run.out = ""
        self.assertEqual(term.term_focus(SID, [dict(self.ROW)])[1]["how"], "error")

    def test_rejects_not_visible_and_bad_tty_as_notfound(self):
        # 200 + notfound: the page showed every 400 here as a permission problem
        self.assertEqual(term.term_focus(SID, []), (200, {"ok": False, "how": "notfound", "cmd": "claude --resume " + SID,
                                                          "err": "session not live on screen"}))
        self.assertEqual(term.term_focus(SID, [dict(self.ROW, state="done")])[1]["how"], "notfound")
        for bad in ("../x", "ttys003; rm", "console", "ttys12345"):
            self.assertEqual(term.term_focus(SID, [dict(self.ROW, term={"app": "iterm", "tty": bad})])[1]["how"], "notfound")
        self.assertEqual(self.run.calls, [])

    def test_timeout_is_not_error_and_logged(self):
        def slow(*a, **k):
            raise term.subprocess.TimeoutExpired("osascript", 5)
        self.patch(term.subprocess, "run", slow)
        out = term.term_focus(SID, [dict(self.ROW)])[1]
        self.assertEqual(out["how"], "timeout")
        term.term_focus(SID, [dict(self.ROW)])
        self.assertEqual([w[0] for w in self.warns], ["term-jump-timeout"] * 2)
        self.assertEqual(self.warns[-1][1]["n"], 2)                # count carried in the line

    def test_off_not_logged(self):
        term.term_focus(SID, [dict(self.ROW)], cfg="off")
        self.assertEqual(self.warns, [])

    def test_unresolved_row_reresolves_once(self):
        seen = []
        self.patch(term, "_resolve", lambda sid: seen.append(sid) or (True, {"app": "iterm", "tty": "ttys009"}))
        out = term.term_focus(SID, [dict(self.ROW, term=None)])[1]
        self.assertEqual((out["how"], seen, self.run.calls[-1][3]), ("focused", [SID], "/dev/ttys009"))
        self.patch(term, "_resolve", lambda sid: (False, None))
        self.assertEqual(term.term_focus(SID, [dict(self.ROW, term=None)])[1]["how"], "notfound")

    def test_resolve_forces_probe_past_fail_cache(self):
        self.patch(term, "_resolve", Focus._real_resolve)
        self.patch(term, "agent_view", lambda: {"101": {"sessionId": SID}})
        self.patch(term, "_ps_snap", lambda: [])
        self.patch(term, "_TTY_CACHE", {})
        self.patch(term, "_TTY_FAIL", [9e18])                     # poll path is blocked
        self.run.out = lambda argv: "101 ttys007 claude TERM_PROGRAM=iTerm.app\n" if argv[0] == "ps" else "ok\n"
        self.assertEqual(term.term_focus(SID, [dict(self.ROW, term=None)])[1]["how"], "focused")
        self.assertEqual(self.run.calls[-1][3], "/dev/ttys007")


class Orca(Base):
    ENV = "claude TERM_PROGRAM=Orca ORCA_TERMINAL_HANDLE=term_a1-B2.c3 ORCA_TAB_ID=t1"
    ROW = {"sid": SID, "state": "wait", "term": {"app": "orca", "tty": "ttys004"}}

    def setUp(self):
        self.patch(term, "IS_MAC", True)
        self.patch(term, "term_cfg", lambda: "auto")
        self.patch(term, "_av_cache", [0.0, {"101": {"sessionId": SID}}])
        self.patch(term, "_ps_snap_cache", [0.0, []])
        self.patch(term, "_TTY_CACHE", {"101": (9e18, "ttys004", "orca", "term_a1-B2.c3")})
        self.patch(term, "_TTY_FAIL", [0.0])
        self.patch(term, "_JUMP_FAILS", {})
        self.patch(term, "warn_once", lambda *a, **k: None)
        self.patch(term.shutil, "which", lambda n, path=None: "/opt/homebrew/bin/orca" if n == "orca" else None)

    def fake(self, by_verb):
        calls = []

        def run(argv, **kw):
            calls.append(argv)
            rc, out = by_verb.get(argv[2] if argv[0] != "open" else "open", (0, ""))
            return type("R", (), {"returncode": rc, "stdout": out, "stderr": ""})()
        self.patch(term.subprocess, "run", run)
        return calls

    def test_detect_and_bad_handle(self):
        self.assertEqual(term.app_of_env(self.ENV), "orca")
        self.assertEqual(term.orca_handle_of_env(self.ENV), "term_a1-B2.c3")
        for bad in ("-rf", "a;b", "x" * 200, ""):
            self.assertIsNone(term.orca_handle_of_env("TERM_PROGRAM=Orca ORCA_TERMINAL_HANDLE=" + bad))

    def test_attach_keeps_handle_server_side(self):
        self.patch(term, "_TTY_CACHE", {})
        self.patch(term.subprocess, "run", _Run("101 ttys004 " + self.ENV + "\n"))
        rows = [{"sid": SID, "state": "wait"}]
        term.term_attach(rows)
        self.assertEqual(rows[0]["term"], {"app": "orca", "tty": "ttys004"})
        self.assertNotIn("term_a1", json.dumps(rows))
        self.assertEqual(term._orca_handle(SID), "term_a1-B2.c3")

    def test_switch_argv(self):
        calls = self.fake({})
        code, out = term.term_focus(SID, [dict(self.ROW)])
        self.assertEqual(out["how"], "focused")
        self.assertEqual(calls, [["/opt/homebrew/bin/orca", "terminal", "switch", "--terminal", "term_a1-B2.c3"]])

    def test_old_cli_falls_back_to_focus(self):
        calls = self.fake({"switch": (1, "error: unknown command 'switch'")})
        self.assertEqual(term.term_focus(SID, [dict(self.ROW)])[1]["how"], "focused")
        self.assertEqual([c[2] for c in calls], ["switch", "focus"])

    def test_stale_handle_app_only(self):
        calls = self.fake({"switch": (1, "terminal handle not found")})
        out = term.term_focus(SID, [dict(self.ROW)])[1]
        self.assertEqual((out["how"], out["hint"], out["cmd"]), ("app", "handle", "claude --resume " + SID))
        self.assertEqual(calls[-1], ["open", "-b", "com.stablyai.orca"])

    def test_missing_cli_app_fallback(self):
        self.patch(term.shutil, "which", lambda n, path=None: None)
        calls = self.fake({})
        out = term.term_focus(SID, [dict(self.ROW)])[1]
        self.assertEqual((out["how"], out["hint"]), ("app", "cli"))
        self.assertEqual(calls, [["open", "-b", "com.stablyai.orca"]])

    def test_non_mac_without_cli_unsupported(self):
        self.patch(term, "IS_MAC", False)
        self.patch(term.shutil, "which", lambda n, path=None: None)
        calls = self.fake({})
        self.assertEqual(term.term_focus(SID, [dict(self.ROW)])[1]["how"], "unsupported")
        self.assertEqual(calls, [])

    def test_linux_binary_name(self):
        self.patch(term.shutil, "which", lambda n, path=None: "/usr/bin/orca-ide" if n == "orca-ide" else None)
        calls = self.fake({})
        term.term_focus(SID, [dict(self.ROW)])
        self.assertEqual(calls[0][0], "/usr/bin/orca-ide")


class Setting(Base):
    def test_orca_accepted(self):
        store = {}
        self.patch(term, "_save_json", lambda n, d: store.__setitem__(n, d))
        self.patch(term, "_load", lambda n, d: store.get(n, d))
        self.assertEqual(term.term_set({"termApp": "orca"}), (200, {"ok": True, "termApp": "orca"}))
        self.assertEqual(term.term_cfg(), "orca")

    def test_cfg_roundtrip(self):
        store = {}
        self.patch(term, "_save_json", lambda n, d: store.__setitem__(n, d))
        self.patch(term, "_load", lambda n, d: store.get(n, d))
        self.assertEqual(term.term_cfg(), "auto")
        self.assertEqual(term.term_set({"termApp": "iterm"}), (200, {"ok": True, "termApp": "iterm"}))
        self.assertEqual(term.term_cfg(), "iterm")
        self.assertEqual(term.term_set({"termApp": "bash"})[0], 400)
        self.assertEqual(term.term_set(["iterm"])[0], 400)
        store[term.TERM_CFG_FILE] = {"termApp": "zzz"}
        self.assertEqual(term.term_cfg(), "auto")


class Route(Base):
    def post(self, path, body):
        cs = load()
        h = cs.Handler.__new__(cs.Handler)
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        h.headers = {"Content-Length": str(len(raw))}
        h.rfile = io.BytesIO(raw)
        got = {}
        h._send = lambda code, b, ct: got.update(code=code, body=json.loads(b))
        cs.Handler._POST_ROUTES[path](h, None)
        return got["code"], got["body"]

    def test_bad_sid_400(self):
        rp = sidereus("routes_post")
        self.patch(rp, "term_focus", lambda *a: self.fail("must not reach focus"))
        for b in ({"sid": "../../x"}, {"sid": 5}, {}, ["x"], b"x" * 600):
            self.assertEqual(self.post("/api/term/focus", b)[0], 400)

    def test_focus_uses_server_rows(self):
        rp = sidereus("routes_post")
        seen = []
        self.patch(rp, "sessions_rows", lambda **k: [{"sid": SID}])
        self.patch(rp, "term_focus", lambda sid, rows: seen.append((sid, rows)) or (200, {"ok": True}))
        self.assertEqual(self.post("/api/term/focus", {"sid": SID, "tty": "ttys001"})[0], 200)
        self.assertEqual(seen, [(SID, [{"sid": SID}])])

    def test_set_route(self):
        rp = sidereus("routes_post")
        self.patch(rp, "term_set", lambda req: (200, {"ok": True, "termApp": req["termApp"]}))
        self.assertEqual(self.post("/api/term/set", {"termApp": "off"}), (200, {"ok": True, "termApp": "off"}))


if __name__ == "__main__":
    unittest.main()
