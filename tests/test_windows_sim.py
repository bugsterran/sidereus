"""Windows simulation: a child python loads chat_server with POSIX-only modules removed and serves /api/state."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

from tests._load import ROOT

PY = sys.executable                # the runner's python, so a CI version matrix covers the child too

# ⚠Runs in a child: sys.platform / sys.modules edits must not leak into the other tests.
CHILD = textwrap.dedent(r'''
    import importlib.util, json, os, sys, types, threading
    import subprocess, socket, http.server, http.client, ctypes   # pre-import before POSIX modules vanish
    ROOT = sys.argv[1]
    for m in ("fcntl", "pwd", "grp", "termios", "resource"):
        sys.modules[m] = None
    del os.getuid
    sys.platform = "win32"
    os.name = "nt"                 # ⚠after the pre-imports: os.path stays posixpath, only `os.name == "nt"` branches flip
    def _nope(*a, **k):
        raise FileNotFoundError("no such program (simulated Windows)")
    subprocess.run = _nope
    subprocess.Popen = _nope
    sys.argv = ["chat_server.py"]
    sys.path.insert(0, ROOT)
    spec = importlib.util.spec_from_file_location("cs", os.path.join(ROOT, "chat_server.py"))
    cs = importlib.util.module_from_spec(spec); sys.modules["cs"] = cs
    spec.loader.exec_module(cs)
    import sidereus.config as cfg
    out = {"is_mac": cfg.IS_MAC, "is_win": cfg.IS_WIN}

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), cs.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    # ⚠plain http.client: urlopen's opener builds HTTPSHandler/ProxyHandler, which reach for win32-only ssl/proxy APIs on 3.12+.
    def _get(path):
        c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=60)
        c.request("GET", path, headers={"Host": "127.0.0.1:%d" % cfg.PORT})   # _host_ok compares against the configured port
        r = c.getresponse(); body = r.read(); c.close()
        return r.status, body
    code, body = _get("/api/state")
    out["code"] = code
    out["json"] = isinstance(json.loads(body.decode("utf-8")), dict)
    code, body = _get("/")
    out["page"] = [code, len(body)]
    srv.shutdown()

    import glob, importlib
    bad = []
    for f in sorted(glob.glob(os.path.join(ROOT, "sidereus", "*.py"))) + ["sidereus_cli"]:
        name = f if f == "sidereus_cli" else "sidereus." + os.path.basename(f)[:-3]
        if name in ("sidereus.__main__",):
            continue                   # runs sidereus_cli.main() on import
        try:
            importlib.import_module(name)
        except Exception as e:
            bad.append("%s: %s: %s" % (name, type(e).__name__, e))
    out["import_bad"] = bad

    import sidereus.live_win as lw
    lw._scan_windows()                 # empty HOME: must not raise on a Windows-shaped run

    import sidereus.awake as aw
    sets = []
    aw.IS_WIN, aw.IS_MAC, aw._win_held = True, False, [False]
    ctypes.windll = types.SimpleNamespace(kernel32=types.SimpleNamespace(
        SetThreadExecutionState=lambda f: sets.append(f) or 1))
    aw._awake_apply(True); held_on = aw._awake_held()
    aw._awake_apply(False); held_off = aw._awake_held()
    out["awake"] = [sets, held_on, held_off]

    import sidereus_cli as cli
    seen = {}
    class _P:
        pid = 4242
    def _fake_popen(argv, **kw):
        seen.update(kw); return _P()
    cli.IS_WIN, cli._Popen = True, _fake_popen
    cli.data_dir = lambda: os.environ["MAILBOX_DIR"]
    cli.spawn(cfg.PORT)
    out["spawn"] = {"flags": seen.get("creationflags"), "want": cli.WIN_SPAWN_FLAGS,
                    "utf8": (seen.get("env") or {}).get("PYTHONUTF8"), "sns": "start_new_session" in seen}

    import sidereus.ident as idn
    old_sep = os.pathsep
    try:
        os.pathsep = ";"
        idn.IS_WIN, idn.IS_MAC, idn._BIN_DIRS = True, False, ()   # ⚠_BIN_DIRS is built at import
        idn.node_dir = lambda: ""
        os.environ["PATH"] = "C:\\x;C:\\y"
        out["path"] = idn.rich_env()["PATH"]
    finally:
        os.pathsep = old_sep

    calls = []
    ms = types.ModuleType("msvcrt"); ms.LK_LOCK = 1; ms.LK_UNLCK = 0
    ms.locking = lambda fd, mode, n: calls.append((mode, n))
    sys.modules["msvcrt"] = ms
    with cfg.file_lock(os.path.join(os.environ["MAILBOX_DIR"], "x.lock")):
        calls.append("body")
    out["lock"] = calls

    class K32:
        err = 0
        def OpenProcess(self, access, inherit, pid):
            out.setdefault("access", access)
            if pid == 111: return 7
            K32.err = 5 if pid == 222 else 87
            return 0
        def GetLastError(self): return K32.err
        def CloseHandle(self, h): out["closed"] = h
    ctypes.windll = types.SimpleNamespace(kernel32=K32())
    out["pids"] = [cfg.pid_alive(111), cfg.pid_alive(222), cfg.pid_alive(333), cfg.pid_alive(0)]
    print("RESULT " + json.dumps(out), flush=True)
    os._exit(0)
''')


class WindowsSim(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-winsim-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_loads_and_serves_state(self):
        env = dict(os.environ, MAILBOX_DIR=self.tmp, HOME=self.tmp, SIDEREUS_HOOK_NO_PID="1",
                   CODEX_HOME=os.path.join(os.devnull, "no-codex-home"))
        env.pop("MAILBOX_CONFIG", None)
        p = subprocess.run([PY, "-c", CHILD, ROOT], env=env, cwd=self.tmp,
                           capture_output=True, text=True, timeout=120)
        line = [x for x in p.stdout.splitlines() if x.startswith("RESULT ")]
        self.assertTrue(line, "child failed:\n" + p.stderr[-3000:])
        out = json.loads(line[-1][7:])
        self.assertFalse(out["is_mac"])
        self.assertTrue(out["is_win"])
        self.assertEqual(out["code"], 200)
        self.assertTrue(out["json"])
        self.assertEqual(out["lock"], [[1, 1], "body", [0, 1]])
        self.assertEqual(out["access"], 0x00100000)
        self.assertEqual(out["closed"], 7)
        self.assertEqual(out["pids"], [True, True, False, None])
        self.assertEqual(out["page"][0], 200)
        self.assertGreater(out["page"][1], 0)
        self.assertEqual(out["import_bad"], [])
        self.assertEqual(out["awake"], [[0x80000001, 0x80000000], True, False])
        sp = out["spawn"]
        self.assertEqual(sp["flags"], 0x08000000 | 0x00000200)
        self.assertEqual(sp["flags"], sp["want"])
        self.assertEqual(sp["flags"] & 0x8, 0)          # DETACHED_PROCESS must stay off
        self.assertEqual(sp["utf8"], "1")
        self.assertFalse(sp["sns"])
        self.assertEqual(out["path"], "C:\\x;C:\\y")
        self.assertEqual(out["path"].split(";"), ["C:\\x", "C:\\y"])


if __name__ == "__main__":
    unittest.main()
