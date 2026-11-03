"""POST routes other than /api/say and /api/dm: malformed body, cross-origin, oversize length, happy path.

The Handler is driven without a socket (fake rfile/wfile/headers). Every file a route writes is redirected
to a temp dir, and the ingest/session hooks are stubbed in the module that routes_post imported them into.
"""
import http.client
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import load, sidereus

cs = load()
RP = sidereus("routes_post")
bus = sidereus("bus")
cards = sidereus("cards")
sv = sidereus("saver")
bt = sidereus("bgtasks")
bp = sidereus("bgtasks_parse")
live = sidereus("live")
wm = sidereus("warn")
PORT = cs.PORT
HOST = "127.0.0.1:%d" % PORT
EVIL = "http://evil.example"
OWN = "http://127.0.0.1:%d" % PORT
# Routes that act as the person or run a process: post() sends OWN by default; origin="" sends none.
VIEWER_ONLY = {"/api/say", "/api/dm", "/api/thread/close", "/api/term/focus", "/api/term/set", "/api/saver/set",
               "/api/cards/read", "/api/bg/dismiss", "/api/health/dismiss", "/api/review/mark"}


class _Rfile(io.BytesIO):
    """BytesIO that records whether the handler read the body."""
    reads = 0

    def read(self, *a):
        self.reads += 1
        return super().read(*a)


def post(path, body=b"", clen=None, origin=None, te=None):
    """Run do_POST on a socketless Handler; returns (status, parsed body or text, handler).
    `te` sends that Transfer-Encoding with no Content-Length."""
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode("utf-8")
    hdr = "Host: %s\r\nContent-Type: application/json\r\n" % HOST
    hdr += ("Transfer-Encoding: %s\r\n" % te) if te else \
        "Content-Length: %s\r\n" % (len(body) if clen is None else clen)
    if origin is None and path.split("?")[0] in VIEWER_ONLY:
        origin = OWN
    if origin:
        hdr += "Origin: %s\r\n" % origin
    h = cs.Handler.__new__(cs.Handler)
    h.headers = http.client.parse_headers(io.BytesIO((hdr + "\r\n").encode("latin-1")))
    h.rfile, h.wfile = _Rfile(body), io.BytesIO()
    h.path, h.command, h.request_version = path, "POST", "HTTP/1.1"
    h.requestline = "POST %s HTTP/1.1" % path
    h.close_connection = False
    h.client_address = ("127.0.0.1", 0)
    h.do_POST()
    raw = h.wfile.getvalue()
    head, _, payload = raw.partition(b"\r\n\r\n")
    code = int(head.split(b"\r\n", 1)[0].split()[1])
    try:
        out = json.loads(payload.decode("utf-8"))
    except ValueError:
        out = payload.decode("utf-8", "replace")
    return code, out, h


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-rp-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.warns = []
        self.patch(RP, "warn_once", lambda *a, **k: self.warns.append(a[0]))

    def patch(self, obj, name, val):
        p = mock.patch.object(obj, name, val)
        p.start()
        self.addCleanup(p.stop)

    def assertRefused(self, path, body=b"{}"):
        code, out, h = post(path, body, origin=EVIL)
        self.assertEqual(code, 403, path)
        self.assertIn("cross-origin", out)
        self.assertEqual(h.rfile.reads, 0, "refused POST must not read the body")
        self.assertTrue(h.close_connection)


class HookTest(_Base):
    def setUp(self):
        super().setUp()
        self.got = []
        self.patch(RP, "ext_ingest", lambda req: (self.got.append(req), (True, ""))[1])
        self.stat0 = dict(RP._ext_stat)
        self.addCleanup(RP._ext_stat.update, self.stat0)

    def test_malformed(self):
        code, out, _ = post("/api/hook", b"{not json")
        self.assertEqual((code, out), (400, {"ok": 0, "err": "bad request"}))
        self.assertEqual(self.got, [])
        self.assertEqual(RP._ext_stat["drop"], self.stat0["drop"] + 1)
        self.assertEqual(self.warns, ["ext-hook"])

    def test_empty_and_non_object(self):
        post("/api/hook", b"")
        post("/api/hook", b"[1, 2]")
        self.assertEqual(self.got, [{}, {}])

    def test_cross_origin(self):
        self.assertRefused("/api/hook")
        self.assertEqual(self.got, [])
        self.assertEqual(RP._ext_stat["posts"], self.stat0["posts"])

    def test_oversize(self):
        code, _, h = post("/api/hook", b"", clen=1_000_001)
        self.assertEqual(h.rfile.reads, 0)
        self.assertEqual(self.got, [{}])
        self.assertEqual(code, 200)       # stub accepts; the real ext_ingest({}) decides the verdict

    def test_happy(self):
        ev = {"src": "gemini", "event": "start", "sid": "s1"}
        code, out, _ = post("/api/hook", ev)
        self.assertEqual((code, out), (200, {"ok": 1}))
        self.assertEqual(self.got, [ev])
        self.assertEqual(RP._ext_stat["posts"], self.stat0["posts"] + 1)
        self.assertEqual(RP._ext_stat["kept"], self.stat0["kept"] + 1)

    def test_rejected_by_ingest(self):
        self.patch(RP, "ext_ingest", lambda req: (False, "no sid"))
        code, out, _ = post("/api/hook", {"x": 1})
        self.assertEqual((code, out), (400, {"ok": 0, "err": "no sid"}))


