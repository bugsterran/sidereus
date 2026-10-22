#!/usr/bin/env python3
"""Detached Codex mail waiter: start one «[mailbox]» turn in an idle Codex TUI session through the app-server daemon.

Spawned by `gemini_mail_stop.py --platform codex --wake` at turn end (argv: session_id cwd transcript_path me).
hooks/mail_wait.py WAKE["codex"] == "app-server-turn".
Flow:
- Pre-check (before the waiter slot): find the daemon sockets in /tmp/codex-daemon-<uid>/ (owner uid, no group/other
  bits), connect, initialize{experimentalApi} → initialized → thread/loaded/list. The session must be loaded on one.
  No daemon, not loaded (e.g. a TUI not attached to the daemon) or any error = silent exit 0.
- Wait: hooks/mail_wait.wait (bus.jsonl stat, LIFE_S). check() first compares the rollout's (size, mtime) with the
  snapshot from the first check; a change means the person typed (or a turn ran) and the waiter exits. Every
  RECHECK_S it re-runs thread/loaded/list and exits once the thread is gone (TUI quit).
- Fire: thread/loaded/list → thread/resume → only if still loaded, status idle, canAcceptDirectInput is not false
  and the rollout is unchanged, turn/start with decide()'s reason line; only then mark the mail surfaced (last_t)
  and bump wake_n. Exit without waiting for the turn.
Rules:
- ⚠The prompt is decide()'s reason only (ids, room names, a count): never a subject or body. It starts with
  "[mailbox]" so gemini_mail_stop.human_key() does not count it as a human prompt; SIDEREUS_MAIL_WAIT_MAX caps loops.
- ⚠Never prints, never raises: errors go (type and step only) to ext-hooks/.codex-wake.log, capped at LOG_MAX.
- ⚠The snapshot is taken at the first check (after FIRST_S), not at spawn: Codex still appends turn-end rows
  after the Stop hook returns, which would read as typing.
- ⚠AF_UNIX paths are limited to 104 bytes on macOS; a longer socket path fails to connect and is skipped.
- Protocol: WebSocket over AF_UNIX (HTTP Upgrade, masked client text frames, one JSON-RPC message per frame).
"""
import base64
import hashlib
import json
import os
import socket
import stat
import struct
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "hooks"))
sys.path.insert(0, _HERE)
import mailbox_stop as ms  # noqa: E402
import mail_wait as mw  # noqa: E402
import gemini_mail_stop as gms  # noqa: E402

SOCK_DIR = None            # None = /tmp/codex-daemon-<uid>; tests point it at a temp dir
LIFE_S = 6 * 3600
FIRST_S = 3.0
RPC_TIMEOUT_S = 10.0
RECHECK_S = 60.0           # re-check thread/loaded/list while waiting: a quit TUI must not get a headless turn
FRAME_MAX = 16 * 1024 * 1024
LOG = os.path.join(_HERE, ".codex-wake.log")
LOG_MAX = 64 * 1024
CLIENT = {"name": "sidereus_mail_wake", "version": "1"}
_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def log(step, err=None):
    try:
        if os.path.getsize(LOG) > LOG_MAX:
            os.remove(LOG)
    except OSError:
        pass
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%d %s %s\n" % (int(time.time()), step, type(err).__name__ if err is not None else ""))
    except OSError:
        pass


def sock_dir():
    if SOCK_DIR:
        return SOCK_DIR
    uid = getattr(os, "getuid", None)
    # ⚠ Codex's own fixed socket dir; not $TMPDIR (macOS points that elsewhere), and sockets() checks owner + mode.
    return "/tmp/codex-daemon-%d" % uid() if uid else ""  # nosec B108


def sockets():
    """Daemon socket paths owned by this uid with no group/other access, sorted."""
    d = sock_dir()
    uid = os.getuid() if hasattr(os, "getuid") else -1
    out = []
    try:
        dst = os.lstat(d)
        # ⚠/tmp is shared: trust only a real dir owned by us that nobody else can write into.
        if not stat.S_ISDIR(dst.st_mode) or dst.st_uid != uid or dst.st_mode & 0o022:
            return out
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for n in names:
        p = os.path.join(d, n)
        try:
            st = os.lstat(p)
        except OSError:
            continue
        if stat.S_ISSOCK(st.st_mode) and st.st_uid == uid and not st.st_mode & 0o077:
            out.append(p)
    return out


