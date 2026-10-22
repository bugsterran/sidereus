"""ext-hooks/codex_wake.py: fake app-server daemon (WebSocket over a unix socket), temp store, injected clock."""
import base64
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("codex_wake_t", os.path.join(ROOT, "ext-hooks", "codex_wake.py"))
cw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cw)
SID = "01a15274-e17e-7170-8917-f810882056d1"


class FakeDaemon(object):
    """Accepts any number of connections; records (method, params) and whether each client frame was masked."""

    def __init__(self, path, loaded, status="idle"):
        self.loaded, self.status, self.calls, self.unmasked, self.handshakes = loaded, status, [], 0, 0
        self.srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.srv.bind(path)
        os.chmod(path, 0o600)
        self.srv.listen(8)
        self.t = threading.Thread(target=self.loop, daemon=True)
        self.t.start()

    def loop(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self.conn, args=(c,), daemon=True).start()

    def conn(self, c):
        buf = b""
        try:
            while b"\r\n\r\n" not in buf:
                buf += c.recv(4096)
            head, buf = buf.split(b"\r\n\r\n", 1)
            key = [ln.split(b":", 1)[1].strip() for ln in head.split(b"\r\n") if ln.lower().startswith(b"sec-websocket-key")][0]
            # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1 -- RFC 6455 mandates SHA-1 here
            acc = base64.b64encode(hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11", usedforsecurity=False).digest())  # nosec B324
            c.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      b"Sec-WebSocket-Accept: " + acc + b"\r\n\r\n")
            self.handshakes += 1
            while True:
                while len(buf) < 2:
                    d = c.recv(65536)
                    if not d:
                        return
                    buf += d
                b1 = buf[1]
                n, o = b1 & 0x7F, 2
                if n == 126:
                    n, o = struct.unpack(">H", buf[2:4])[0], 4
                if not b1 & 0x80:
                    self.unmasked += 1
                while len(buf) < o + 4 + n:
                    buf += c.recv(65536)
                m, p, buf = buf[o:o + 4], buf[o + 4:o + 4 + n], buf[o + 4 + n:]
                msg = json.loads(bytes(b ^ m[i % 4] for i, b in enumerate(p)).decode("utf-8"))
                self.calls.append((msg["method"], msg.get("params")))
                if "id" not in msg:
                    continue
                self.send(c, {"jsonrpc": "2.0", "method": "noise", "params": {}})   # a notification first
                self.send(c, {"jsonrpc": "2.0", "id": msg["id"], "result": self.result(msg["method"])})
        except (OSError, IndexError, ValueError):
            return
        finally:
            c.close()

    def result(self, method):
        if method == "thread/loaded/list":
            return {"data": self.loaded, "nextCursor": None}
        if method == "thread/resume":
            return {"thread": {"id": SID, "status": {"type": self.status}, "canAcceptDirectInput": True}}
        return {}

    @staticmethod
    def send(c, obj):
        d = json.dumps(obj).encode("utf-8")
        h = bytes([0x81, len(d)]) if len(d) < 126 else bytes([0x81, 126]) + struct.pack(">H", len(d))
        c.sendall(h + d)

    def close(self):
        self.srv.close()

    def methods(self):
        return [m for m, _ in self.calls if m != "noise"]