class OtelTest(_Base):
    def setUp(self):
        super().setUp()
        self.got = []
        self.patch(RP, "_otel_ingest", lambda d: (self.got.append(d), 1)[1])
        self.stat0 = dict(RP._otel_stat)
        self.addCleanup(RP._otel_stat.update, self.stat0)

    def test_malformed(self):
        code, out, _ = post("/v1/logs", b"\xff\xfe")
        self.assertEqual((code, out), (200, {}))    # telemetry always gets a quick 200
        self.assertEqual(self.got, [])
        self.assertEqual(self.warns, ["otel"])

    def test_empty(self):
        self.assertEqual(post("/v1/logs", b"")[0], 200)
        self.assertEqual(self.got, [{}])

    def test_cross_origin(self):
        self.assertRefused("/v1/logs")
        self.assertEqual(self.got, [])
        self.assertEqual(RP._otel_stat["posts"], self.stat0["posts"])

    def test_oversize(self):
        code, _, h = post("/v1/logs", b"", clen=8_000_001)
        self.assertEqual((code, h.rfile.reads), (200, 0))
        self.assertEqual(self.got, [{}])

    def test_happy_logs_and_metrics(self):
        doc = {"resourceLogs": []}
        self.assertEqual(post("/v1/logs", doc)[0], 200)
        self.assertEqual(post("/v1/metrics", doc)[0], 200)
        self.assertEqual(self.got, [doc])            # metrics are counted but not ingested
        self.assertEqual(RP._otel_stat["posts"], self.stat0["posts"] + 2)


class CardsReadTest(_Base):
    def setUp(self):
        super().setUp()
        self.ids = os.path.join(self.tmp, "ids.txt")
        self.mark = os.path.join(self.tmp, "mark.txt")
        self.patch(cards, "READ_IDS", self.ids)
        self.patch(cards, "READ_MARK", self.mark)

    def test_malformed_falls_back_to_all(self):
        code, out, _ = post("/api/cards/read", b"{bad")
        self.assertEqual(code, 200)
        self.assertIn("at", out)
        self.assertTrue(os.path.exists(self.mark))

    def test_empty_marks_all(self):
        code, out, _ = post("/api/cards/read", b"")
        self.assertEqual(code, 200)
        with open(self.mark, encoding="utf-8") as f:
            self.assertEqual(f.read(), out["at"])

    def test_cross_origin(self):
        self.assertRefused("/api/cards/read", {"key": "k"})
        self.assertFalse(os.path.exists(self.mark) or os.path.exists(self.ids))

    def test_oversize_not_read(self):
        code, out, h = post("/api/cards/read", b"", clen=65537)
        self.assertEqual((code, h.rfile.reads), (200, 0))
        self.assertIn("at", out)        # ⚠oversize == empty body == mark-all (documented fallback)

    def test_happy_keys(self):
        code, out, _ = post("/api/cards/read", {"key": "a|done|p", "keys": ["b|done|p", "a|done|p"]})
        self.assertEqual(code, 200)
        self.assertEqual(sorted(cards.cards_read_ids()), ["a|done|p", "b|done|p"])
        self.assertFalse(os.path.exists(self.mark))


