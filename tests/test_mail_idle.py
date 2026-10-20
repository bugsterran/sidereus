"""sidereus/mail_idle.py: unread mail on a session nothing will wake (temp store, injected now, no live files)."""
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

mi = sidereus("mail_idle")

NOW = 1_800_000_000.0
NS = 10 ** 9


def row(state="wait", sid="s1", mbox="me", **kw):
    r = {"sid": sid, "state": state, "mbox": mbox, "plat": "cc", "mon": [], "ageSec": 900}
    r.update(kw)
    return r


def msg(mid, age_s, **kw):
    m = {"id": mid, "t": int((NOW - age_s) * NS), "from": "peer", "subject": "SECRET-SUBJ", "body": "SECRET-BODY"}
    m.update(kw)
    return m


class MailIdle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, ".wake"))
        self._dd, self._cfg = mi.DATA_DIR, mi.CFG
        mi.DATA_DIR, mi.CFG = self.tmp, {}

    def tearDown(self):
        mi.DATA_DIR, mi.CFG = self._dd, self._cfg
        shutil.rmtree(self.tmp, ignore_errors=True)

    def lock(self, sid, age_s):
        p = os.path.join(self.tmp, ".wake", sid + ".lock")
        open(p, "w").close()
        os.utime(p, (NOW - age_s, NOW - age_s))

    def run1(self, rows, msgs, cursors=None, acks=None, rooms=None):
        return mi.annotate(rows, msgs, cursors or {}, acks or {}, rooms or {}, now=NOW)

    def test_R3_idle_after_N(self):
        msgs = [msg("a", 700, to="me"), msg("b", 30, room="r1"), msg("c", 900, to="other"),
                msg("d", 800, to="me"), msg("e", 650, room="r2")]
        rooms = {"r1": {"members": ["me", "peer"]}, "r2": {"members": ["peer"]}}
        out = self.run1([row()], msgs, acks={"d": {"delivered": ["me"], "ack": []}}, rooms=rooms)
        self.assertEqual(out[0]["mailIdle"], {"n": 2, "age": 700})
        # younger than 10 min -> nothing
        self.assertNotIn("mailIdle", self.run1([row()], [msg("a", 300, to="me")])[0])
        # behind the read cursor -> nothing
        self.assertNotIn("mailIdle", self.run1([row()], [msg("a", 700, to="me")], cursors={"me": int(NOW * NS)})[0])

    def test_R3_not_when_lock_fresh(self):
        self.lock("s1", 3)
        self.assertNotIn("mailIdle", self.run1([row()], [msg("a", 700, to="me")])[0])
        self.lock("s1", 60)   # stale lock = no waiter
        self.assertIn("mailIdle", self.run1([row()], [msg("a", 700, to="me")])[0])
        # ext row with a fresh lock gets one «Mailbox watch» row
        self.lock("x1", 2)
        ext = self.run1([row(sid="x1", plat="codex")], [])[0]
        self.assertEqual(ext["mon"], [{"lab": "Mailbox watch", "src": "proc"}])

    def test_R3_not_when_working(self):
        for st in ("tool", "think", "ask", "done"):
            self.assertNotIn("mailIdle", self.run1([row(state=st)], [msg("a", 700, to="me")])[0])
        self.assertNotIn("mailIdle", self.run1([row(mbox="")], [msg("a", 700, to="")])[0])

    def test_R3_no_body_keys(self):
        src = row()
        out = self.run1([src], [msg("a", 700, to="me")])[0]
        self.assertEqual(set(out["mailIdle"]), {"n", "age"})
        self.assertNotIn("SECRET", repr(out))
        self.assertNotIn("mailIdle", src)   # cached snapshot row untouched

    def test_R3_N_from_cfg(self):
        mi.CFG = {"mail_idle_min": 30}
        self.assertNotIn("mailIdle", self.run1([row()], [msg("a", 700, to="me")])[0])
        self.assertIn("mailIdle", self.run1([row()], [msg("a", 1900, to="me")])[0])

    def test_window_is_wake_lookback(self):
        # older than the wake hook's lookback -> a wake would never show it -> not flagged
        self.assertNotIn("mailIdle", self.run1([row()], [msg("a", mi.MI_LOOKBACK_S + 60, to="me")])[0])
        self.assertIn("mailIdle", self.run1([row()], [msg("a", mi.MI_LOOKBACK_S - 60, to="me")])[0])

    def test_cursor0_skips_lines_before_floor(self):
        new = msg("n", 700, to="me")
        old_t = int((NOW - mi.MI_LOOKBACK_S - 60) * NS)
        fake = type("B", (), {"BUS": "x", "ACK_KEEP_S": mi.bus.ACK_KEEP_S, "_bus_parse": None,
                              "_cached": staticmethod(lambda p, b: ([(old_t, "{not json"), (new["t"], mi.json.dumps(new))], 0, None))})
        real, mi.bus = mi.bus, fake
        try:   # the old line is invalid JSON: decoding it would raise
            out = mi.annotate([row()], None, {}, {}, {}, now=NOW)
        finally:
            mi.bus = real
        self.assertEqual(out[0]["mailIdle"]["n"], 1)


if __name__ == "__main__":
    unittest.main()
