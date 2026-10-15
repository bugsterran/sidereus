"""First-load stubs (sidereus/bus.py messages_first/messages_range) and state() wiring + rule-1 guard on fail1h.

Temp bus file only; every live piece of state() is monkeypatched on sidereus.state.
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

bus = sidereus("bus")
st = sidereus("state")
F = sidereus("failures")


class FirstLoadStubs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "bus.jsonl")
        with open(self.path, "w", encoding="utf-8") as f:
            for i in range(1, 11):
                f.write(json.dumps({"id": "m%d" % i, "t": i * 100, "from": "a", "to": "b",
                                    "subject": "s%d" % i, "thread": "th", "body": "BODY%d" % i}) + "\n")
        self._saved = bus.BUS
        bus.BUS = self.path
        with bus._parse_lock:
            bus._parse_cache.clear()

    def tearDown(self):
        bus.BUS = self._saved
        with bus._parse_lock:
            bus._parse_cache.clear()
        shutil.rmtree(self.tmp)

    def test_only_newest_n_keep_bodies_and_stubs_keep_metadata(self):
        out = bus.messages_first(3)
        self.assertEqual([m["id"] for m in out], ["m%d" % i for i in range(1, 11)])
        self.assertEqual([m.get("body") for m in out[-3:]], ["BODY8", "BODY9", "BODY10"])
        for m in out[:7]:
            self.assertNotIn("body", m)
            self.assertEqual((m["stub"], m["thread"], m["from"]), (1, "th", "a"))
        self.assertNotIn("stub", out[-1])

    def test_fewer_than_n_is_unchanged(self):
        self.assertEqual(bus.messages_first(50), bus.messages(0))

    def test_range_is_exclusive_and_keeps_newest_n(self):
        self.assertEqual([m["id"] for m in bus.messages_range(200, 600)], ["m3", "m4", "m5"])
        self.assertEqual([m["id"] for m in bus.messages_range(0, 600, 2)], ["m4", "m5"])
        self.assertEqual(bus.messages_range(0, 300)[0]["body"], "BODY1")
        self.assertEqual(len(bus.messages_range(0, None, 10 ** 6)), 10)   # capped at MSG_RANGE_MAX, not an error

    def test_no_n_is_the_first_load_window_and_any_n_is_capped(self):
        # /api/messages without `n` must not return the whole bus; the cap must still admit the feed's HYD_N (1000).
        import inspect
        self.assertEqual(inspect.signature(bus.messages_range).parameters["n"].default, bus.MSG_FIRST)
        self.assertEqual(bus.MSG_RANGE_MAX, 1000)
        with mock.patch.object(bus, "MSG_RANGE_MAX", 4):
            self.assertEqual([m["id"] for m in bus.messages_range(0, None, 10 ** 6)], ["m7", "m8", "m9", "m10"])


class StateWiring(unittest.TestCase):
    """state(): since=0 -> messages_first, since>0 -> messages; fail1h never carries raw tool text."""

    def _patches(self, calls):
        z = lambda *a, **k: None   # noqa: E731
        names = {"quota": z, "sessions_cached": lambda **k: ([], True), "cards": lambda n: [], "usage": z, "selfcheck": z, "health": z,
                 "cards_read": lambda: "", "cards_read_ids": lambda: [], "presence": lambda: {}, "ack_map": lambda: {},
                 "cursors": lambda: {}, "_load": lambda n, d: d, "attention": z, "review": z,
                 "wt_orders": lambda *a: {}, "quota_who": z, "_saver_state": z, "_saver_view": z,
                 "_saver_switch": z, "ext_usage_today": lambda: {}, "term_cfg": lambda: "auto",
                 "messages": lambda s=0: calls.append(("messages", s)) or [],
                 "messages_first": lambda: calls.append(("first",)) or []}
        return [mock.patch.object(st, k, v) for k, v in names.items()]

    def run_state(self, since):
        calls = []
        ps = self._patches(calls)
        for p in ps:
            p.start()
        try:
            return st.state(since), calls
        finally:
            for p in ps:
                p.stop()

    def test_first_load_uses_stubbed_messages(self):
        self.assertEqual(self.run_state(0)[1], [("first",)])
        self.assertEqual(self.run_state(123)[1], [("messages", 123)])

    def test_fail1h_in_state_has_no_raw_tool_output(self):
        now = 1_800_000_000.0
        raw = [{"at": now - 5, "kind": "tool", "proj": "p", "sid": "s", "cwd": "/x", "tool": "Bash",
                "sig": "RAWSIG-leak", "text": "RAWTEXT-leak", "why": "RAWWHY-leak"}]
        old = F._FAIL_1H
        try:
            with mock.patch.object(F, "_fail_events", lambda h, capped=True: (raw, 1, h)), \
                 mock.patch.object(F.time, "time", return_value=now):
                F._fail_1h_build()
            s, _ = self.run_state(0)
            dumped = json.dumps(s["fail1h"])
            self.assertEqual(s["fail1h"]["n"], 1)
            for bad in ("RAWSIG", "RAWTEXT", "RAWWHY", '"text"', '"sig"'):
                self.assertNotIn(bad, dumped)
        finally:
            F._FAIL_1H = old


if __name__ == "__main__":
    unittest.main()