class WS(object):
    """Minimal WebSocket client over a unix socket: masked text frames out, JSON-RPC calls by id."""

    def __init__(self, path, timeout=RPC_TIMEOUT_S):
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.s.settimeout(timeout)
        self.s.connect(path)
        self.buf = b""
        self.nid = 0
        self.deadline = time.monotonic() + timeout
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        self.s.sendall(("GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % key).encode("ascii"))
        while b"\r\n\r\n" not in self.buf:
            self._more()
            if len(self.buf) > 65536:
                raise ValueError("handshake")
        head, self.buf = self.buf.split(b"\r\n\r\n", 1)
        lines = head.decode("latin-1").split("\r\n")
        if " 101 " not in lines[0] + " ":
            raise ValueError("handshake")
        # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1 -- RFC 6455 mandates SHA-1 here
        want = base64.b64encode(hashlib.sha1((key + _GUID).encode("ascii"), usedforsecurity=False).digest()).decode("ascii")  # nosec B324
        acc = [ln.split(":", 1)[1].strip() for ln in lines[1:] if ln.lower().startswith("sec-websocket-accept:")]
        if acc != [want]:
            raise ValueError("accept")

    def _more(self):
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise socket.timeout("deadline")
        self.s.settimeout(left)
        c = self.s.recv(65536)
        if not c:
            raise EOFError("closed")
        self.buf += c

    def _need(self, k):
        while len(self.buf) < k:
            self._more()

    def send_frame(self, op, data):
        m = os.urandom(4)
        n = len(data)
        h = bytes([0x80 | op])
        if n < 126:
            h += bytes([0x80 | n])
        elif n < 65536:
            h += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            h += bytes([0x80 | 127]) + struct.pack(">Q", n)
        self.s.sendall(h + m + bytes(b ^ m[i % 4] for i, b in enumerate(data)))

    def recv_frame(self):
        self._need(2)
        b0, b1 = self.buf[0], self.buf[1]
        n, o = b1 & 0x7F, 2
        if n == 126:
            self._need(4)
            n, o = struct.unpack(">H", self.buf[2:4])[0], 4
        elif n == 127:
            self._need(10)
            n, o = struct.unpack(">Q", self.buf[2:10])[0], 10
        if n > FRAME_MAX:
            raise ValueError("frame")
        mask = b""
        if b1 & 0x80:
            self._need(o + 4)
            mask, o = self.buf[o:o + 4], o + 4
        self._need(o + n)
        p, self.buf = self.buf[o:o + n], self.buf[o + n:]
        if mask:
            p = bytes(b ^ mask[i % 4] for i, b in enumerate(p))
        return b0 & 0x80, b0 & 0x0F, p

    def recv_msg(self):
        """Next complete text message; answers pings, raises on close."""
        parts = []
        while True:
            fin, op, p = self.recv_frame()
            if op == 9:
                self.send_frame(0xA, p)
                continue
            if op == 0xA:
                continue
            if op == 8:
                raise EOFError("close")
            parts.append(p)
            if sum(len(x) for x in parts) > FRAME_MAX:
                raise ValueError("frame")
            if fin:
                return b"".join(parts)

    def send(self, obj):
        self.send_frame(0x1, json.dumps(obj).encode("utf-8"))

    def call(self, method, params):
        """Result of one JSON-RPC request; notifications and server requests in between are skipped."""
        self.nid += 1
        rid = self.nid
        self.send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        self.deadline = time.monotonic() + RPC_TIMEOUT_S      # enforced per recv in _more()
        while True:
            o = json.loads(self.recv_msg().decode("utf-8"))
            if isinstance(o, dict) and o.get("id") == rid and "method" not in o:
                if "error" in o or not isinstance(o.get("result"), dict):
                    raise RuntimeError(method)
                return o["result"]

    def notify(self, method):
        self.send({"jsonrpc": "2.0", "method": method})

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass


def connect(path):
    ws = WS(path)
    try:
        ws.call("initialize", {"clientInfo": CLIENT, "capabilities": {"experimentalApi": True}})
        ws.notify("initialized")
    except Exception:
        ws.close()
        raise
    return ws


def is_loaded(ws, sid):
    """thread/loaded/list (paged) on an open connection contains sid."""
    cursor = None
    for _ in range(50):
        r = ws.call("thread/loaded/list", {"cursor": cursor} if cursor else {})
        if sid in (r.get("data") or []):
            return True
        cursor = r.get("nextCursor")
        if not cursor:
            return False
    return False


def still_loaded(path, sid):
    ws = None
    try:
        ws = connect(path)
        return is_loaded(ws, sid)
    except Exception as e:
        log("recheck", e)
        return False
    finally:
        if ws:
            ws.close()


def find_daemon(sid):
    """Socket path whose daemon has the thread loaded, else None."""
    for p in sockets():
        ws = None
        try:
            ws = connect(p)
            if is_loaded(ws, sid):
                return p
        except Exception as e:
            log("list", e)
        finally:
            if ws:
                ws.close()
    return None


def rollout_sig(tp):
    try:
        st = os.stat(tp)
        return (st.st_size, st.st_mtime_ns)
    except OSError:
        return None


def fire(path, sid, tp, snap, text):
    """thread/resume, then turn/start only on an idle thread with an unchanged rollout; True when started."""
    ws = connect(path)
    try:
        if not is_loaded(ws, sid):      # ⚠resume would load a closed thread and run a turn nobody sees
            return False
        th = ws.call("thread/resume", {"threadId": sid}).get("thread") or {}
        status = th.get("status") if isinstance(th, dict) else None
        if not isinstance(status, dict) or status.get("type") != "idle" or th.get("canAcceptDirectInput") is False:
            return False
        if rollout_sig(tp) != snap:
            return False
        ws.call("turn/start", {"threadId": sid, "input": [{"type": "text", "text": text, "text_elements": []}]})
        return True
    finally:
        ws.close()


def run(sid, cwd, tp, me, store=None, sleep=time.sleep, clock=time.monotonic):
    """Return a short outcome tag (for tests); never raises."""
    try:
        if not sid or not all(c.isalnum() or c in "-_" for c in sid) or not cwd or not tp or not me:
            return "bad-args"
        gms.set_platform("codex")
        store = store or ms.data_dir()
        inp = {"session_id": sid, "cwd": cwd, "transcript_path": tp}
        if not gms.interactive(inp):
            return "exec"
        n, cap, human = gms.wake_count(inp, store)
        if n >= cap:
            return "cap"
        path = find_daemon(sid)
        if not path:
            return "not-loaded"
        snap, hold, seen = [], {}, [clock()]

        def check():
            sig = rollout_sig(tp)
            if not snap:
                snap.append(sig)
            elif sig != snap[0]:
                return "typed"
            if clock() - seen[0] >= RECHECK_S:
                seen[0] = clock()
                if not still_loaded(path, sid):
                    return "gone"
            gms.T0 = time.monotonic()      # ⚠decide() gives up after BUDGET_S from T0
            hold.clear()
            # ⚠hold: the mail is marked surfaced only after turn/start succeeds, else the next Stop shows it.
            return gms.decide(inp, store=store, hold=hold)
        got, val = mw.wait(store, sid, me, check, LIFE_S, first_s=FIRST_S, sleep=sleep, clock=clock,
                           retry_s=mw.POLL_S)
        if got != "hit":
            return got
        if val in ("typed", "gone"):
            return val
        if not fire(path, sid, tp, snap[0], val):
            return "rejected"
        gms.mark_surfaced(ms.state_path(store, gms.KEY_PREFIX + sid), hold["newest"], hold["me"], hold["at"])
        gms.bump_wake(inp, store, n, human)
        return "fired"
    except Exception as e:
        log("run", e)
        return "error"


if __name__ == "__main__":
    a = sys.argv[1:] + [""] * 4
    run(a[0], a[1], a[2], a[3])
    sys.exit(0)