class SaverSetTest(_Base):
    def setUp(self):
        super().setUp()
        self.force = os.path.join(self.tmp, ".saver-force.json")
        self.goal = os.path.join(self.tmp, ".saver-goal.json")
        self.patch(sv, "SAVER_FORCE", self.force)
        self.patch(sv, "SAVER_GOAL", self.goal)
        self.patch(sv, "SAVER_VIEW", os.path.join(self.tmp, ".saver-view.json"))
        self.patch(sv, "quota", lambda: {})
        sv._saver_force_cache["at"] = 0.0
        sv._saver_sw_cache["at"] = 0.0

    def _nothing_written(self):
        self.assertFalse(os.path.exists(self.force) or os.path.exists(self.goal))

    def test_malformed_and_empty(self):
        for body in (b"{bad", b"", b"[1]", b"{}"):
            code, out, _ = post("/api/saver/set", body)
            self.assertEqual(code, 400, body)
            self.assertFalse(out["ok"])
        self._nothing_written()

    def test_cross_origin(self):
        self.assertRefused("/api/saver/set", {"mode": "off"})
        self._nothing_written()

    def test_oversize(self):
        code, _, h = post("/api/saver/set", b"", clen=4097)
        self.assertEqual((code, h.rfile.reads), (400, 0))
        self._nothing_written()

    def test_happy(self):
        code, out, _ = post("/api/saver/set", {"mode": "on", "stage": 2, "goal": 80})
        self.assertEqual(code, 200)
        self.assertTrue(out["ok"])
        with open(self.force, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"mode": "on", "stage": 2})
        with open(self.goal, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"goal": 80})


class HealthDismissTest(_Base):
    def setUp(self):
        super().setUp()
        saved = (list(wm._WARN_LOG), dict(wm._SOFT), dict(wm._wmute), set(wm._warned))

        def restore():
            wm._WARN_LOG[:] = saved[0]
            for live_, old in zip((wm._SOFT, wm._wmute, wm._warned), saved[1:]):
                live_.clear()
                live_.update(old)
        self.addCleanup(restore)
        wm._WARN_LOG[:] = [{"key": "k1", "msg": "a"}, {"key": "k2", "msg": "b"}, {"key": "k1", "msg": "c"}]
        wm._SOFT.clear()
        wm._SOFT["k1"] = {"n": 9}
        wm._wmute.clear()
        wm._warned.clear()
        wm._warned.update({"k1", "k2"})

    def _untouched(self):
        self.assertEqual(len(wm._WARN_LOG), 3)
        self.assertIn("k1", wm._warned)
        self.assertNotIn("k1", wm._wmute)

    def test_malformed_and_empty(self):
        for body in (b"{bad", b"", b'{"key": ""}'):
            code, out, _ = post("/api/health/dismiss", body)
            self.assertEqual((code, out), (200, {"ok": False, "n": 0}), body)
        self._untouched()

    def test_cross_origin(self):
        self.assertRefused("/api/health/dismiss", {"key": "k1"})
        self._untouched()

    def test_oversize(self):
        code, out, h = post("/api/health/dismiss", b"", clen=4097)
        self.assertEqual((code, out, h.rfile.reads), (200, {"ok": False, "n": 0}, 0))
        self._untouched()

    def test_happy(self):
        code, out, _ = post("/api/health/dismiss", {"key": "k1"})
        self.assertEqual((code, out), (200, {"ok": True, "n": 2}))
        self.assertEqual([w["key"] for w in wm._WARN_LOG], ["k2"])
        self.assertNotIn("k1", wm._SOFT)
        self.assertNotIn("k1", wm._warned)
        self.assertIn("k2", wm._warned)
        self.assertIn("k1", wm._wmute)


class BgDismissTest(_Base):
    def setUp(self):
        super().setUp()
        saved = (dict(bt._bg_open), dict(bt._bg_dropped), dict(live._parse_cache))

        def restore():
            for d, old in zip((bt._bg_open, bt._bg_dropped, live._parse_cache), saved):
                d.clear()
                d.update(old)
        self.addCleanup(restore)
        self.drop = os.path.join(self.tmp, "bg_drop")
        self.patch(bp, "BG_DROP", self.drop)
        self.patch(bp, "warn_once", lambda *a, **k: None)
        bt._bg_open.clear()
        bt._bg_open["/fp-a"] = {"t1": ("sub", "x"), "t2": ("task", "y")}
        bt._bg_open["/fp-b"] = {"t3": ("bg", "z")}
        live._parse_cache.clear()
        live._parse_cache["/fp-a"] = (0, {"cwd": "/cwd-a"})
        live._parse_cache["/fp-b"] = (0, {"cwd": "/cwd-b"})

    def _untouched(self):
        self.assertEqual(set(bt._bg_open["/fp-a"]), {"t1", "t2"})
        self.assertEqual(set(bt._bg_open["/fp-b"]), {"t3"})

    def test_malformed_refused(self):
        # A broken body once read as {} and cleared every cwd; the UI always sends {cwd} or {tid}.
        for body in (b"{bad", b"", b"{}", b"[1]", b'{"cwd": 5}', b'{"tid": null}',
                     b'{"tid": ""}', b'{"cwd": "  "}', b'{"cwd": "", "tid": " "}'):
            code, out, _ = post("/api/bg/dismiss", body)
            self.assertEqual((code, out["ok"]), (400, False), body)
        self._untouched()
        self.assertEqual(len(live._parse_cache), 2)

    def test_cross_origin(self):
        self.assertRefused("/api/bg/dismiss", {"tid": "t1"})
        self._untouched()
        self.assertEqual(len(live._parse_cache), 2)

    def test_oversize(self):
        code, out, h = post("/api/bg/dismiss", b"", clen=4097)
        self.assertEqual((code, h.rfile.reads, h.close_connection), (400, 0, True))
        self._untouched()

    def test_happy_by_cwd(self):
        code, out, _ = post("/api/bg/dismiss", {"cwd": "/cwd-a"})
        self.assertEqual((code, out), (200, {"ok": True, "removed": 1}))
        self.assertEqual(set(bt._bg_open["/fp-a"]), {"t2"})
        self.assertEqual(set(bt._bg_open["/fp-b"]), {"t3"})
        self.assertIn("t1", bt._bg_dropped)
        self.assertEqual(live._parse_cache, {})
        self.assertTrue(os.path.exists(self.drop))

    def test_happy_by_tid(self):
        self.assertEqual(post("/api/bg/dismiss", {"tid": "t3"})[1]["removed"], 1)
        self.assertEqual(bt._bg_open["/fp-b"], {})


