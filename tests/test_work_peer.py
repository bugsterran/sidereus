"""Work-popup peer check (sidereus/peer.py) and its gate on the three work routes. lsof, pid, platform and clock are faked."""
import subprocess
import types
import unittest
from unittest import mock
from urllib.parse import urlparse

from tests._load import load, sidereus

load()
peer = sidereus("peer")
rg = sidereus("routes_get")

VPORT = 8799
CPORT = 51234
ME = 4242


def _run(stdout="", rc=0, calls=None):
    def run(argv, **kw):
        if calls is not None:
            calls.append(argv)
        return types.SimpleNamespace(returncode=rc, stdout=stdout, stderr="")
    return run


def _out(*pairs):
    lines = []
    for pid, name in pairs:
        lines += ["p%d" % pid, "f9", "n" + name]
    return "\n".join(lines) + "\n"


CLIENT = "127.0.0.1:%d->127.0.0.1:%d" % (CPORT, VPORT)
SERVER = "127.0.0.1:%d->127.0.0.1:%d" % (VPORT, CPORT)


class _Clock:
    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t


class PeerOk(unittest.TestCase):
    def setUp(self):
        self.clock = _Clock()
        self.calls = []
        peer._peer_memo.clear()
        self.p = [mock.patch.object(peer.config, "IS_MAC", True), mock.patch.object(peer.config, "PORT", VPORT),
                  mock.patch.object(peer.os, "getpid", lambda: ME), mock.patch.object(peer, "time", self.clock)]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        peer._peer_memo.clear()

    def _with(self, run):
        return mock.patch.object(peer.subprocess, "run", run)

    def test_other_pid_client_end_allows(self):
        with self._with(_run(_out((ME, SERVER), (777, CLIENT)), calls=self.calls)):
            self.assertTrue(peer.peer_ok(("127.0.0.1", CPORT)))
        self.assertEqual(self.calls[0][0], peer.LSOF)
        self.assertIn("-iTCP@127.0.0.1:%d" % CPORT, self.calls[0])

    def test_only_own_socket_refuses(self):
        with self._with(_run(_out((ME, SERVER), (ME, CLIENT)))):
            self.assertFalse(peer.peer_ok(("127.0.0.1", CPORT)))

    def test_other_pid_server_end_only_refuses(self):
        with self._with(_run(_out((777, SERVER)))):
            self.assertFalse(peer.peer_ok(("127.0.0.1", CPORT)))

    def test_empty_or_rc1_refuses(self):
        with self._with(_run("")):
            self.assertFalse(peer.peer_ok(("127.0.0.1", CPORT)))
        with self._with(_run(_out((777, CLIENT)), rc=1)):
            self.assertFalse(peer.peer_ok(("127.0.0.1", CPORT)))

    def test_exceptions_refuse(self):
        for exc in (subprocess.TimeoutExpired("lsof", 1.5), OSError("nope")):
            def run(argv, _e=exc, **kw):
                raise _e
            with self._with(run), mock.patch.object(peer, "warn_once", lambda *a, **kw: None):
                self.assertFalse(peer.peer_ok(("127.0.0.1", CPORT)))

    def test_timeout_twice_is_undetermined_not_cached(self):
        warns, timeouts = [], []

        def run(argv, timeout=None, **kw):
            timeouts.append(timeout)
            raise subprocess.TimeoutExpired("lsof", timeout)
        with self._with(run), mock.patch.object(peer, "warn_once", lambda *a, **kw: warns.append(a[0])):
            self.assertIsNone(peer.peer_state(("127.0.0.1", CPORT)))
        self.assertEqual(timeouts, list(peer.PEER_TIMEOUTS))
        self.assertEqual(warns, ["peer-slow"])
        self.assertNotIn(CPORT, peer._peer_memo)

    def test_timeout_then_success_allows(self):
        seq = [subprocess.TimeoutExpired("lsof", 1.5)]

        def run(argv, **kw):
            if seq:
                raise seq.pop()
            return _run(_out((777, CLIENT)))(argv)
        with self._with(run):
            self.assertIs(peer.peer_state(("127.0.0.1", CPORT)), True)

    def test_real_miss_is_false(self):
        for out, rc in (("", 0), (_out((777, SERVER)), 0), (_out((777, CLIENT)), 1)):
            with self.subTest(rc=rc), self._with(_run(out, rc=rc)):
                self.assertIs(peer.peer_state(("127.0.0.1", CPORT)), False)

    def test_ipv6_refuses_without_run(self):
        with self._with(_run(_out((777, CLIENT)), calls=self.calls)):
            self.assertFalse(peer.peer_ok(("::1", CPORT, 0, 0)))
        self.assertEqual(self.calls, [])

    def test_not_mac_allows_without_run(self):
        with mock.patch.object(peer.config, "IS_MAC", False), self._with(_run(calls=self.calls)):
            self.assertTrue(peer.peer_ok(("127.0.0.1", CPORT)))
        self.assertEqual(self.calls, [])

    def test_allow_cached_within_ttl(self):
        with self._with(_run(_out((777, CLIENT)), calls=self.calls)):
            self.assertTrue(peer.peer_ok(("127.0.0.1", CPORT)))
            self.clock.t += peer.PEER_TTL_S - 1
            self.assertTrue(peer.peer_ok(("127.0.0.1", CPORT)))
            self.assertEqual(len(self.calls), 1)
            self.clock.t += 2
            self.assertTrue(peer.peer_ok(("127.0.0.1", CPORT)))
            self.assertEqual(len(self.calls), 2)

    def test_refusal_not_cached(self):
        with self._with(_run("", calls=self.calls)):
            self.assertFalse(peer.peer_ok(("127.0.0.1", CPORT)))
            self.assertFalse(peer.peer_ok(("127.0.0.1", CPORT)))
        self.assertEqual(len(self.calls), 2)
        self.assertNotIn(CPORT, peer._peer_memo)


