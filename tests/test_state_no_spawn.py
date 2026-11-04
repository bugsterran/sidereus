"""/api/state never spawns a probe or waits on probe locks on the request thread (`live_probe.request_path`).

No live processes, clock or files: subprocess, IS_MAC, warn_once, account lookups and every state() reader except the
probe callers are replaced on their owning modules; blocked background refreshes are released and joined."""
import threading
import time
import unittest
from unittest import mock

from tests._load import sidereus

st = sidereus("state")
lp = sidereus("live_probe")
live = sidereus("live")
SC = sidereus("sessions_health")


class _SlowSub(object):
    """subprocess stand-in: records the calling thread, then blocks until released (a 5 s hang under load)."""

    def __init__(self, gate):
        self.gate, self.threads = gate, []

    def run(self, argv, **kw):
        self.threads.append(threading.get_ident())
        self.gate.wait(5)
        return mock.Mock(stdout="")


class StateNoSpawn(unittest.TestCase):
    def setUp(self):
        self.gate = threading.Event()
        self.sub = _SlowSub(self.gate)
        self.addCleanup(self._release)
        self.seen = {}

        def perm_rows(rows):   # the probes perm_rows reaches (tool_busy · shell_after) plus the watch probe
            self.seen["busy"] = lp.tool_busy()
            self.seen["after"] = lp.shell_after("/r", 0)
            self.seen["mon"] = live.mailbox_watches()
            return rows

        def cards(n=50):
            self.seen["av"] = lp.agent_view()
            return []
        patches = [
            (lp, "subprocess", self.sub), (live, "subprocess", self.sub), (lp, "IS_MAC", True), (live, "IS_MAC", True),
            (lp, "warn_once", lambda *a, **k: None), (live, "warn_once", lambda *a, **k: None),
            (lp, "bin_path", lambda n: n), (lp, "rich_env", lambda: {}), (lp, "_av_registry_sig", lambda d: None),
            (lp, "_av_accounts", lambda: [("", "/acct", True)]), (lp, "_sid_transcript", lambda sid: ""),
            (lp, "_busy_cache", (0.0, {})), (lp, "_busy_shells", {"/r": ["7"]}), (lp, "_starts_cache", (0.0, (), None)),
            (lp, "_av_cache", [0.0, None]), (lp, "_av_fail", [0.0]), (lp, "_av_held", {}), (lp, "_stale", {}),
            (lp, "_ps_snap_cache", [0.0, None]), (lp, "_ps_snap_fail", [0.0, None]),
            (live, "_mon_cache", [0.0, None]), (live, "_live_cache", (0.0, set())),
            (SC, "clear_links", lambda: []),
            (st, "_tick", lambda: 0.0), (st, "_loadavg", lambda: (1.0, 1.0, 1.0)), (st, "snapshot_age", lambda: 1.0),
            (st, "quota", lambda: None), (st, "sessions_cached", lambda *a, **k: ([{"sid": "s1"}], True)),
            (st, "perm_rows", perm_rows), (st, "cards", cards), (st, "usage", lambda: None),
            (st, "health", lambda: None), (st, "cards_read", lambda: ""), (st, "cards_read_ids", lambda: []),
            (st, "presence", lambda: {}), (st, "ack_map", lambda cut=None: {}), (st, "messages", lambda since=0: []),
            (st, "messages_first", lambda: []), (st, "cursors", lambda: {}), (st, "_load", lambda name, d: d),
            (st, "_ack_cut", lambda: 0), (st, "attention", lambda *a: {"rows": []}), (st, "wt_orders", lambda *a: {}),
            (st, "quota_who", lambda *a: None), (st, "review", lambda rows: None),
            (st, "_saver_state", lambda pct, left=None: None), (st, "_saver_view", lambda: None),
            (st, "_saver_switch", lambda: None), (st, "ext_usage_today", lambda: {}), (st, "state_off", lambda: set()),
        ]
        for mod, name, val in patches:
            p = mock.patch.object(mod, name, val)
            p.start()
            self.addCleanup(p.stop)

    def _release(self):
        self.gate.set()
        for t in threading.enumerate():
            if t.name == "bg-refresh":
                t.join(5)

    def test_cold_probes_unknown_and_no_spawn_on_request_thread(self):
        t0 = time.monotonic()
        st.state()
        self.assertLess(time.monotonic() - t0, 1.0)
        self.assertNotIn(threading.get_ident(), self.sub.threads)
        # cold caches read as unknown, never «nothing running» / «no sessions»
        self.assertEqual((self.seen["busy"], self.seen["mon"], self.seen["av"]), (None, None, None))
        self.assertTrue(self.seen["after"])

    def test_stale_values_served_while_refresh_blocks(self):
        now = time.time()
        lp._av_cache[:] = [now - 30, {"9": {"sessionId": "s1"}}]
        lp._busy_cache = (now - 5, {"/r": True})
        live._mon_cache[:] = [now - 10, {"/t.jsonl": []}]
        t0 = time.monotonic()
        st.state()
        self.assertLess(time.monotonic() - t0, 1.0)
        self.assertNotIn(threading.get_ident(), self.sub.threads)
        self.assertEqual(self.seen["av"], {"9": {"sessionId": "s1"}})
        self.assertEqual(self.seen["busy"], {"/r": True})
        self.assertEqual(self.seen["mon"], {"/t.jsonl": []})

    def test_held_ps_lock_does_not_block_request(self):
        with lp._ps_snap_lock, lp._av_lock:     # a background collector mid-spawn
            t0 = time.monotonic()
            st.state()
            self.assertLess(time.monotonic() - t0, 1.0)

    def test_outside_request_path_still_spawns_inline(self):
        self.gate.set()
        self.assertEqual(lp._ps_snap(), [])
        self.assertIn(threading.get_ident(), self.sub.threads)


if __name__ == "__main__":
    unittest.main()