class RemovedRoomRoutesTest(_Base):
    """Room invite/tags/hide/create were removed from the viewer (rooms are managed by sessions): 404 JSON, nothing written."""

    def test_removed_routes_404(self):
        self.patch(bus, "DATA_DIR", self.tmp)
        for path in ("/api/room/invite", "/api/rooms/tags", "/api/rooms/hide", "/api/rooms/unhide", "/api/rooms/create"):
            code, out, _ = post(path, {"room": "r", "ids": ["alice"]}, origin=OWN)
            self.assertEqual((code, out), (404, {"error": "not found"}), path)
            self.assertNotIn(path, RP._PostRoutes._POST_ROUTES)
        self.assertEqual(os.listdir(self.tmp), [])


class UnreadBodyClosesTest(_Base):
    """A body left unread must close the connection, or keep-alive parses it as the next request."""
    ROUTES = {"/api/hook": 1_000_000, "/v1/logs": 8_000_000, "/api/cards/read": 65536,
              "/api/saver/set": 4096, "/api/health/dismiss": 4096, "/api/bg/dismiss": 4096}

    def setUp(self):
        super().setUp()
        self.patch(RP, "ext_ingest", lambda req: (False, "stub"))
        self.patch(RP, "_otel_ingest", lambda d: 0)
        self.patch(RP, "set_cards_read", lambda: "stub")
        self.patch(RP, "saver_set", lambda req: {"ok": False})
        self.patch(RP, "bg_dismiss", lambda *a: 0)
        self.addCleanup(RP._ext_stat.update, dict(RP._ext_stat))
        self.addCleanup(RP._otel_stat.update, dict(RP._otel_stat))

    def test_bad_lengths_close(self):
        for path, cap in self.ROUTES.items():
            for clen in (cap + 1, -1, "abc"):
                _, _, h = post(path, b"", clen=clen, origin=OWN)
                self.assertTrue(h.close_connection, (path, clen))
                self.assertEqual(h.rfile.reads, 0, (path, clen))

    def test_chunked_without_length_refused(self):
        chunked = b'7\r\n{"k":1}\r\n0\r\n\r\n'
        for path in list(self.ROUTES) + ["/api/say", "/api/dm", "/v1/metrics", "/nope"]:
            code, _, h = post(path, chunked, te="chunked")
            self.assertEqual((code, h.rfile.reads, h.close_connection), (411, 0, True), path)

    def test_normal_body_keeps_alive(self):
        for path in self.ROUTES:
            _, _, h = post(path, {"k": 1}, origin=OWN)
            self.assertFalse(h.close_connection, path)


class ViewerOnlyTest(unittest.TestCase):
    """Routes that act as the person (say, DM) or run a process (terminal focus) refuse Origin-less posts."""

    def test_refused_without_viewer_origin(self):
        for path in sorted(VIEWER_ONLY):
            for origin in ("", EVIL):
                code, out, h = post(path, {"x": 1}, origin=origin)
                self.assertEqual(code, 403, (path, origin))
                self.assertEqual(h.rfile.reads, 0, (path, origin))

    def test_viewer_origin_reaches_handler(self):
        # Malformed body: the handler answers 400 itself, so nothing is written or run.
        for path in sorted(VIEWER_ONLY - {"/api/cards/read", "/api/health/dismiss", "/api/review/mark", "/api/term/set"}):
            self.assertEqual(post(path, b"[1]", origin=OWN)[0], 400, path)


if __name__ == "__main__":
    unittest.main()
