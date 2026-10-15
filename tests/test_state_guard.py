"""/api/state per-piece guard (sidereus/state.py `_piece`) and the branch warm loop surviving a tick exception.
No live files: every reader state() calls is replaced on the state module; warn_once is captured."""
import unittest

from tests._load import sidereus

st = sidereus("state")
g = sidereus("git")

_READERS = {
    "quota": lambda: {"five_hour": {"pct": 10, "leftSec": 100}},
    "sessions_cached": lambda **k: ([], True),
    "cards": lambda n=50: [],
    "usage": lambda: {"block": None},
    "selfcheck": lambda s: None,
    "health": lambda: {"warns": []},
    "cards_read": lambda: "",
    "cards_read_ids": lambda: [],
    "presence": lambda: {},
    "ack_map": lambda: {},
    "messages": lambda since=0: [],
    "messages_first": lambda: [],   # since=0 path (bus.MSG_FIRST stubs)
    "cursors": lambda: {},
    "_load": lambda name, d: d,
    "_ack_cut": lambda: 0,
    "attention": lambda *a: {"rows": []},
    "wt_orders": lambda *a: {"/r": ["a"]},
    "quota_who": lambda q: {"rows": []},
    "_saver_state": lambda pct, left=None: {"on": False},
    "_saver_view": lambda: None,
    "_saver_switch": lambda: {},
    "fail1h": lambda: {"n": 0},
    "ext_usage_today": lambda: {"codex": 1},
}


def _boom(*a, **k):
    raise ValueError("boom")


class StateGuard(unittest.TestCase):
    def setUp(self):
        self._saved = {k: getattr(st, k) for k in list(_READERS) + ["warn_once"]}
        for k, v in _READERS.items():
            setattr(st, k, v)
        self.warns = []
        st.warn_once = lambda key, msg, soft=False, **kw: self.warns.append((key, soft))

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(st, k, v)

    def test_all_ok(self):
        s = st.state()
        self.assertEqual(s["wtOrder"], {"/r": ["a"]})
        self.assertEqual(s["extUsage"], {"codex": 1})
        self.assertEqual(self.warns, [])

    def test_raising_pieces_yield_defaults(self):
        for k in ("attention", "wt_orders", "quota_who", "ext_usage_today", "fail1h",
                  "_saver_state", "_saver_view", "_saver_switch", "usage", "health", "quota", "selfcheck"):
            setattr(st, k, _boom)
        s = st.state()
        self.assertEqual(s["messages"], [])
        self.assertIsNone(s["attention"])
        self.assertEqual(s["wtOrder"], {})
        self.assertIsNone(s["quotaWho"])
        self.assertEqual(s["extUsage"], {})
        self.assertIsNone(s["fail1h"])
        self.assertIsNone(s["saver"])
        self.assertIsNone(s["quota"])
        self.assertIsNone(s["health"])
        keys = {k for k, _ in self.warns}
        self.assertIn("state-attention", keys)
        self.assertIn("state-extUsage", keys)
        self.assertTrue(all(soft for _, soft in self.warns))

    def test_core_piece_still_raises(self):
        st.sessions_cached = _boom
        with self.assertRaises(ValueError):
            st.state()


class WarmLoopSurvives(unittest.TestCase):
    def test_exception_does_not_end_loop(self):
        saved = g._br_warm_tick
        calls = []

        def tick():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("tick")
        w = sidereus("warn")
        saved_w, warns = w.warn_once, []
        w.warn_once = lambda key, *a, **k: warns.append(key)
        g._br_warm_tick = tick
        try:
            g._br_warm_loop(_sleep=lambda s: None, _ticks=3)
        finally:
            g._br_warm_tick = saved
            w.warn_once = saved_w
        self.assertEqual(len(calls), 3)
        self.assertEqual(warns, ["br-warm"])


if __name__ == "__main__":
    unittest.main()