class _H:
    client_address = ("127.0.0.1", CPORT)
    _peer_refused = rg._GetRoutes._peer_refused

    def __init__(self):
        self.sent = None

    def _send(self, code, body, ctype, *a, **kw):
        self.sent = (code, body)

    def send_response(self, code):
        self.sent = (code, None)
        self.hdr = {}

    def send_header(self, k, v):
        self.hdr[k] = v

    def end_headers(self):
        pass

    @property
    def wfile(self):
        return self

    def write(self, b):
        self.sent = (self.sent[0], b)

    def _raw_json(self, code, out, *a, **kw):
        self.sent = (code, out)


ROUTES = (("_g_agent_work", "agent_work", "/api/agent/work?cwd=/w&tid=t"),
          ("_g_session_work", "session_work", "/api/session/work?cwd=/w&sid=s"),
          ("_g_ext_work", "ext_work", "/api/ext/work?plat=gm&sid=s"))


class Routes(unittest.TestCase):
    def _call(self, meth, fn, url, ok):
        calls = []
        with mock.patch.object(rg, "peer_state", lambda addr: ok), \
                mock.patch.object(rg, fn, lambda *a, **kw: calls.append(a) or {"ok": True}):
            h = _H()
            getattr(rg._GetRoutes, meth)(h, urlparse(url))
        return h.sent, calls

    def test_refused_peer_gets_403(self):
        for meth, fn, url in ROUTES:
            with self.subTest(meth):
                sent, calls = self._call(meth, fn, url, False)
                self.assertEqual(sent[0], 403)
                self.assertEqual(calls, [])

    def test_undetermined_peer_gets_503_retry(self):
        for meth, fn, url in ROUTES:
            with self.subTest(meth):
                sent, calls = self._call(meth, fn, url, None)
                self.assertEqual(sent[0], 503)
                self.assertNotIn(b"steps", sent[1])
                self.assertEqual(calls, [])

    def test_lsof_timeouts_reach_route_as_503(self):
        def run(argv, timeout=None, **kw):
            raise subprocess.TimeoutExpired("lsof", timeout)
        calls = []
        with mock.patch.object(peer.config, "IS_MAC", True), mock.patch.object(peer.subprocess, "run", run), \
                mock.patch.object(peer, "warn_once", lambda *a, **kw: None), \
                mock.patch.object(rg, "session_work", lambda *a, **kw: calls.append(a) or {"ok": True}):
            peer._peer_memo.clear()
            h = _H()
            rg._GetRoutes._g_session_work(h, urlparse(ROUTES[1][2]))
        self.assertEqual(h.sent[0], 503)
        self.assertEqual(h.hdr.get("Retry-After"), "2")
        self.assertEqual(calls, [])

    def test_allowed_peer_falls_through(self):
        for meth, fn, url in ROUTES:
            with self.subTest(meth):
                sent, calls = self._call(meth, fn, url, True)
                self.assertEqual(sent, (200, {"ok": True}))
                self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
