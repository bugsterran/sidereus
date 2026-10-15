"""selfcheck: a /clear pair (official keeps the old sid on the same pid, our row has the new sid) is not a mismatch."""
import unittest

from tests._load import sidereus

ss = sidereus("sessions_health")
W = sidereus("warn")

OLD = "aa11aa11-0000-4000-8000-000000000000"
NEW = "bb22bb22-0000-4000-8000-000000000000"
ODD = "cc33cc33-0000-4000-8000-000000000000"


class SelfcheckClear(unittest.TestCase):
    def setUp(self):
        g = ss.selfcheck.__globals__
        keys = ("agent_view", "sid_alive", "mailbox_watches", "warn_once", "SELF_GRACE_S",
                "clear_links", "_sid_claim_stale")
        self.saved = {k: g[k] for k in keys}
        self.warns = []
        self.links = []
        self.stale = set()
        g["agent_view"] = lambda: {"4100": {"sessionId": OLD, "cwd": "/w/a"}}
        g["sid_alive"] = lambda sid: False
        g["mailbox_watches"] = lambda: None
        g["warn_once"] = lambda key, msg, **kw: self.warns.append((key, W._fill(msg, kw.get("vars"))))
        g["SELF_GRACE_S"] = 0
        g["clear_links"] = lambda: self.links
        g["_sid_claim_stale"] = lambda sid, cwd=None: (sid, cwd) in self.stale
        self.since = dict(ss._self_since)
        ss._self_since.clear()

    def tearDown(self):
        ss.selfcheck.__globals__.update(self.saved)
        ss._self_since.clear()
        ss._self_since.update(self.since)

    def keys(self, k):
        return [m for kk, m in self.warns if kk == k]

    def test_clear_link_silences_both(self):
        self.links = [{"pid": "4100", "old": OLD, "new": NEW, "at": 1}]
        ss.selfcheck([{"sid": NEW, "state": "busy", "cwd": "/w/a"}])
        self.assertEqual(self.keys("selfcheck-live"), [])
        self.assertEqual(self.keys("selfcheck-dead"), [])

    def test_link_on_other_pid_ignored(self):
        self.links = [{"pid": "9999", "old": OLD, "new": NEW, "at": 1}]
        ss.selfcheck([{"sid": NEW, "state": "busy", "cwd": "/w/a"}])
        self.assertEqual(len(self.keys("selfcheck-dead")), 1)

    def test_cwd_stale_fallback(self):
        self.stale = {(OLD, "/w/a")}
        ss.selfcheck([{"sid": NEW, "state": "busy", "cwd": "/w/a"}])
        self.assertEqual(self.keys("selfcheck-live"), [])

    def test_unrelated_sid_still_warns(self):
        self.links = [{"pid": "4100", "old": OLD, "new": NEW, "at": 1}]
        ss.selfcheck([{"sid": NEW, "state": "busy", "cwd": "/w/a"},
                      {"sid": ODD, "state": "busy", "cwd": "/w/b"}])
        live = self.keys("selfcheck-live")
        self.assertEqual(len(live), 1)
        self.assertIn(ODD[:8], live[0])
        self.assertNotIn(NEW[:8], live[0])
        self.assertIn("Status uncertain for 1 sessions", live[0])


if __name__ == "__main__":
    unittest.main()
