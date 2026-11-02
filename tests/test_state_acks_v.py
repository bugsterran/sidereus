"""/api/state `acksV`: the server omits `acks` only for a page that sent the same version (sidereus/state.py, bus.ack_ver).
No live files: every reader state() calls is replaced on the state module; ack_ver runs on a temp acks.jsonl."""
import os
import shutil
import tempfile
import types
import unittest

from tests._load import sidereus

st = sidereus("state")
bus = sidereus("bus")
import mailbox_core  # noqa: E402  (on sys.path after the loader)

ACKS = {"m1": {"delivered": ["bob"], "ack": []}}
_READERS = {
    "quota": lambda: None, "sessions_cached": lambda **k: ([], True), "cards": lambda n=50: [],
    "usage": lambda: None, "selfcheck": lambda s: None, "health": lambda: None,
    "cards_read": lambda: "", "cards_read_ids": lambda: [], "presence": lambda: {},
    "messages": lambda since=0: [], "messages_first": lambda: [], "cursors": lambda: {},
    "_load": lambda name, d: d, "_ack_cut": lambda: 600, "attention": lambda *a: None,
    "review": lambda *a: None, "wt_orders": lambda *a: {}, "quota_who": lambda q: None,
    "_saver_state": lambda *a: None, "_saver_view": lambda: None, "_saver_switch": lambda: {},
    "ext_usage_today": lambda: {}, "term_cfg": lambda: "auto",
    "ack_map": lambda cut=None: dict(ACKS), "ack_ver": lambda cut: "5-9-%d" % cut,
}


class StateAcksV(unittest.TestCase):
    def setUp(self):
        self.idle = []
        names = list(_READERS) + ["mail_idle_annotate", "state"]
        self._saved = {k: getattr(st, k) for k in names}
        for k, v in _READERS.items():
            setattr(st, k, v)
        st.mail_idle_annotate = lambda sess, _x, cur, acks, rooms: self.idle.append(acks) or sess
        st.state_cache_clear()

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(st, k, v)
        st.state_cache_clear()

    def test_matching_version_omits_acks_but_idle_gets_the_map(self):
        s = st.state(5, 50, "5-9-600")
        self.assertNotIn("acks", s)
        self.assertEqual((s["acksV"], s["acksSince"]), ("5-9-600", 600))
        self.assertEqual(self.idle[-1], ACKS)

    def test_full_acks_without_or_with_other_version(self):
        for args in ((), (0,), (5, 50, ""), (5, 50, "5-9-1"), (0, 50, "1-1-600")):
            s = st.state(*args)
            self.assertEqual(s["acks"], ACKS, args)
            self.assertEqual(s["acksV"], "5-9-600", args)

    def test_ack_map_failure_sends_full_and_no_version(self):
        st.ack_map = lambda cut=None: bus.AckMapError()
        s = st.state(5, 50, "5-9-600")
        self.assertEqual((s["acks"], s["acksV"]), ({}, ""))

    def test_cache_key_keeps_omitted_body_from_other_callers(self):
        calls = []
        real = self._saved["state"]
        st.state = lambda since, nc, av="": calls.append(av) or real(since, nc, av)
        omit, _ = st._state_body(5, 50, "5-9-600")
        full, _ = st._state_body(5, 50)
        again, _ = st._state_body(5, 50, "5-9-600")
        self.assertNotIn('"acks":', omit)
        self.assertIn('"acks":', full)
        self.assertEqual((again, calls), (omit, ["5-9-600", ""]))

    def test_stale_body_is_only_served_for_the_same_key(self):
        st._state_body(5, 50, "5-9-600")
        with st._state_cache_lock:
            st._state_building.add((5, 50, ""))
            for k, v in list(st._state_cache.items()):
                st._state_cache[k] = (v[0] - 5, v[1], v[2])   # past TTL, inside the stale window
        try:
            full, _ = st._state_body(5, 50)
        finally:
            with st._state_cache_lock:
                st._state_building.discard((5, 50, ""))
        self.assertIn('"acks":', full)


class AckVer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._saved = (mailbox_core.ACKS, bus.time)
        mailbox_core.ACKS = os.path.join(self.tmp, "acks.jsonl")

    def tearDown(self):
        mailbox_core.ACKS, bus.time = self._saved
        shutil.rmtree(self.tmp)

    def test_missing_then_size_and_mtime_change_the_version(self):
        self.assertEqual(bus.ack_ver(7), "0-0-7")
        with open(mailbox_core.ACKS, "w", encoding="utf-8") as f:
            f.write("{}\n")
        os.utime(mailbox_core.ACKS, ns=(10 ** 18, 10 ** 18))
        v1 = bus.ack_ver(7)
        self.assertEqual(v1, "%d-3-7" % 10 ** 18)
        os.utime(mailbox_core.ACKS, ns=(10 ** 18 + 1, 10 ** 18 + 1))
        self.assertNotEqual(bus.ack_ver(7), v1)
        with open(mailbox_core.ACKS, "a", encoding="utf-8") as f:
            f.write("{}\n")
        os.utime(mailbox_core.ACKS, ns=(10 ** 18, 10 ** 18))
        self.assertNotEqual(bus.ack_ver(7), v1)
        self.assertNotEqual(bus.ack_ver(8), bus.ack_ver(7))

    def test_cut_is_stable_inside_a_step_and_moves_across_it(self):
        step = bus.ACK_CUT_STEP_S * 10 ** 9
        base = 1_800_000_000 * 10 ** 9 // step * step + bus.ACK_KEEP_S * 10 ** 9
        cuts = []
        for t in (base, base + step - 1, base + step):
            bus.time = types.SimpleNamespace(time_ns=lambda t=t: t)
            cuts.append(bus._ack_cut())
        self.assertEqual(cuts[0], cuts[1])
        self.assertEqual(cuts[2] - cuts[0], step)


if __name__ == "__main__":
    unittest.main()