# The app-server daemon socket (/tmp/codex-daemon-<uid>, AF_UNIX) exists only on macOS/Linux.
@unittest.skipIf(sys.platform == "win32" or not hasattr(socket, "AF_UNIX"), "codex_wake uses a POSIX unix socket")
class CodexWake(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cwd = os.path.realpath(tempfile.mkdtemp())
        self.sd = tempfile.mkdtemp(dir="/tmp")  # nosec B108 -- ⚠short path: AF_UNIX is limited to 104 bytes on macOS
        self.me = os.path.basename(self.cwd) + "-codex"
        with open(os.path.join(self.d, "identity.json"), "w", encoding="utf-8") as f:
            json.dump({self.cwd: "claude-a"}, f)
        open(os.path.join(self.d, "bus.jsonl"), "w", encoding="utf-8").close()
        self.tp = os.path.join(self.d, "rollout.jsonl")
        self.meta("codex-tui", "cli")
        self.old = (cw.SOCK_DIR, cw.LOG, cw.FIRST_S)
        cw.SOCK_DIR, cw.LOG = self.sd, os.path.join(self.d, "wake.log")
        self._env = os.environ.pop("SIDEREUS_MAIL_WAIT_MAX", None)
        self.daemon = None

    def tearDown(self):
        cw.SOCK_DIR, cw.LOG, cw.FIRST_S = self.old
        cw.gms.set_platform("gemini")
        os.environ.pop("SIDEREUS_MAIL_WAIT_MAX", None)
        if self._env is not None:
            os.environ["SIDEREUS_MAIL_WAIT_MAX"] = self._env
        if self.daemon:
            self.daemon.close()
        for p in (self.d, self.cwd, self.sd):
            shutil.rmtree(p, ignore_errors=True)

    def meta(self, originator, source):
        with open(self.tp, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "session_meta", "payload": {"id": SID, "originator": originator,
                                                                    "source": source}}) + "\n")

    def serve(self, loaded=(SID,), status="idle"):
        self.daemon = FakeDaemon(os.path.join(self.sd, "d"), list(loaded), status)
        return self.daemon

    def dm(self):
        with open(os.path.join(self.d, "bus.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": "m%d" % time.time_ns(), "t": time.time_ns(), "from": "zed", "to": self.me,
                                "subject": "SECRET-SUBJ", "body": "SECRET-BODY"}) + "\n")

    def grow(self):
        with open(self.tp, "a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "response_item", "payload": {"type": "message", "role": "user"}}) + "\n")
        os.utime(self.tp, ns=(time.time_ns(), time.time_ns() + 10 ** 9))

    def run_cw(self, on_sleep=None, life=60):
        clk = {"t": 0.0, "n": 0}

        def sleep(s):
            clk["n"] += 1
            clk["t"] += max(s, 0.5)
            if on_sleep:
                on_sleep(clk["n"])
        old = cw.LIFE_S
        cw.LIFE_S = life
        try:
            return cw.run(SID, self.cwd, self.tp, self.me, store=self.d, sleep=sleep, clock=lambda: clk["t"])
        finally:
            cw.LIFE_S = old

    def lock_left(self):
        return os.path.exists(os.path.join(self.d, ".wake", SID + ".lock"))

    def wake_n(self):
        st = cw.ms.load(cw.ms.state_path(self.d, "codex:" + SID), {})
        return int(st.get("wake_n") or 0)

    def test_R1_fires_turn_in_rpc_order(self):
        d = self.serve()
        self.assertEqual(self.run_cw(on_sleep=lambda n: self.dm() if n == 3 else None), "fired")
        self.assertEqual(d.methods(), ["initialize", "initialized", "thread/loaded/list",
                                       "initialize", "initialized", "thread/loaded/list", "thread/resume",
                                       "turn/start"])
        self.assertEqual(d.unmasked, 0)
        self.assertEqual(d.handshakes, 2)
        self.assertTrue(d.calls[0][1]["capabilities"]["experimentalApi"])
        p = d.calls[-1][1]
        self.assertEqual(p["threadId"], SID)
        text = p["input"][0]["text"]
        self.assertEqual((p["input"][0]["type"], p["input"][0]["text_elements"]), ("text", []))
        self.assertTrue(text.startswith("[mailbox]"))
        self.assertTrue(text.startswith(cw.gms.MACHINE_PROMPTS))
        self.assertIn("`%s`" % self.me, text)
        self.assertNotIn("SECRET", json.dumps(d.calls))
        self.assertFalse(self.lock_left())
        self.assertEqual(self.wake_n(), 1)
        self.assertIsNone(self.decide())                   # delivered: surfaced once

    def decide(self):
        cw.gms.T0 = time.monotonic()
        return cw.gms.decide({"session_id": SID, "cwd": self.cwd}, store=self.d)

    def test_R3_no_socket_is_silent(self):
        self.assertEqual(self.run_cw(on_sleep=lambda n: self.dm()), "not-loaded")
        self.assertFalse(self.lock_left())
        cw.SOCK_DIR = os.path.join(self.sd, "missing")
        self.assertEqual(self.run_cw(), "not-loaded")

    def test_R3_not_loaded_is_silent(self):
        d = self.serve(loaded=["other"])
        self.assertEqual(self.run_cw(on_sleep=lambda n: self.dm()), "not-loaded")
        self.assertNotIn("turn/start", d.methods())
        self.assertFalse(self.lock_left())

    def test_R2_active_thread_no_turn(self):
        d = self.serve(status="active")
        self.assertEqual(self.run_cw(on_sleep=lambda n: self.dm() if n == 2 else None), "rejected")
        self.assertIn("thread/resume", d.methods())
        self.assertNotIn("turn/start", d.methods())
        self.assertFalse(self.lock_left())
        self.assertEqual(self.wake_n(), 0)
        self.assertIn("1 new mail", self.decide())         # not delivered: the next Stop still shows it

    def test_R3_thread_unloaded_at_fire_no_turn(self):
        d = self.serve()

        def on(n):
            if n == 2:
                d.loaded = []                              # TUI quit after spawn
            if n == 3:
                self.dm()
        self.assertEqual(self.run_cw(on_sleep=on), "rejected")
        self.assertNotIn("thread/resume", d.methods())
        self.assertNotIn("turn/start", d.methods())
        self.assertFalse(self.lock_left())
        self.assertIsNotNone(self.decide())

    def test_R3_thread_unloaded_while_waiting_exits(self):
        d = self.serve()

        def on(n):
            if n == 2:
                d.loaded = []
        self.assertEqual(self.run_cw(on_sleep=on, life=600), "gone")
        self.assertEqual(d.methods().count("thread/loaded/list"), 2)
        self.assertNotIn("thread/resume", d.methods())
        self.assertFalse(self.lock_left())

    def test_R3_untrusted_socket_dir_is_ignored(self):
        d = self.serve()
        # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions -- mode under test
        os.chmod(self.sd, 0o777)  # nosec B103 -- deliberately world-writable to test rejection
        self.assertEqual(self.run_cw(on_sleep=lambda n: self.dm()), "not-loaded")
        # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions -- restores owner-only
        os.chmod(self.sd, 0o700)
        link = self.sd + "-link"
        os.symlink(self.sd, link)
        try:
            cw.SOCK_DIR = link
            self.assertEqual(self.run_cw(on_sleep=lambda n: self.dm()), "not-loaded")
        finally:
            os.remove(link)
        self.assertEqual(d.methods(), [])

    def test_R2_typed_before_mail_no_turn(self):
        d = self.serve()

        def on(n):
            if n == 2:
                self.grow()
            if n == 4:
                self.dm()
        self.assertEqual(self.run_cw(on_sleep=on), "typed")
        self.assertEqual(d.methods(), ["initialize", "initialized", "thread/loaded/list"])
        self.assertFalse(self.lock_left())

    def test_second_waiter_is_busy(self):
        # ⚠Same-pid waiters share the slot (the lock holds a pid), so the first waiter is a live lock from another pid.
        d = self.serve()
        lp = cw.mw.lock_path(self.d, SID)
        os.makedirs(os.path.dirname(lp))
        with open(lp, "w", encoding="utf-8") as f:
            f.write(str(os.getpid() + 1))
        self.assertEqual(self.run_cw(on_sleep=lambda n: self.dm()), "busy")
        self.assertNotIn("turn/start", d.methods())
        self.assertTrue(self.lock_left())                  # the other waiter's lock is untouched

    def test_R3_exec_rollout_is_silent(self):
        d = self.serve()
        self.meta("codex_exec", "exec")
        self.assertEqual(self.run_cw(on_sleep=lambda n: self.dm()), "exec")
        self.assertEqual(d.methods(), [])

    def test_cap_stops_turns(self):
        os.environ["SIDEREUS_MAIL_WAIT_MAX"] = "1"
        d = self.serve()
        self.assertEqual(self.run_cw(on_sleep=lambda n: self.dm() if n == 2 else None), "fired")
        self.assertEqual(self.wake_n(), 1)
        self.assertEqual(self.run_cw(on_sleep=lambda n: self.dm() if n == 2 else None), "cap")
        self.assertEqual(d.methods().count("turn/start"), 1)

    def test_bad_args_and_errors_never_raise(self):
        self.assertEqual(cw.run("../x", self.cwd, self.tp, self.me, store=self.d), "bad-args")
        self.assertEqual(cw.run("", "", "", ""), "bad-args")


if __name__ == "__main__":
    unittest.main()
